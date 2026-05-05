export MONGO_URI="mongodb://localhost:27017/ThoughtDB"
export PORT="8080"
export IMAGES_PATH="IMAGES/"
gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:8080 app:app