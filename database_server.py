import os
import json
import socket
import threading
import time
import signal
import sys
import uuid
import re
import logging
from datetime import datetime
from copy import deepcopy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('db_server.log')
    ]
)
logger = logging.getLogger(__name__)

PORT = 9001
DB_PATH = 'DB'
WAL_PATH = 'DB/wal.log'
SYNC_INTERVAL = 60

class DBServer:
    def __init__(self, db_path=DB_PATH):
        self.db_path = os.path.abspath(db_path)
        if not os.path.exists(self.db_path):
            os.makedirs(self.db_path)
        self.data = {}
        self.id_maps = {} # {col_name: {_id: doc}}
        self.indexes = {} # {col_name: {field: {val: set(doc_ids)}}}
        self.lock = threading.Lock()
        self.running = True
        self._load_all()
        self._replay_wal()
        self._rebuild_indexes()

    def _load_all(self):
        logger.info("Loading data from disk...")
        for filename in os.listdir(self.db_path):
            if filename.endswith('.json'):
                col_name = filename[:-5]
                file_path = os.path.join(self.db_path, filename)
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                        if content:
                            self.data[col_name] = json.loads(content)
                        else:
                            self.data[col_name] = []
                except Exception as e:
                    logger.error(f"Error loading {filename}: {e}")
                    self.data[col_name] = []

    def _save_all(self):
        with self.lock:
            logger.info("Syncing all collections to disk...")
            for col_name, col_data in self.data.items():
                file_path = os.path.join(self.db_path, f"{col_name}.json")
                temp_path = file_path + ".tmp"
                try:
                    with open(temp_path, 'w') as f:
                        json.dump(col_data, f, default=self._json_serial)
                    os.rename(temp_path, file_path)
                except Exception as e:
                    logger.error(f"Error saving {col_name}: {e}")

            # Clear WAL after successful sync
            if os.path.exists(WAL_PATH):
                open(WAL_PATH, 'w').close()

    def _log_to_wal(self, req):
        try:
            with open(WAL_PATH, 'a') as f:
                f.write(json.dumps(req, default=self._json_serial) + "\n")
        except Exception as e:
            logger.error(f"WAL error: {e}")

    def _replay_wal(self):
        if not os.path.exists(WAL_PATH):
            return
        logger.info("Replaying WAL...")
        try:
            with open(WAL_PATH, 'r') as f:
                for line in f:
                    if line.strip():
                        req = json.loads(line)
                        self.process_request(req, log_wal=False)
        except Exception as e:
            logger.error(f"Error replaying WAL: {e}")

    def _rebuild_indexes(self):
        # Build master ID maps and predefined indexes
        for col_name in self.data:
            self.id_maps[col_name] = {doc['_id']: doc for doc in self.data[col_name] if '_id' in doc}
            self.indexes[col_name] = {}
            self._ensure_index(col_name, '_id')

            # Additional pre-defined indexes for performance
            if col_name == 'userdb':
                self._ensure_index(col_name, 'username')
            elif col_name == 'postdb':
                self._ensure_index(col_name, 'user_id')
            elif col_name == 'commentdb':
                self._ensure_index(col_name, 'post_id')

    def _ensure_index(self, col_name, field):
        if col_name not in self.indexes:
            self.indexes[col_name] = {}
        if field not in self.indexes[col_name]:
            logger.info(f"Building index for {col_name}.{field}")
            self.indexes[col_name][field] = {}
            for doc in self.data[col_name]:
                val = self._get_nested(doc, field)
                if val is not None:
                    if not isinstance(val, (dict, list)): # Only index hashable scalars
                        if val not in self.indexes[col_name][field]:
                            self.indexes[col_name][field][val] = set()
                        self.indexes[col_name][field][val].add(doc['_id'])

    def _update_index_on_insert(self, col_name, doc):
        self.id_maps[col_name][doc['_id']] = doc
        for field in self.indexes[col_name]:
            val = self._get_nested(doc, field)
            if val is not None and not isinstance(val, (dict, list)):
                if val not in self.indexes[col_name][field]:
                    self.indexes[col_name][field][val] = set()
                self.indexes[col_name][field][val].add(doc['_id'])

    def _update_index_on_delete(self, col_name, doc):
        self.id_maps[col_name].pop(doc['_id'], None)
        for field in self.indexes[col_name]:
            val = self._get_nested(doc, field)
            if val in self.indexes[col_name][field]:
                self.indexes[col_name][field][val].discard(doc['_id'])

    def sync_loop(self):
        while self.running:
            time.sleep(SYNC_INTERVAL)
            self._save_all()

    @staticmethod
    def _json_serial(obj):
        if isinstance(obj, datetime):
            return {"$date": obj.isoformat()}
        return str(obj)

    def _json_deserial(self, data):
        if isinstance(data, dict):
            if "$date" in data:
                return datetime.fromisoformat(data["$date"])
            return {k: self._json_deserial(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._json_deserial(v) for v in data]
        return data

    def handle_client(self, conn):
        try:
            buffer = b""
            while True:
                chunk = conn.recv(8192)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    request = json.loads(line.decode('utf-8'))
                    response = self.process_request(request)
                    conn.sendall((json.dumps(response, default=self._json_serial) + "\n").encode('utf-8'))
        except Exception as e:
            logger.debug(f"Client disconnected or error: {e}")
        finally:
            conn.close()

    def process_request(self, req, log_wal=True):
        cmd = req.get('cmd')
        col_name = req.get('col')

        start_time = time.time()

        with self.lock:
            if col_name not in self.data:
                self.data[col_name] = []
                self.id_maps[col_name] = {}
                self.indexes[col_name] = {}
                self._ensure_index(col_name, '_id')

            # Ensure all data in this collection is deserialized
            # (In-memory optimization: only do this if it's currently serialized strings)
            # Actually, the memory state should always be deserialized Python objects.

            if log_wal and cmd in ['insert_one', 'insert_many', 'update_one', 'update_many', 'delete_one', 'delete_many']:
                self._log_to_wal(req)

            res = None
            if cmd == 'find':
                res = self._find(col_name, self._json_deserial(req.get('query')), req.get('limit'), req.get('skip'))
            elif cmd == 'find_one':
                res = self._find_one(col_name, self._json_deserial(req.get('query')))
            elif cmd == 'insert_one':
                res = self._insert_one(col_name, self._json_deserial(req.get('doc')))
            elif cmd == 'insert_many':
                res = self._insert_many(col_name, self._json_deserial(req.get('docs')))
            elif cmd == 'update_one':
                res = self._update(col_name, self._json_deserial(req.get('query')), self._json_deserial(req.get('update')), many=False)
            elif cmd == 'update_many':
                res = self._update(col_name, self._json_deserial(req.get('query')), self._json_deserial(req.get('update')), many=True)
            elif cmd == 'delete_one':
                res = self._delete(col_name, self._json_deserial(req.get('query')), many=False)
            elif cmd == 'delete_many':
                res = self._delete(col_name, self._json_deserial(req.get('query')), many=True)
            elif cmd == 'aggregate':
                res = self._aggregate(col_name, self._json_deserial(req.get('pipeline')))
            elif cmd == 'ping':
                res = {'status': 'pong'}
            else:
                res = {'error': 'Unknown command'}

        duration = time.time() - start_time
        if duration > 0.1: # Log slow queries
            logger.warning(f"Slow query: {cmd} on {col_name} took {duration:.2f}s")

        return res

    def _get_nested(self, doc, key):
        parts = key.split('.')
        val = doc
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            elif isinstance(val, list) and p.isdigit():
                idx = int(p)
                val = val[idx] if 0 <= idx < len(val) else None
            else:
                return None
        return val

    def _match(self, doc, query):
        if not query: return True
        for key, value in query.items():
            if key == "$or":
                if not any(self._match(doc, q) for q in value): return False
                continue

            doc_val = self._get_nested(doc, key)

            if isinstance(value, dict):
                for op, op_val in value.items():
                    if op == "$lt":
                        if not (doc_val is not None and doc_val < op_val): return False
                    elif op == "$gt":
                        if not (doc_val is not None and doc_val > op_val): return False
                    elif op == "$in":
                        if doc_val not in op_val: return False
                    elif op == "$ne":
                        if doc_val == op_val: return False
                    elif op == "$regex":
                        if not (isinstance(doc_val, str) and re.search(op_val, doc_val, re.I if isinstance(op_val, str) else 0)):
                            return False
            elif isinstance(value, str) and value.startswith('__RE__'):
                pattern, flags = value[6:].split('|', 1)
                if not (isinstance(doc_val, str) and re.search(pattern, doc_val, int(flags))):
                    return False
            else:
                if doc_val != value: return False
        return True

    def _find(self, col_name, query, limit=None, skip=0):
        # Use indexes if possible
        candidate_ids = None
        if query:
            for field in self.indexes.get(col_name, {}):
                if field in query and not isinstance(query[field], (dict, list)):
                    val = query[field]
                    ids = self.indexes[col_name][field].get(val, set())
                    if candidate_ids is None:
                        candidate_ids = set(ids)
                    else:
                        candidate_ids &= ids

        # Determine source of documents: index-filtered or full scan
        if candidate_ids is not None:
            docs_to_check = [self.id_maps[col_name][_id] for _id in candidate_ids if _id in self.id_maps[col_name]]
        else:
            docs_to_check = self.data[col_name]

        results = []
        for doc in docs_to_check:
            if self._match(doc, query):
                results.append(doc)

        if skip:
            results = results[skip:]
        if limit:
            results = results[:limit]

        return results

    def _find_one(self, col_name, query):
        # Quick ID lookup using master map
        if query and '_id' in query and isinstance(query['_id'], str):
            doc = self.id_maps[col_name].get(query['_id'])
            if doc and self._match(doc, query):
                return doc
            return None

        # Use other indexes if available (only for simple equality)
        if query:
            for field in self.indexes.get(col_name, {}):
                val = query.get(field)
                if val is not None and not isinstance(val, (dict, list)) and not hasattr(val, 'search'):
                    ids = self.indexes[col_name][field].get(val, set())
                    for _id in ids:
                        doc = self.id_maps[col_name].get(_id)
                        if doc and self._match(doc, query):
                            return doc
                    return None

        for doc in self.data[col_name]:
            if self._match(doc, query):
                return doc
        return None

    def _validate_doc(self, doc):
        if not isinstance(doc, dict):
            raise ValueError("Document must be a dictionary")
        for key in doc.keys():
            if not isinstance(key, str):
                raise ValueError("Field names must be strings")
            if "." in key or key.startswith("$"):
                raise ValueError(f"Invalid field name: {key}")

    def _insert_one(self, col_name, doc):
        self._validate_doc(doc)
        if "_id" not in doc:
            doc["_id"] = uuid.uuid4().hex
        # Initial versioning for optimistic locking
        doc["__v"] = 0
        self.data[col_name].append(doc)
        self._update_index_on_insert(col_name, doc)
        return doc

    def _insert_many(self, col_name, docs):
        results = []
        for d in docs:
            results.append(self._insert_one(col_name, d))
        return results

    def _update(self, col_name, query, update, many=False, upsert=False):
        updated_count = 0

        # Optimized lookup using master map
        docs_to_check = self.data[col_name]
        if query and '_id' in query and isinstance(query['_id'], str):
            doc = self.id_maps[col_name].get(query['_id'])
            docs_to_check = [doc] if doc else []
        elif query:
            # Try other indexes (equality only)
            for field in self.indexes.get(col_name, {}):
                val = query.get(field)
                if val is not None and not isinstance(val, (dict, list)) and not hasattr(val, 'search'):
                    ids = self.indexes[col_name][field].get(val, set())
                    docs_to_check = [self.id_maps[col_name][_id] for _id in ids if _id in self.id_maps[col_name]]
                    break

        for doc in docs_to_check:
            if self._match(doc, query):
                # Optimistic locking check if __v is provided in query
                if "__v" in query and doc.get("__v") != query["__v"]:
                    continue # Version mismatch

                self._apply_update(doc, update)
                doc["__v"] = doc.get("__v", 0) + 1
                updated_count += 1
                if not many:
                    break

        if updated_count == 0 and upsert:
            new_doc = deepcopy(query)
            # Remove operators from query for new doc
            new_doc = {k: v for k, v in new_doc.items() if not k.startswith('$')}
            self._apply_update(new_doc, update)
            self._insert_one(col_name, new_doc)
            return 1

        return updated_count

    def _delete(self, col_name, query, many=False):
        indices_to_remove = []
        for i, doc in enumerate(self.data[col_name]):
            if self._match(doc, query):
                indices_to_remove.append(i)
                if not many:
                    break

        for i in reversed(indices_to_remove):
            doc = self.data[col_name].pop(i)
            self._update_index_on_delete(col_name, doc)

        return len(indices_to_remove) > 0

    def _apply_update(self, doc, update):
        if "$set" in update:
            for k, v in update["$set"].items():
                self._set_nested(doc, k, v)
        if "$inc" in update:
            for k, v in update["$inc"].items():
                old_val = self._get_nested(doc, k) or 0
                self._set_nested(doc, k, old_val + v)
        if "$pull" in update:
            for k, v in update["$pull"].items():
                arr = self._get_nested(doc, k)
                if isinstance(arr, list):
                    new_arr = [i for i in arr if i != v]
                    self._set_nested(doc, k, new_arr)
        if "$addToSet" in update:
            for k, v in update["$addToSet"].items():
                arr = self._get_nested(doc, k)
                if arr is None:
                    arr = []
                    self._set_nested(doc, k, arr)
                if isinstance(arr, list) and v not in arr:
                    arr.append(v)

    def _set_nested(self, doc, key, value):
        parts = key.split('.')
        curr = doc
        for i, p in enumerate(parts[:-1]):
            next_p = parts[i+1]
            if isinstance(curr, dict):
                if p not in curr:
                    curr[p] = [] if next_p.isdigit() else {}
                curr = curr[p]
            elif isinstance(curr, list) and p.isdigit():
                idx = int(p)
                while len(curr) <= idx:
                    curr.append({} if not next_p.isdigit() else [])
                curr = curr[idx]
            else:
                return # Should not happen with valid queries

        last_key = parts[-1]
        if isinstance(curr, dict):
            curr[last_key] = value
        elif isinstance(curr, list) and last_key.isdigit():
            idx = int(last_key)
            while len(curr) <= idx:
                curr.append(None)
            curr[idx] = value

    def _aggregate(self, col_name, pipeline):
        result = self.data[col_name]
        for stage in pipeline:
            if "$match" in stage:
                result = [d for d in result if self._match(d, stage["$match"])]
            elif "$sort" in stage:
                sort_keys = stage["$sort"]
                result = list(result)
                for key, order in reversed(list(sort_keys.items())):
                    result.sort(key=lambda x: (v if not isinstance(v := self._get_nested(x, key), (dict, list)) and v is not None else ""), reverse=(order == -1))
            elif "$group" in stage:
                group_config = stage["$group"]
                group_id_expr = group_config["_id"]
                groups = {}
                for doc in result:
                    gid = self._eval_expr(group_id_expr, doc)
                    gid_key = json.dumps(gid, sort_keys=True) if isinstance(gid, (dict, list)) else gid
                    if gid_key not in groups:
                        groups[gid_key] = {"_id": gid}
                        for field, expr in group_config.items():
                            if field == "_id": continue
                            if "$sum" in expr: groups[gid_key][field] = 0
                            elif "$first" in expr: groups[gid_key][field] = self._eval_expr(expr["$first"], doc)
                    for field, expr in group_config.items():
                        if field == "_id": continue
                        if "$sum" in expr:
                            groups[gid_key][field] += self._eval_expr(expr["$sum"], doc)
                result = list(groups.values())
        return result

    def _eval_expr(self, expr, doc):
        if isinstance(expr, str) and expr.startswith("$"):
            if expr == "$$ROOT": return doc
            return self._get_nested(doc, expr[1:])
        if isinstance(expr, dict):
            if "$cond" in expr:
                cond_part = expr["$cond"]
                if isinstance(cond_part, list): cond, true_val, false_val = cond_part
                else: cond, true_val, false_val = cond_part["if"], cond_part["then"], cond_part["else"]
                return self._eval_expr(true_val, doc) if self._eval_expr(cond, doc) else self._eval_expr(false_val, doc)
            if "$eq" in expr: return self._eval_expr(expr["$eq"][0], doc) == self._eval_expr(expr["$eq"][1], doc)
            if "$and" in expr: return all(self._eval_expr(c, doc) for c in expr["$and"])
        return expr

    def start(self):
        sync_thread = threading.Thread(target=self.sync_loop, daemon=True)
        sync_thread.start()

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('127.0.0.1', PORT))
        server.listen(50)
        logger.info(f"Database server started on port {PORT}")

        def handle_signal(sig, frame):
            logger.info("Shutting down database server...")
            self.running = False
            self._save_all()
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        while True:
            try:
                conn, addr = server.accept()
                client_thread = threading.Thread(target=self.handle_client, args=(conn,))
                client_thread.start()
            except Exception as e:
                if self.running:
                    logger.error(f"Accept error: {e}")

if __name__ == "__main__":
    DBServer().start()
