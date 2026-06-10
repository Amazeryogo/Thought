import os
import json
import socket
import re
import time
import threading
from datetime import datetime
from copy import deepcopy
from queue import Queue, Empty

ASCENDING = 1
DESCENDING = -1
PORT = 9001
MAX_RETRIES = 5
INITIAL_BACKOFF = 0.5 # seconds

class ConnectionPool:
    def __init__(self, host='127.0.0.1', port=PORT, max_connections=10):
        self.host = host
        self.port = port
        self.max_connections = max_connections
        self.pool = Queue(maxsize=max_connections)
        self.lock = threading.Lock()
        self.created_count = 0

    def get_connection(self, timeout=5):
        try:
            return self.pool.get(block=False)
        except Empty:
            with self.lock:
                if self.created_count < self.max_connections:
                    s = self._create_connection()
                    if s:
                        self.created_count += 1
                        return s
            # If pool is full and no connections available, wait a bit
            try:
                return self.pool.get(block=True, timeout=timeout)
            except Empty:
                return None

    def _create_connection(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        try:
            s.connect((self.host, self.port))
            return s
        except Exception:
            return None

    def release_connection(self, conn):
        if conn:
            try:
                self.pool.put(conn, block=False)
            except:
                conn.close()
                with self.lock:
                    self.created_count -= 1

    def drop_connection(self, conn):
        if conn:
            conn.close()
            with self.lock:
                self.created_count -= 1

_pool = ConnectionPool()

class DatabaseError(Exception):
    pass

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
        request = {'cmd': cmd, 'col': self.name, **kwargs}
        retries = 0
        backoff = INITIAL_BACKOFF

        while retries < MAX_RETRIES:
            conn = _pool.get_connection()
            if not conn:
                time.sleep(backoff)
                retries += 1
                backoff *= 2
                continue

            try:
                conn.sendall((json.dumps(request) + "\n").encode('utf-8'))

                response_data = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        raise socket.error("Connection closed")
                    response_data += chunk
                    if b"\n" in response_data:
                        break

                _pool.release_connection(conn)
                response = json.loads(response_data.decode('utf-8'))
                if isinstance(response, dict) and 'error' in response:
                    raise DatabaseError(response['error'])
                return self._deserialize_response(response)
            except (socket.error, json.JSONDecodeError) as e:
                _pool.drop_connection(conn)
                retries += 1
                time.sleep(backoff)
                backoff *= 2
            except Exception as e:
                _pool.release_connection(conn)
                raise e

        raise DatabaseError(f"Failed to connect to database server after {MAX_RETRIES} attempts")

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
        return Cursor(self, query)

    def find_one(self, query=None):
        return self._send_cmd('find_one', query=self._serialize_query(query))

    def insert_one(self, document):
        return self._send_cmd('insert_one', doc=self._serialize_doc(document))

    def insert_many(self, documents):
        return self._send_cmd('insert_many', docs=[self._serialize_doc(d) for d in documents])

    def update_one(self, query, update, upsert=False):
        res = self._send_cmd('update_one', query=self._serialize_query(query), update=self._serialize_doc(update), upsert=upsert)
        return res

    def update_many(self, query, update, upsert=False):
        return self._send_cmd('update_many', query=self._serialize_query(query), update=self._serialize_doc(update), upsert=upsert)

    def delete_one(self, query):
        return self._send_cmd('delete_one', query=self._serialize_query(query))

    def delete_many(self, query):
        return self._send_cmd('delete_many', query=self._serialize_query(query))

    def aggregate(self, pipeline):
        return self._send_cmd('aggregate', pipeline=self._serialize_pipeline(pipeline)) or []

class Cursor:
    def __init__(self, collection, query=None):
        self.collection = collection
        self.query = query or {}
        self._results = None
        self._sort_config = None
        self._limit_n = None

    def sort(self, key, order=ASCENDING):
        self._sort_config = (key, order)
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def _fetch(self):
        if self._results is None:
            # We don't have server-side sorting/limiting yet in the 'find' command,
            # but we can pass them to the server if we update db_server.py
            # For now, let's keep it simple but lazy.
            self._results = self.collection._send_cmd('find', query=self.collection._serialize_query(self.query)) or []

            if self._sort_config:
                key, order = self._sort_config
                if isinstance(key, list):
                    for k, o in reversed(key):
                        self._results.sort(key=lambda x: (v if (v := x.get(k)) is not None else ""), reverse=(o == DESCENDING))
                elif isinstance(key, dict):
                    for k, o in reversed(list(key.items())):
                        self._results.sort(key=lambda x: (v if (v := x.get(k)) is not None else ""), reverse=(o == DESCENDING))
                else:
                    self._results.sort(key=lambda x: (v if (v := x.get(key)) is not None else ""), reverse=(order == DESCENDING))

            if self._limit_n is not None:
                self._results = self._results[:self._limit_n]
        return self._results

    def __iter__(self):
        return iter(self._fetch())

    def __getitem__(self, index):
        return self._fetch()[index]

    def __len__(self):
        return len(self._fetch())

    def list(self):
        return self._fetch()
