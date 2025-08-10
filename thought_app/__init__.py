import os
from flask import Flask
from flask_login import LoginManager
from flask_pymongo import PyMongo
import flask_bootstrap
from flask_mail import Mail

with open("secretkey.txt", "r") as f:
    SECRET_KEY = f.read()

appx = Flask(__name__)
appx.config['SECRET_KEY'] = SECRET_KEY
appx.config["MONGO_URI"] = os.environ.get("MONGO_URI")

# Email config for password reset
appx.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.googlemail.com')
appx.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
appx.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
appx.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
appx.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')


mongo = PyMongo(appx)
login = LoginManager(appx)
login.login_view = '/login'
appx.config['TESTING'] = False
db = mongo.db
flask_bootstrap.Bootstrap(appx)
mail = Mail(appx)
appx.config['FAVICON'] = 'favicon.ico'
IMAGED = os.environ.get("IMAGES_PATH")
COMMENT_MAX = 2000
POST_MAX = 5000
ABOUT_ME_MAX = 50
PASSWORD_MAX = 12
MESSAGE_MAX = 100
USERNAME_MAX = 12
USERNAME_MIN = 2
STATIC_FOLDER = "bluh"
JWT_SECRET = os.environ.get("JWT_SECRET", SECRET_KEY)
JWT_ALGORITHM = "HS256"
JWT_EXP_DELTA_SECONDS = 3600

from . import routes
from . import apiroutes
