export MONGO_URI="mongodb://localhost:27017/ThoughtDB"
export PORT="8080"
export IMAGES_PATH="IMAGES/" # add your own
export STATIC_FOLDER="bluh/" # add your own
export REPOS_PATH="repos/" # add your own
gunicorn --worker-class eventlet -w 4 -b 0.0.0.0:8080 app:app