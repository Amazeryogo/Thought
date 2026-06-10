import os
import json
import socket
import threading
import time
import signal
import sys
import uuid
import re
from datetime import datetime
from copy import deepcopy

PORT = 9001
DB_PATH = 'DB'
SYNC_INTERVAL = 60 # seconds

class DBServer:
    def __init__(self, db_path=DB_PATH):
        self.db_path = os.path.abspath(db_path)
        if not os.path.exists(self.db_path):
            os.makedirs(self.db_path)
        self.data = {}
        self.lock = threading.Lock()
        self.running = True
        self._load_all()

    def _load_all(self):
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
                    print(f"Error loading {filename}: {e}")
                    self.data[col_name] = []

    def _save_all(self):
        with self.lock:
            for col_name, col_data in self.data.items():
                file_path = os.path.join(self.db_path, f"{col_name}.json")
                temp_path = file_path + ".tmp"
                try:
                    with open(temp_path, 'w') as f:
                        json.dump(col_data, f, default=self._json_serial)
                    os.rename(temp_path, file_path)
                except Exception as e:
                    print(f"Error saving {col_name}: {e}")

    def sync_loop(self):
        while self.running:
            time.sleep(SYNC_INTERVAL)
            print("Syncing database to disk...")
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
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    request = json.loads(line.decode('utf-8'))
                    response = self.process_request(request)
                    conn.sendall((json.dumps(response, default=self._json_serial) + "\n").encode('utf-8'))
        except Exception as e:
            print(f"Client error: {e}")
        finally:
            conn.close()

    def process_request(self, req):
        cmd = req.get('cmd')
        col_name = req.get('col')

        with self.lock:
            if col_name not in self.data:
                self.data[col_name] = []

            # Ensure all data in this collection is deserialized (with dates)
            self.data[col_name] = [self._json_deserial(d) if isinstance(d, dict) and any(isinstance(v, str) and v.startswith('20') for v in d.values()) else d for d in self.data[col_name]]

            if cmd == 'find':
                return self._find(col_name, self._json_deserial(req.get('query')))
            elif cmd == 'find_one':
                return self._find_one(col_name, self._json_deserial(req.get('query')))
            elif cmd == 'insert_one':
                return self._insert_one(col_name, self._json_deserial(req.get('doc')))
            elif cmd == 'update_one':
                return self._update(col_name, self._json_deserial(req.get('query')), self._json_deserial(req.get('update')), many=False)
            elif cmd == 'update_many':
                return self._update(col_name, self._json_deserial(req.get('query')), self._json_deserial(req.get('update')), many=True)
            elif cmd == 'delete_one':
                return self._delete(col_name, self._json_deserial(req.get('query')))
            elif cmd == 'aggregate':
                return self._aggregate(col_name, self._json_deserial(req.get('pipeline')))
        return {'error': 'Unknown command'}

    def _get_nested(self, doc, key):
        parts = key.split('.')
        val = doc
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                return None
        return val

    def _match(self, doc, query):
        for key, value in query.items():
            if key == "$or":
                if not any(self._match(doc, q) for q in value):
                    return False
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
                # Handle regex object passed from client
                pattern, flags = value[6:].split('|', 1)
                if not (isinstance(doc_val, str) and re.search(pattern, doc_val, int(flags))):
                    return False
            else:
                if doc_val != value:
                    return False
        return True

    def _find(self, col_name, query):
        query = query or {}
        results = [d for d in self.data[col_name] if self._match(d, query)]
        return results

    def _find_one(self, col_name, query):
        query = query or {}
        for doc in self.data[col_name]:
            if self._match(doc, query):
                return doc
        return None

    def _insert_one(self, col_name, doc):
        if "_id" not in doc:
            doc["_id"] = uuid.uuid4().hex
        self.data[col_name].append(doc)
        return doc

    def _update(self, col_name, query, update, many=False):
        updated_count = 0
        for doc in self.data[col_name]:
            if self._match(doc, query):
                self._apply_update(doc, update)
                updated_count += 1
                if not many:
                    break
        return updated_count

    def _delete(self, col_name, query):
        for i, doc in enumerate(self.data[col_name]):
            if self._match(doc, query):
                self.data[col_name].pop(i)
                return True
        return False

    def _apply_update(self, doc, update):
        if "$set" in update:
            for k, v in update["$set"].items():
                doc[k] = v
        if "$pull" in update:
            for k, v in update["$pull"].items():
                if k in doc and isinstance(doc[k], list):
                    doc[k] = [i for i in doc[k] if i != v]
        if "$addToSet" in update:
            for k, v in update["$addToSet"].items():
                if k not in doc:
                    doc[k] = []
                if v not in doc[k]:
                    doc[k].append(v)

    def _aggregate(self, col_name, pipeline):
        result = self.data[col_name]
        for stage in pipeline:
            if "$match" in stage:
                result = [d for d in result if self._match(d, stage["$match"])]
            elif "$sort" in stage:
                sort_keys = stage["$sort"]
                # We need to copy to avoid modifying the original list in memory if it's reused
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
        server.listen(5)
        print(f"Database server started on port {PORT}")

        def handle_signal(sig, frame):
            print("Shutting down database server...")
            self.running = False
            self._save_all()
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        while True:
            conn, addr = server.accept()
            client_thread = threading.Thread(target=self.handle_client, args=(conn,))
            client_thread.start()

if __name__ == "__main__":
    DBServer().start()
