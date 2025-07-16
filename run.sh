export MONGO_URI="mongodb://localhost:27017/ThoughtDB"
export PORT="8080"
export IMAGES_PATH="IMAGES/"
gunicorn -w 4 -b 0.0.0.0:8080 app:appx