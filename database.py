import os
import json
import socket
import re
from datetime import datetime
from copy import deepcopy

ASCENDING = 1
DESCENDING = -1
PORT = 9001

class Database:
    def __init__(self, db_path='DB'):
        self.collections = {}

    def __getattr__(self, name):
        if name not in self.collections:
            self.collections[name] = Collection(name)
        return self.collections[name]

    def __getitem__(self, name):
        return getattr(self, name)

class Collection:
    def __init__(self, name):
        self.name = name

    def _send_cmd(self, cmd, **kwargs):
        # Convert any regex objects to a serializable format
        if 'query' in kwargs:
            kwargs['query'] = self._serialize_query(kwargs['query'])
        if 'pipeline' in kwargs:
            kwargs['pipeline'] = self._serialize_pipeline(kwargs['pipeline'])
        if 'doc' in kwargs:
            kwargs['doc'] = self._serialize_doc(kwargs['doc'])
        if 'update' in kwargs:
            kwargs['update'] = self._serialize_doc(kwargs['update'])

        request = {'cmd': cmd, 'col': self.name, **kwargs}

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect(('127.0.0.1', PORT))
                s.sendall((json.dumps(request) + "\n").encode('utf-8'))

                response_data = b""
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    response_data += chunk
                    if b"\n" in response_data:
                        break

                response = json.loads(response_data.decode('utf-8'))
                return self._deserialize_response(response)
        except Exception as e:
            print(f"Database connection error: {e}")
            return None

    def _serialize_query(self, query):
        if not isinstance(query, dict):
            return query
        new_query = {}
        for k, v in query.items():
            if hasattr(v, 'pattern'): # Regex object
                new_query[k] = f"__RE__{v.pattern}|{v.flags}"
            elif isinstance(v, dict):
                new_query[k] = self._serialize_query(v)
            elif isinstance(v, list):
                new_query[k] = [self._serialize_query(i) for i in v]
            else:
                new_query[k] = self._serialize_doc(v)
        return new_query

    def _serialize_doc(self, doc):
        if isinstance(doc, datetime):
            return {"$date": doc.isoformat()}
        if isinstance(doc, dict):
            return {k: self._serialize_doc(v) for k, v in doc.items()}
        if isinstance(doc, list):
            return [self._serialize_doc(i) for i in doc]
        return doc

    def _serialize_pipeline(self, pipeline):
        return [self._serialize_query(stage) for stage in pipeline]

    def _deserialize_response(self, data):
        if isinstance(data, dict):
            if "$date" in data:
                return datetime.fromisoformat(data["$date"])
            return {k: self._deserialize_response(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._deserialize_response(i) for i in data]
        return data

    def find(self, query=None):
        results = self._send_cmd('find', query=self._serialize_query(query)) or []
        return Cursor(results)

    def find_one(self, query=None):
        return self._send_cmd('find_one', query=self._serialize_query(query))

    def insert_one(self, document):
        return self._send_cmd('insert_one', doc=self._serialize_doc(document))

    def update_one(self, query, update):
        return self._send_cmd('update_one', query=self._serialize_query(query), update=self._serialize_doc(update)) > 0

    def update_many(self, query, update):
        return self._send_cmd('update_many', query=self._serialize_query(query), update=self._serialize_doc(update))

    def delete_one(self, query):
        return self._send_cmd('delete_one', query=self._serialize_query(query))

    def aggregate(self, pipeline):
        return self._send_cmd('aggregate', pipeline=self._serialize_pipeline(pipeline)) or []

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
