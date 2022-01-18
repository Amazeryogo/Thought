from flask import Flask, flash, render_template, request, session, make_response, redirect, url_for
from forms import *
import os
from flask_pymongo import *
from flask_login import LoginManager
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import current_user, login_user, logout_user, login_required, UserMixin
import uuid
from hashlib import md5
from datetime import datetime as bruh
import flask_bootstrap

appx = Flask(__name__)
SECRET_KEY = os.urandom(32)
appx.config['SECRET_KEY'] = SECRET_KEY
# get from heroku config variables
appx.config["MONGO_URI"] = os.environ.get("MONGO_URI")
mongo = PyMongo(appx)
login = LoginManager(appx)
login.login_view = '/login'
appx.config['TESTING'] = False
db = mongo.db
flask_bootstrap.Bootstrap(appx)


class User(UserMixin):

    def __init__(self, username, email, password, invcode, _id=None, aboutme=None):
        if aboutme is None:
            aboutme = "New to Thought"
            self.aboutme = aboutme
        else:
            self.aboutme = aboutme

        self.username = username
        self.email = email
        self.password = password
        self.invcode = invcode
        self._id = uuid.uuid4().hex if _id is None else _id
        self.posts = db.postdb.find({"user_id": self._id})

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
    def addaboutme(cls, username, aboutme):
        db.userdb.update_one({"username": username}, {"$set": {"aboutme": aboutme}})

    @classmethod
    def get_aboutme(cls, username):
        data = db.userdb.find_one({"username": username})
        if data is not None:
            return data["aboutme"]
        else:
            return "No About Me"

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

    @classmethod
    def change_email(cls, username, email):
        existing_user = db.userdb.find_one({"email": email})
        if existing_user is None:
            db.userdb.update_one({"username": username}, {"$set": {"email": email}})
            return True
        else:
            return False

    @staticmethod
    def login_valid(username, password):
        verify_user = User.get_by_username(username)
        if verify_user is not None:
            return check_password_hash(verify_user.password, password)
        return True

    # rewrite register function
    @classmethod
    def register(cls, username, email, password, invcode):
        user = User.get_by_username(username)
        user_by_email = User.get_by_email(email)
        if user is None and user_by_email is None:
            new_user = User(username, email, password, invcode)
            new_user.save_to_mongo()
            return True
        else:
            return False

    def json(self):
        return {
            "username": self.username,
            "email": self.email,
            "_id": self._id,
            "aboutme": self.aboutme,
            "invcode": self.invcode,
            "password": self.password
        }

    @classmethod
    def avatar(self, username):
        x = db.userdb.find_one({"username": username})
        if x is not None:
            email = x["email"]
            digest = md5(email.lower().encode('utf-8')).hexdigest()
            return 'https://www.gravatar.com/avatar/{}?d=identicon&s={}'.format(
                digest, 128)

    def save_to_mongo(self):
        db.userdb.insert_one(self.json())


class Messages:
    def __init__(self, sender, receiver, timestamp, message, _id=None):
        self.sender = sender
        self.receiver = receiver
        self.timestamp = timestamp
        self.message = message
        self._id = uuid.uuid4().hex if _id is None else _id

    def json(self):
        return {
            "sender": self.sender,
            "receiver": self.receiver,
            "message": self.message,
            "timestamp": self.timestamp,
            "_id": self._id
        }

    # a function that compiles a chat between two users and sort them by timestamps
    @classmethod
    def get_chat(cls, user1, user2):
        chats = db.messagesdb.find(
            {"$or": [{"sender": user1, "receiver": user2}, {"sender": user2, "receiver": user1}]})
        # sort using timestamps
        chats = list(chats)
        chats.sort(key=lambda x: x["timestamp"])
        return [cls(**chat) for chat in chats]

    @classmethod
    def send_message(cls, sender, receiver, message):
        timestamp = bruh.now()
        new_message = cls(sender, receiver, timestamp, message)
        new_message.save_to_mongo()
        return new_message.json()

    @classmethod
    def get_users(self):
        users = []
        for i in db.messagesdb.find():
            if i['sender'] == current_user.username:
                if i['receiver'] not in users:
                    users.append(i['receiver'])
                else:
                    pass
            elif i['receiver'] == current_user.username:
                if i['sender'] not in users:
                    users.append(i['sender'])
                else:
                    pass
        return users

    def save_to_mongo(self):
        db.messagesdb.insert_one(self.json())


class Post:
    def __init__(self, username, title, content, timestamp, user_id, _id=None):
        self.title = title
        self.content = content
        self.user_id = user_id
        self.username = username
        self.timestamp = timestamp
        self._id = uuid.uuid4().hex if _id is None else _id

    def json(self):
        return {
            "title": self.title,
            "content": self.content,
            "user_id": self.user_id,
            "_id": self._id,
            "timestamp": self.timestamp,
            "username": self.username
        }

    @classmethod
    def get_by_id(cls, _id):
        data = db.postdb.find_one({"_id": _id})
        if data is not None:
            return cls(**data)

    @classmethod
    def get_by_user_id(cls, user_id):
        data = db.postdb.find({"user_id": user_id})
        if data is not None:
            return cls(**data)

    def save_to_mongo(self):
        db.postdb.insert_one(self.json())


@login.user_loader
def load_user(user_id):
    return User.get_by_id(user_id)


# render latest posts
@appx.route('/')
@appx.route('/home')
def home():
    posts = db.postdb.find().sort("timestamp", DESCENDING).limit(10)
    return render_template('home.html', posts=posts)


@appx.route("/register", methods=['GET', 'POST'])
def register():
    form = CreateUserForm()
    if form.validate_on_submit():
        if request.method == 'POST':
            username = request.form["username"]
            email = request.form["email"]
            # invcode = request.form["invcode"]
            invcode = "idk123"
            password = generate_password_hash(request.form["password"])  # .decode('utf-8')
            find_user = User.get_by_email(email)
            if find_user is None:
                User.register(username, email, password, invcode)
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
                current_user.is_authenticated = True
                flash(f'You are now logged in as {form.username.data}!', 'success')
                return redirect('/me')

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
        "name": "Thought",
        "version": "1.0"
    }
    return str(uhh)


@appx.route("/api/register", methods=['GET', 'POST'])
def registerapi():
    x = request.args
    username = x.get("username")
    email = x.get("email")
    invcode = x.get("invcode")
    password = generate_password_hash(x.get("password"))  # .decode('utf-8')
    find_user = User.get_by_email(email)
    if find_user is None:
        User.register(username, email, password, invcode)
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


@appx.route("/<username>")
@login_required
def user(username):
    if username == "me":
        avatar = User.avatar(current_user.username)
        posts = db.postdb.find({"user_id": current_user._id})
        return render_template('user.html', user=current_user, posts=posts, avatar=avatar)
    else:
        avatar = User.avatar(username)
        user = User.get_by_username(username)
        aboutme = User.get_aboutme(username)
        if user is None:
            posts = []
            return redirect('/error/user')
        else:
            posts = db.postdb.find({"user_id": user._id})
    return render_template('user.html', avatar=avatar, user=user, posts=posts, aboutme=aboutme)


@appx.route("/createnewpost", methods=['GET', 'POST'])
@login_required
def createnewpost2():
    form = PostForm()
    if form.validate_on_submit():
        if request.method == 'POST':
            title = request.form["title"]
            content = request.form["content"]
            user_id = current_user._id
            new_post = Post(current_user.username, title, content, bruh.now().strftime('%Y-%m-%d %H:%M:%S')
                            , user_id)
            new_post.save_to_mongo()
            flash(f'Your post has been created!', 'success')
            return redirect('/me')
    return render_template('create_post.html', title='New Post', form=form)


@appx.route("/deletepost", methods=['GET', 'POST'])
@login_required
def deletepost():
    x = request.args
    post_id = x.get("post_id")
    db.postdb.delete_one({"_id": post_id, "username": current_user.username})
    return redirect('/me')


@appx.route('/deletemsg')
@login_required
def deletemsg():
    x = request.args
    msg_id = x.get("msg_id")
    db.messagesdb.delete_one({"_id": msg_id})
    return "OK"


@appx.route("/set/aboutme", methods=['GET', 'POST'])
@login_required
def setaboutme():
    return redirect('/settings')


@appx.route("/settings", methods=['GET', 'POST'])
@login_required
def settings():
    form = AboutMeForm()
    form.content.data = User.get_aboutme(current_user.username)
    form.email.data = current_user.email
    form.content.data = User.get_aboutme(current_user.username)
    if form.validate_on_submit():
        if request.method == 'POST':
            aboutme = request.form["content"]
            email = request.form["email"]
            User.addaboutme(current_user.username, aboutme)
            x = User.change_email(current_user.username, email)
            if x == False:
                flash(f'Email already exists!', 'danger')
            flash(f'Your changes have been saved', 'success')
            return redirect('/me')
    return render_template('settings.html', title='Set About Me', form=form)


@appx.errorhandler(404)
def page_not_found(e):
    return render_template('404.html')


@appx.route('/mes/<username>')
def mes(username):
    chat = Messages.get_chat(current_user.username, username)
    return render_template('mes.html', messages=chat)


@appx.route("/message/<username>", methods=['GET', 'POST'])
@login_required
def message(username):
    hmm = MessageForm()
    if hmm.validate_on_submit():
        if request.method == 'POST':
            message = request.form["message"]
            h = '/sendmessage' + '?username=' + username + '&message=' + message
            return redirect(h)
    return render_template('messages.html', username=username, form=hmm)


@appx.route("/sendmessage", methods=['GET', 'POST'])
@login_required
def sendmessage():
    x = request.args
    username = x.get("username")
    message = x.get("message")
    Messages.send_message(current_user.username, username, message)
    return redirect('/message/' + username)


@appx.route("/messaging/dashboard", methods=['GET', 'POST'])
@login_required
def messagingdashboard():
    # get all users that the current user has messaged
    # then show them in a list
    # then show the messages between the two
    c = Messages.get_users()
    return render_template('wuff.html', users=c)


from waitress import serve

serve(appx, host='0.0.0.0', port=os.environ['PORT'])
