import os
import flask_bootstrap
from flask import *
from flask_login import *
from flask_pymongo import *


appx = Flask(__name__)
SECRET_KEY = os.urandom(32)
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