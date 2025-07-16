import os
import flask_bootstrap
from flask import *
from flask_login import *
from flask_pymongo import *

with open("secretkey.txt","r") as f:
    SECRET_KEY = f.read()

appx = Flask(__name__)
appx.config['SECRET_KEY'] = SECRET_KEY
appx.config["MONGO_URI"] = os.environ.get("MONGO_URI")
mongo = PyMongo(appx)
login = LoginManager(appx)
login.login_view = '/login'
appx.config['TESTING'] = False
db = mongo.db
flask_bootstrap.Bootstrap(appx)
appx.config['FAVICON'] = 'favicon.ico'
IMAGED = os.environ.get("IMAGES_PATH")
COMMENT_MAX =2000
POST_MAX = 5000
ABOUT_ME_MAX = 50
PASSWORD_MAX = 12
MESSAGE_MAX = 100
USERNAME_MAX = 12
USERNAME_MIN = 2