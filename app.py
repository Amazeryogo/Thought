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

app = Flask(__name__)
SECRET_KEY = os.urandom(32)
app.config['SECRET_KEY'] = SECRET_KEY
app.config["MONGO_URI"] = "mongodb://localhost:27017/ThoughtDB" 
mongo = PyMongo(app)
login = LoginManager(app)
db = mongo.db

@login.user_loader
def load_user(user_id):
    user =User.get_by_id(user_id)
    if user is not None:
        return User(user["_id"])
    else:
        return None

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
        db.userdb.insert( self.json())


@app.route('/')
@app.route('/home')
@login_required() 
def home():
    return render_template('home.html')

@app.route("/register", methods=['GET', 'POST'])
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


@app.route("/login", methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = request.form["username"]
        password = request.form["password"]
        find_user = db.userdb.find_one({"username": username})
        if User.login_valid(username, password):
            loguser = User(find_user["_id"], find_user["username"], find_user["password"], find_user["invcode"])
            login_user(loguser, remember=form.remember_me.data)
            flash('You have been logged in!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', title='Login', form=form)
@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))