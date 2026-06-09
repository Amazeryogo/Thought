import os
import json
import uuid
import re
import fcntl
from datetime import datetime
from copy import deepcopy

ASCENDING = 1
DESCENDING = -1

class Database:
    def __init__(self, db_path='DB'):
        self.db_path = os.path.abspath(db_path)
        if not os.path.exists(self.db_path):
            os.makedirs(self.db_path)
        self.collections = {}

    def __getattr__(self, name):
        if name not in self.collections:
            self.collections[name] = Collection(self.db_path, name)
        return self.collections[name]

    def __getitem__(self, name):
        return getattr(self, name)

class Collection:
    def __init__(self, db_path, name):
        self.file_path = os.path.join(db_path, f"{name}.json")
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w') as f:
                json.dump([], f)

    def _load(self):
        with open(self.file_path, 'r') as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                content = f.read()
                if not content:
                    return []
                data = json.loads(content)
                return [self._json_deserial(d) for d in data]
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _save(self, data):
        temp_path = self.file_path + ".tmp"
        with open(self.file_path, 'r+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                with open(temp_path, 'w') as tf:
                    json.dump(data, tf, default=self._json_serial)
                os.rename(temp_path, self.file_path)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

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

    def _match(self, doc, query):
        for key, value in query.items():
            if key == "$or":
                if not any(self._match(doc, q) for q in value):
                    return False
                continue

            doc_val = doc.get(key)

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
            elif hasattr(value, 'search'): # Regex
                if not (isinstance(doc_val, str) and value.search(doc_val)):
                    return False
            else:
                if doc_val != value:
                    return False
        return True

    def find(self, query=None):
        query = query or {}
        data = self._load()
        results = [d for d in data if self._match(d, query)]
        return Cursor(results)

    def find_one(self, query=None):
        query = query or {}
        data = self._load()
        for doc in data:
            if self._match(doc, query):
                return doc
        return None

    def insert_one(self, document):
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w') as f:
                json.dump([], f)
        # We need an exclusive lock during the whole read-modify-write cycle
        with open(self.file_path, 'r+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                content = f.read()
                data = json.loads(content) if content else []
                data = [self._json_deserial(d) for d in data]

                doc = deepcopy(document)
                if "_id" not in doc:
                    doc["_id"] = uuid.uuid4().hex
                data.append(doc)

                temp_path = self.file_path + ".tmp"
                with open(temp_path, 'w') as tf:
                    json.dump(data, tf, default=self._json_serial)
                os.rename(temp_path, self.file_path)
                return doc
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def update_one(self, query, update):
        with open(self.file_path, 'r+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                content = f.read()
                data = json.loads(content) if content else []
                data = [self._json_deserial(d) for d in data]

                updated = False
                for doc in data:
                    if self._match(doc, query):
                        self._apply_update(doc, update)
                        updated = True
                        break

                if updated:
                    temp_path = self.file_path + ".tmp"
                    with open(temp_path, 'w') as tf:
                        json.dump(data, tf, default=self._json_serial)
                    os.rename(temp_path, self.file_path)
                return updated
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def update_many(self, query, update):
        with open(self.file_path, 'r+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                content = f.read()
                data = json.loads(content) if content else []
                data = [self._json_deserial(d) for d in data]

                updated_count = 0
                for doc in data:
                    if self._match(doc, query):
                        self._apply_update(doc, update)
                        updated_count += 1

                if updated_count > 0:
                    temp_path = self.file_path + ".tmp"
                    with open(temp_path, 'w') as tf:
                        json.dump(data, tf, default=self._json_serial)
                    os.rename(temp_path, self.file_path)
                return updated_count
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def delete_one(self, query):
        with open(self.file_path, 'r+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                content = f.read()
                data = json.loads(content) if content else []
                data = [self._json_deserial(d) for d in data]

                for i, doc in enumerate(data):
                    if self._match(doc, query):
                        data.pop(i)
                        temp_path = self.file_path + ".tmp"
                        with open(temp_path, 'w') as tf:
                            json.dump(data, tf, default=self._json_serial)
                        os.rename(temp_path, self.file_path)
                        return True
                return False
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

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

    def aggregate(self, pipeline):
        data = self._load()

        result = data
        for stage in pipeline:
            if "$match" in stage:
                result = [d for d in result if self._match(d, stage["$match"])]
            elif "$sort" in stage:
                sort_keys = stage["$sort"]
                for key, order in reversed(list(sort_keys.items())):
                    result.sort(key=lambda x: (v if (v := self._get_nested(x, key)) is not None else ""), reverse=(order == DESCENDING))
            elif "$group" in stage:
                group_config = stage["$group"]
                group_id_expr = group_config["_id"]
                groups = {}
                for doc in result:
                    gid = self._eval_expr(group_id_expr, doc)
                    if gid not in groups:
                        groups[gid] = {"_id": gid}
                        for field, expr in group_config.items():
                            if field == "_id": continue
                            if "$sum" in expr:
                                groups[gid][field] = 0
                            elif "$first" in expr:
                                groups[gid][field] = self._eval_expr(expr["$first"], doc)

                    for field, expr in group_config.items():
                        if field == "_id": continue
                        if "$sum" in expr:
                            val = self._eval_expr(expr["$sum"], doc)
                            groups[gid][field] += val
                result = list(groups.values())
        return result

    def _get_nested(self, doc, key):
        parts = key.split('.')
        val = doc
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                return None
        return val

    def _eval_expr(self, expr, doc):
        if isinstance(expr, str) and expr.startswith("$"):
            if expr == "$$ROOT":
                return doc
            key = expr[1:]
            return self._get_nested(doc, key)
        if isinstance(expr, dict):
            if "$cond" in expr:
                cond_part = expr["$cond"]
                if isinstance(cond_part, list):
                    cond, true_val, false_val = cond_part
                else:
                    cond = cond_part["if"]
                    true_val = cond_part["then"]
                    false_val = cond_part["else"]

                if self._eval_expr(cond, doc):
                    return self._eval_expr(true_val, doc)
                else:
                    return self._eval_expr(false_val, doc)
            if "$eq" in expr:
                return self._eval_expr(expr["$eq"][0], doc) == self._eval_expr(expr["$eq"][1], doc)
            if "$and" in expr:
                return all(self._eval_expr(c, doc) for c in expr["$and"])
        return expr

class Cursor:
    def __init__(self, data):
        self.data = data

    def sort(self, key, order=ASCENDING):
        if isinstance(key, list):
            for k, o in reversed(key):
                self.data.sort(key=lambda x: x.get(k) if x.get(k) is not None else "", reverse=(o == DESCENDING))
        elif isinstance(key, dict):
            for k, o in reversed(list(key.items())):
                self.data.sort(key=lambda x: x.get(k) if x.get(k) is not None else "", reverse=(o == DESCENDING))
        else:
            self.data.sort(key=lambda x: x.get(key) if x.get(key) is not None else "", reverse=(order == DESCENDING))
        return self

    def limit(self, n):
        self.data = self.data[:n]
        return self

    def __iter__(self):
        return iter(self.data)

    def __getitem__(self, index):
        return self.data[index]

    def __len__(self):
        return len(self.data)

    def list(self):
        return self.data
