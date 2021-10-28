from flask import Flask, flash, render_template, request, session, make_response,  redirect, url_for
from forms import *
import os
from flask import Flask
from flask_pymongo import PyMongo
from flask_login import LoginManager
from flask import render_template, url_for, request, flash
from flask import request
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import current_user, login_user, logout_user, login_required, UserMixin
import uuid


appx = Flask(__name__)
SECRET_KEY = os.urandom(32)
appx.config['SECRET_KEY'] = SECRET_KEY
appx.config["MONGO_URI"] = "mongodb://localhost:27017/ThoughtDB" 
mongo = PyMongo(appx)
login = LoginManager(appx)
login.login_view = '/login'
appx.config['TESTING'] = False
db = mongo.db



class User(UserMixin):

    def __init__(self, username, email, password,invcode, _id=None,):

        self.username = username
        self.email = email
        self.password = password
        self.invcode = invcode
        self._id = uuid.uuid4().hex if _id is None else _id

    def is_authenticated(self):
        return True
    def is_active(self):
        return True
    def is_anonymous(self):
        return False
    def get_id(self):
        return self._id

    @classmethod
    def get_by_username(cls, username):
        data = db.userdb.find_one({"username": username})
        if data is not None:
            return cls(**data)

    @classmethod
    def get_by_email(cls, email):
        data = db.userdb.find_one({"email": email})
        if data is not None:
            return cls(**data)

    @classmethod
    def get_by_id(cls, _id):
        data = db.userdb.find_one({"_id": _id})
        if data is not None:
            return cls(**data)

    @staticmethod
    def login_valid(username, password):
        verify_user = User.get_by_username(username)
        if verify_user is not None:
            return check_password_hash(verify_user.password, password)
        return False

    @classmethod
    def register(cls, username, email, password, invcode):
        user = cls.get_by_email(email)
        if user is None:
            new_user = cls( username, email, password, invcode)
            new_user.save_to_mongo()
            session['email'] = email
            return True
        else:
            return False

    def json(self):
        return {
            "username": self.username,
            "email": self.email,
            "_id": self._id,
            "invcode" : self.invcode,
            "password": self.password
        }

    def save_to_mongo(self):
        db.userdb.insert(self.json())

@login.user_loader
def load_user(user_id):
    return User.get_by_id(user_id)


@appx.route('/')
@appx.route('/home')
def home():
    return render_template('home.html')

@appx.route("/register", methods=['GET', 'POST'])
def register():
    form = CreateUserForm()
    if form.validate_on_submit():
        if request.method == 'POST':
            username = request.form["username"]
            email = request.form["email"]
            invcode = request.form["invcode"]
            password = generate_password_hash(request.form["password"])#.decode('utf-8')
            find_user =  User.get_by_email(email)
            if find_user is None:
                User.register(username, email, password,invcode)
                flash(f'Account created for {form.username.data}!', 'success')
                return redirect(url_for('home'))
            else:
                flash(f'Account already exists for {form.username.data}!', 'success')
    return render_template('create.html', title='Register', form=form)


@appx.route("/login", methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        if request.method == 'POST':
            username = request.form["username"]
            password = request.form["password"]
            user = User.get_by_username(username)
            if user is not None and User.login_valid(username, password):
                login_user(user)
                flash(f'You are now logged in as {form.username.data}!', 'success')
                return redirect(url_for('home'))
            else:
                flash(f'Invalid login!', 'danger')
    return render_template('login.html', title='Login', form=form)


@appx.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))


@appx.route('/api/about')
def api_about():
    uhh = {
        "name" : "Thought",
        "version": "1.0"
    }
    return str(uhh)

@appx.route("/api/register", methods=['GET', 'POST'])
def registerapi():
    x = request.args
    username = x.get("username")
    email = x.get("email")
    invcode = x.get("invcode")
    password = generate_password_hash(x.get("password"))#.decode('utf-8')
    find_user =  User.get_by_email(email)
    if find_user is None:
        User.register(username, email, password,invcode)
        return "{\"comment\" : \"OK!\"}" 
    else:
        return "{\"comment\" : \"USER ALREADY EXISTS, ERROR 404\"}"

@appx.route("/api/login", methods=['GET', 'POST'])
def loginapi():
    x = request.args
    username = x.get("username")
    password = x.get("password")
    user = User.get_by_username(username)
    if user is not None and User.login_valid(username, password):
        return "{\"comment\" : \"OK!\"}" 
    else:
        return "{\"comment\" : \"INVALID LOGIN, ERROR 404\"}"
        

@appx.route('/api/logout')
def logoutapi():
    logout_user()
    return "{\"comment\" : \" LOGGED OUT \"}"

# a simple page that returns the user's personal information
@appx.route('/user')
@login_required
def user():
    return render_template('user.html', user=current_user)
