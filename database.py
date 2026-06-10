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
        self.lock_path = os.path.join(db_path, f"{name}.lock")
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w') as f:
                json.dump([], f)
        if not os.path.exists(self.lock_path):
            open(self.lock_path, 'a').close()

    def _lock(self, mode):
        if not os.path.exists(self.lock_path):
            open(self.lock_path, 'a').close()
        self._lock_file = open(self.lock_path, 'r')
        fcntl.flock(self._lock_file, mode)

    def _unlock(self):
        fcntl.flock(self._lock_file, fcntl.LOCK_UN)
        self._lock_file.close()

    def _load(self):
        if not os.path.exists(self.file_path):
            return []
        with open(self.file_path, 'r') as f:
            content = f.read()
            if not content:
                return []
            data = json.loads(content)
            return [self._json_deserial(d) for d in data]

    def _save(self, data):
        temp_path = self.file_path + ".tmp"
        with open(temp_path, 'w') as f:
            json.dump(data, f, default=self._json_serial)
        os.rename(temp_path, self.file_path)

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
            elif hasattr(value, 'search'): # Regex object
                if not (isinstance(doc_val, str) and value.search(doc_val)):
                    return False
            else:
                if doc_val != value:
                    return False
        return True

    def find(self, query=None):
        query = query or {}
        self._lock(fcntl.LOCK_SH)
        try:
            data = self._load()
            results = [d for d in data if self._match(d, query)]
            return Cursor(results)
        finally:
            self._unlock()

    def find_one(self, query=None):
        query = query or {}
        self._lock(fcntl.LOCK_SH)
        try:
            data = self._load()
            for doc in data:
                if self._match(doc, query):
                    return doc
            return None
        finally:
            self._unlock()

    def insert_one(self, document):
        self._lock(fcntl.LOCK_EX)
        try:
            data = self._load()
            doc = deepcopy(document)
            if "_id" not in doc:
                doc["_id"] = uuid.uuid4().hex
            data.append(doc)
            self._save(data)
            return doc
        finally:
            self._unlock()

    def update_one(self, query, update):
        self._lock(fcntl.LOCK_EX)
        try:
            data = self._load()
            updated = False
            for doc in data:
                if self._match(doc, query):
                    self._apply_update(doc, update)
                    updated = True
                    break
            if updated:
                self._save(data)
            return updated
        finally:
            self._unlock()

    def update_many(self, query, update):
        self._lock(fcntl.LOCK_EX)
        try:
            data = self._load()
            updated_count = 0
            for doc in data:
                if self._match(doc, query):
                    self._apply_update(doc, update)
                    updated_count += 1
            if updated_count > 0:
                self._save(data)
            return updated_count
        finally:
            self._unlock()

    def delete_one(self, query):
        self._lock(fcntl.LOCK_EX)
        try:
            data = self._load()
            for i, doc in enumerate(data):
                if self._match(doc, query):
                    data.pop(i)
                    self._save(data)
                    return True
            return False
        finally:
            self._unlock()

    def _apply_update(self, doc, update):
        if "$set" in update:
            for k, v in update["$set"].items():
                # Note: nested $set not fully implemented for simplicity
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
        self._lock(fcntl.LOCK_SH)
        try:
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
                        # gid might be a dict, need it to be hashable for groups dict
                        if isinstance(gid, dict):
                            gid_key = json.dumps(gid, sort_keys=True)
                        else:
                            gid_key = gid

                        if gid_key not in groups:
                            groups[gid_key] = {"_id": gid}
                            for field, expr in group_config.items():
                                if field == "_id": continue
                                if "$sum" in expr:
                                    groups[gid_key][field] = 0
                                elif "$first" in expr:
                                    groups[gid_key][field] = self._eval_expr(expr["$first"], doc)

                        for field, expr in group_config.items():
                            if field == "_id": continue
                            if "$sum" in expr:
                                val = self._eval_expr(expr["$sum"], doc)
                                groups[gid_key][field] += val
                    result = list(groups.values())
            return result
        finally:
            self._unlock()

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
                self.data.sort(key=lambda x: (v if (v := x.get(k)) is not None else ""), reverse=(o == DESCENDING))
        elif isinstance(key, dict):
            for k, o in reversed(list(key.items())):
                self.data.sort(key=lambda x: (v if (v := x.get(k)) is not None else ""), reverse=(o == DESCENDING))
        else:
            self.data.sort(key=lambda x: (v if (v := x.get(key)) is not None else ""), reverse=(order == DESCENDING))
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
