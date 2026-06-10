export MONGO_URI="mongodb://localhost:27017/ThoughtDB"
export PORT="8080"
export IMAGES_PATH="IMAGES/" # add your own
export REPOS_PATH="repos/" # add your own
python3 database_server.py &
sleep 2
gunicorn -w 4 -b 0.0.0.0:8080 --timeout 600 app:app