export MONGO_URI="mongodb://localhost:27017/ThoughtDB"
export PORT="8080"
export IMAGES_PATH="IMAGES/" # add your own
export REPOS_PATH="repos/" # add your own
python3 database_server.py &

# Wait for DB to be ready
echo "Waiting for database server to start..."
for i in {1..10}; do
    python3 -c "import socket, json; s=socket.socket(); s.settimeout(1); s.connect(('127.0.0.1', 9001)); s.sendall(b'{\"cmd\": \"ping\", \"col\": \"test\"}\n'); print(s.recv(1024))" > /dev/null 2>&1 && break
    sleep 1
done

gunicorn -w 4 -b 0.0.0.0:8080 --timeout 600 app:app