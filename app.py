import os
import uuid
from datetime import datetime as bruh
from hashlib import md5
import flask_bootstrap
import markdown
from flask import *
from flask_login import *
from flask_pymongo import *
from werkzeug.security import generate_password_hash, check_password_hash
from forms import *





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


class User(UserMixin):
    def __init__(self, username, email, password, invcode, _id=None, aboutme=None, followers=None, following=None):
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
        try:
            self.followers = db.userdb.find_one({"_id": self._id}).get("following", [])
            self.following = db.userdb.find_one({"_id": self._id}).get("following", [])
        except:
            self.followers = []
            self.following = []
    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return self._id
    def get_followers(self):
        return db.userdb.find_one({"_id": self._id}).get("followers", [])
    def get_following(self):
        return db.userdb.find_one({"_id": self._id}).get("following", [])
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
            "password": self.password,
            "followers": self.followers,
            "following": self.following
        }

    @classmethod
    def avatar(self, username):
        x = db.userdb.find_one({"username": username})
        if x is not None:
            email = x["email"]
            digest = md5(email.lower().encode('utf-8')).hexdigest()
            return 'https://www.gravatar.com/avatar/{}?d=identicon&s={}'.format(
                digest, 128)

    def get_followers_number(self):
        return len(self.get_followers())

    def get_following_number(self):
        return len(self.get_following())

    def add_follower(self, id):
        self.followers.append(id)

    def add_following(self, id):
        self.following.append(id)

    def save_to_mongo(self):
        db.userdb.insert_one(self.json())

    def email(self):
        return self.email

    @classmethod
    def reset_password(cls, email):
        pass


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


    @classmethod
    def get_last_message(cls, user1, user2):
        chats = db.messagesdb.find(
            {"$or": [{"sender": user1, "receiver": user2}, {"sender": user2, "receiver": user1}]})
        # sort using timestamps
        chats = list(chats)
        chats.sort(key=lambda x: x["timestamp"])
        # return the last message and the sender
        return [i for i in chats][-1]

######################################################################################
class Post:
    def __init__(self, username, title, content, timestamp, user_id, _id=None):
        self.title = title
        self.content = content
        self.user_id = user_id
        self.username = username
        self.timestamp = timestamp
        self.likes = 0
        self.r_ = []
        self.dislikes = 0
        self._id = uuid.uuid4().hex if _id is None else _id

    def json(self):
        return {
            "title": self.title,
            "content": self.content,
            "user_id": self.user_id,
            "_id": self._id,
            "timestamp": self.timestamp,
            "username": self.username,
            "likes": self.likes,
            "r_": self.r_,
            "dislikes": self.dislikes
        }

    @classmethod
    def get_by_id(cls, _id):
        data = db.postdb.find_one({"_id": _id})
        if data is not None:
            return cls(**data)

    @classmethod
    def liked(cls,_id,userx):
        data = db.postdb.find_one({"_id": _id})
        if userx in data["r_"]:
            data['r_'].remove(userx)
            p = data['r_']
            db.postdb.update_one({"_id": _id}, {"$set": {"likes": data['likes']-1}})
            db.postdb.update_one({"_id": _id}, {"$set": {"r_": p }})
        else:
            if userx != data['username']:
                data['r_'].append(userx)
                p = data['r_']
                db.postdb.update_one({"_id": _id}, {"$set": {"likes": data['likes']+1}})
                db.postdb.update_one({"_id": _id}, {"$set": {"r_": p }})

    @classmethod
    def disliked(cls,_id,userx):
        data = db.postdb.find_one({"_id": _id})
        if userx in data["r_"]:
            data['r_'].remove(userx)
            p = data['r_']
            db.postdb.update_one({"_id": _id}, {"$set": {"dislikes": data['dislikes']-1}})
            db.postdb.update_one({"_id": _id}, {"$set": {"r_": p}})
        else:
            if userx != data['username']:
                data['r_'].append(userx)
                p = data['r_']
                db.postdb.update_one({"_id": _id}, {"$set": {"dislikes": data['dislikes']+1}})
                db.postdb.update_one({"_id": _id}, {"$set": {"r_": p}})

    @classmethod
    def get_by_user_id(cls, user_id):
        data = db.postdb.find({"user_id": user_id})
        if data is not None:
            return cls(**data)

    def save_to_mongo(self):
        self.content = markdown.markdown(self.content)
        db.postdb.insert_one(self.json())


@login.user_loader
def load_user(user_id):
    return User.get_by_id(user_id)


# render latest posts
@appx.route('/')
@appx.route('/home', methods=['GET', 'POST'])
def home():
    posts = db.postdb.find().sort("timestamp", DESCENDING).limit(10)
    p2 = []
    for i in posts:
        i['content'] = markdown.markdown(i['content'])
        p2.append(i)
    return render_template('home.html', posts=p2)


@appx.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(appx.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@appx.route("/api/messages")
@login_required
def get_messages():
    user2 = request.args.get("with")
    chat = Messages.get_chat(current_user.username, user2)
    return jsonify([m.json() for m in chat])


@appx.route("/api/send_message", methods=["POST"])
@login_required
def api_send_message():
    data = request.get_json()
    receiver = data["username"]
    message = data["message"]
    new_msg = Messages.send_message(current_user.username, receiver, message)
    return jsonify(new_msg)


@appx.route("/<username>")
@login_required
def user(username):
    if username == "me":
        avatar = User.avatar(current_user.username)
        posts = db.postdb.find({"user_id": current_user._id}).sort("timestamp", DESCENDING).limit(10)
        p2 = []
        for i in posts:
            i['content'] = markdown.markdown(i['content'])
            p2.append(i)
        return render_template('user.html', user=current_user, posts=p2, avatar=avatar)
    else:
        avatar = User.avatar(username)
        user = User.get_by_username(username)
        aboutme = User.get_aboutme(username)
        if user is None:
            p2 = []
            return redirect('/404')
        else:
            posts = db.postdb.find({"user_id": user._id}).sort("timestamp", DESCENDING).limit(10)
            p2 = []
            for i in posts:
                i['content'] = markdown.markdown(i['content'])
                p2.append(i)
    return render_template('user.html', avatar=avatar, user=user, posts=p2, aboutme=aboutme)


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
    next = request.args.get('next')
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
                return redirect(next or url_for('home'))
            else:
                flash(f'Invalid login!', 'danger')
    return render_template('login.html', title='Login', form=form)


@appx.route('/api/about')
def api_about():
    uhh = {
        "name": "ThoughtAPI",
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


@appx.route("/createnewpost", methods=['GET', 'POST'])
@login_required
def createnewpost2():
    form = PostForm()
    if form.validate_on_submit():
        if request.method == 'POST':
            title = request.form["title"]
            content = request.form["content"]
            user_id = current_user._id
            new_post = Post(current_user.username, title, content, bruh.now().strftime('%H:%M:%S %Y-%m-%d ')
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

@appx.route("/like", methods=['GET', 'POST'])
@login_required
def like():
    x = request.args
    post_id = x.get("post_id")
    Post.liked(_id=post_id,userx=current_user.username) #fix it later
    return redirect(url_for('home')) # this also

@appx.route("/dislike", methods=['GET', 'POST'])
@login_required
def dislike():
    x = request.args
    post_id = x.get("post_id")
    Post.disliked(_id=post_id,userx=current_user.username) #fix it later
    return redirect(url_for('home')) # this also

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
    return render_template('errors/404.html')


@appx.route('/404')
def x404():
    return render_template('errors/404.html')


@appx.route('/logout', methods=['GET', 'POST'])
def logout():
    logout_user()
    return redirect('/')


@appx.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    form = ResetPasswordForm()
    if form.validate_on_submit():
        if request.method == 'POST':
            email = request.form["email"]
            User.reset_password(email)
            flash(f'Your password has been reset!', 'success')
            return redirect('/')
    return render_template('reset_password.html', title='Reset Password', form=form)


@appx.route("/messaging/dashboard", methods=['GET', 'POST'])
@login_required
def messagingdashboard():
    k = []
    c = Messages.get_users()
    for i in c:
        p = Messages.get_last_message(current_user.username, i)
        k.append([p, i])
    if len(k) == 0:
        k = None
    return render_template('mdashboard.html', k=k)


@appx.route('/deletemsg')
@login_required
def deletemsg():
    x = request.args
    msg_id = x.get("msg_id")
    red = x.get("redirect")
    db.messagesdb.delete_one({"_id": msg_id})
    red = "/mes/" + red
    return redirect(red)



@appx.route("/message/<username>", methods=['GET', 'POST'])
@login_required
def message(username):
    hmm = MessageForm()
    if hmm.validate_on_submit():
        if request.method == 'POST':
            message = request.form["message"]
            h = '/sendmessage' + '?username=' + username + '&message=' + message
            return redirect(h)
    return render_template('message-page.html', username=username, form=hmm)

@appx.route("/follow/<username>", methods=["GET", "POST"])
@login_required
def toggle_follow(username):
    if username == current_user.username:
        flash("You cannot follow yourself!", "warning")
        return redirect(url_for("user", username=username))

    # Check if target user exists
    target = db.userdb.find_one({"username": username})
    if not target:
        flash("User not found!", "danger")
        return redirect("/404")

    # Check if current user is already a follower (using DB directly)
    is_following = db.userdb.find_one({
        "username": username,
        "followers": current_user.username
    })

    if is_following:
        # Unfollow
        db.userdb.update_one(
            {"username": username},
            {"$pull": {"followers": current_user.username}}
        )
        db.userdb.update_one(
            {"username": current_user.username},
            {"$pull": {"following": username}}
        )
        flash(f"You unfollowed {username}", "info")
    else:
        # Follow
        db.userdb.update_one(
            {"username": username},
            {"$addToSet": {"followers": current_user.username}}
        )
        db.userdb.update_one(
            {"username": current_user.username},
            {"$addToSet": {"following": username}}
        )
        flash(f"You are now following {username}", "success")

    return redirect(url_for("user", username=username))


from waitress import serve
print("Starting Thought at")
print("http://0.0.0.0:8080 on "+str(bruh.now().time()))
serve(appx, host='0.0.0.0', port=os.environ['PORT'])
