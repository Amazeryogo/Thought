import os
import flask_bootstrap
from flask import *
from flask_login import *
from flask_pymongo import *
from flask_mail import Mail

with open("secretkey.txt","r") as f:
    SECRET_KEY = f.read()

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config["MONGO_URI"] = os.environ.get("MONGO_URI")
mongo = PyMongo(app)
login = LoginManager(app)
login.login_view = '/login'
app.config['TESTING'] = False
db = mongo.db
flask_bootstrap.Bootstrap(app)

@app.context_processor
def inject_globals():
    from models import User
    return dict(User=User)

app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.googlemail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
mail = Mail(app)
app.config['FAVICON'] = 'favicon.ico'
app.config['JWT_SECRET'] = os.environ.get("JWT_SECRET", SECRET_KEY)
app.config['JWT_ALGORITHM'] = "HS256"
app.config['JWT_EXP_DELTA_SECONDS'] = 3600
IMAGED = os.environ.get("IMAGES_PATH")
REPOS_PATH = os.environ.get("REPOS_PATH")
COMMENT_MAX =2048
COMMENT_MIN =2
POST_MAX = 512
POST_MIN = 2
ABOUT_ME_MAX = 256
ABOUT_ME_MIN = 2
PASSWORD_MAX = 16
PASSWORD_MIN = 8
MESSAGE_MAX = 256
MESSAGE_MIN = 2
USERNAME_MAX = 16
USERNAME_MIN = 2
STATIC_FOLDER = os.environ.get("STATIC_FOLDER")