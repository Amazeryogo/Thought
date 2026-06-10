from core import *
from werkzeug.security import check_password_hash
import markdown
from itsdangerous import URLSafeTimedSerializer as Serializer
from flask_mail import Message as FlaskMessage
from core import app, mail
import uuid
import re
from datetime import datetime as bruh

class User(UserMixin):
    def __init__(self, username, email, password, invcode, _id=None, aboutme=None, followers=None, following=None, last_seen=None, git_token=None):
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
        self.git_token = git_token if git_token is not None else uuid.uuid4().hex
        self.posts = db.postdb.find({"user_id": self._id})
        self.last_seen = last_seen
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
        data = db.userdb.find_one({"username": re.compile(f"^{re.escape(username)}$", re.I)})
        if data is not None:
            user = cls(**data)
            if "git_token" not in data:
                db.userdb.update_one({"_id": user._id}, {"$set": {"git_token": user.git_token}})
            return user
    @classmethod
    def change_username(cls,_id,username):
        db.userdb.update_one({"_id": _id}, {"$set": {"username": username}})
    def last_live(self):
        if not self.last_seen:
            return "Never"

        ls = self.last_seen
        if isinstance(ls, str):
            try: ls = bruh.strptime(ls, '%H:%M:%S %Y-%m-%d')
            except: return ls

        now = bruh.utcnow()
        # Handle naive vs aware datetime if necessary, though project seems naive
        if ls.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=ls.tzinfo)
        elif ls.tzinfo is None and now.tzinfo is not None:
            now = now.replace(tzinfo=None)

        diff = now - ls
        seconds = diff.total_seconds()

        if seconds < 60:
            return "Online"
        elif seconds < 3600:
            return f"Last seen {int(seconds // 60)}m ago"
        elif seconds < 86400:
            return f"Last seen {int(seconds // 3600)}h ago"
        else:
            return f"Last seen {int(seconds // 86400)}d ago"

    @classmethod
    def addaboutme(cls, _id, aboutme):
        db.userdb.update_one({"_id": _id}, {"$set": {"aboutme": aboutme}})

    @classmethod
    def get_aboutme(cls, _id):
        data = db.userdb.find_one({"_id": _id})
        if data is not None:
            return data["aboutme"]
        else:
            return "No About Me"

    @classmethod
    def get_by_email(cls, email):
        data = db.userdb.find_one({"email": re.compile(f"^{re.escape(email)}$", re.I)})
        if data is not None:
            return cls(**data)

    @classmethod
    def get_by_id(cls, _id):
        data = db.userdb.find_one({"_id": _id})
        if data is not None:
            user = cls(**data)
            if "git_token" not in data:
                db.userdb.update_one({"_id": user._id}, {"$set": {"git_token": user.git_token}})
            return user

    @classmethod
    def change_email(cls, _id, email):
        existing_user = db.userdb.find_one({"email": email})
        if existing_user is None:
            db.userdb.update_one({"_id": _id}, {"$set": {"email": email}})
            return True
        else:
            return False
    @classmethod
    def get_email(cls, _id):
        return db.userdb.find_one({"_id": _id})["email"]
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
            new_user = User(username, email, password, invcode, last_seen=bruh.now())
            new_user.save_to_db()
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
            "following": self.following,
            "last_seen": self.last_seen,
            "git_token": self.git_token
        }

    @classmethod
    def avatar(cls, _id):
        return f'/avatar/{_id}'

    def get_followers_number(self):
        return len(self.get_followers())

    def get_following_number(self):
        return len(self.get_following())

    def add_follower(self, id):
        self.followers.append(id)

    def add_following(self, id):
        self.following.append(id)

    def save_to_db(self):
        db.userdb.insert_one(self.json())

    def email(self):
        return self.email

    def get_reset_token(self, expires_sec=1800):
        s = Serializer(app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.get_id()})

    @staticmethod
    def verify_reset_token(token):
        s = Serializer(app.config['SECRET_KEY'])
        try:
            user_id = s.loads(token)['user_id']
        except:
            return None
        return User.get_by_id(user_id)

    @classmethod
    def reset_password(cls, email):
        user = cls.get_by_email(email)
        if user:
            token = user.get_reset_token()
            msg = FlaskMessage('Password Reset Request',
                              sender='noreply@demo.com',
                              recipients=[user.email])
            msg.body = f'''To reset your password, visit the following link:
{url_for('reset_token', token=token, _external=True)}
If you did not make this request then simply ignore this email and no changes will be made.
'''
            mail.send(msg)
def get_idd(username):
    user = db.userdb.find_one({"username": re.compile(f"^{re.escape(username)}$", re.I)})
    return user['_id'] if user else None
def get_username(_id):
    user = db.userdb.find_one({"_id": _id})
    return user['username'] if user else "Unknown"
class Messages:
    def __init__(self, sender, receiver, timestamp, message, _id=None, reactions=None, media=None, read=False):
        self.sender = sender
        self.receiver = receiver
        self.timestamp = timestamp
        self.message = message
        self._id = uuid.uuid4().hex if _id is None else _id
        self.s_av = User.avatar(sender)
        self.reactions = reactions if reactions is not None else {}
        self.media = media
        self.read = read

    def json(self):
        if isinstance(self.timestamp, str):
            formatted_timestamp = self.timestamp # It's already a string
        else:
            formatted_timestamp = self.timestamp.strftime("%I:%M %p - %b %d, %Y")
        return {
            "sender": self.sender,
            "receiver": self.receiver,
            "message": self.message,
            "timestamp": formatted_timestamp,
            "_id": self._id,
            "reactions": self.reactions,
            "media": self.media,
            "read": self.read
        }

    @classmethod
    def get_chat(cls, user1, user2, before=None, limit=20):
        query = {"$or": [{"sender": user1, "receiver": user2}, {"sender": user2, "receiver": user1}]}
        if before:
            before_message = db.messagesdb.find_one({"_id": before})
            if before_message:
                query["timestamp"] = {"$lt": before_message["timestamp"]}

        chats = db.messagesdb.find(query).sort("timestamp", -1).limit(limit)
        chats = list(chats)
        chats.reverse()
        return [cls(**chat) for chat in chats]

    @classmethod
    def send_message(cls, sender, receiver, message, media=None):
        timestamp = bruh.now()
        new_message = cls(sender=sender, receiver=receiver, timestamp=timestamp, message=message, media=media)
        new_message.save_to_db()
        return new_message.json()

    @classmethod
    def mark_as_read(cls, sender, receiver):
        db.messagesdb.update_many(
            {"sender": sender, "receiver": receiver, "read": False},
            {"$set": {"read": True}}
        )

    @classmethod
    def get_conversations(cls, _id):
        # Optimized to get conversations with last message and unread count
        pipeline = [
            {"$match": {"$or": [{"sender": _id}, {"receiver": _id}]}},
            {"$sort": {"timestamp": -1}},
            {"$group": {
                "_id": {
                    "$cond": [
                        {"$eq": ["$sender", _id]},
                        "$receiver",
                        "$sender"
                    ]
                },
                "last_message": {"$first": "$$ROOT"},
                "unread_count": {
                    "$sum": {
                        "$cond": [
                            {"$and": [{"$eq": ["$receiver", _id]}, {"$eq": ["$read", False]}]},
                            1,
                            0
                        ]
                    }
                }
            }},
            {"$sort": {"last_message.timestamp": -1}}
        ]
        return list(db.messagesdb.aggregate(pipeline))

    @classmethod
    def get_users(self):
        # Keeping for backward compatibility if needed, but get_conversations is better
        users = []
        for i in db.messagesdb.find({"$or": [{"sender": current_user._id}, {"receiver": current_user._id}]}):
            other = i['receiver'] if i['sender'] == current_user._id else i['sender']
            if other not in users:
                users.append(other)
        return users

    def save_to_db(self):
        db.messagesdb.insert_one({
            "sender": self.sender,
            "receiver": self.receiver,
            "message": self.message,
            "timestamp": self.timestamp,
            "_id": self._id,
            "reactions": self.reactions,
            "media": self.media,
            "read": self.read
        })

    @classmethod
    def get_last_message(cls, user1, user2):
        chat = db.messagesdb.find_one(
            {"$or": [{"sender": user1, "receiver": user2}, {"sender": user2, "receiver": user1}]},
            sort=[("timestamp", -1)]
        )
        return chat



class Post:
    def __init__(self, title, content, timestamp, user_id, username=None, _id=None,likes=0,dislikes=0,liked_by=None,disliked_by=None,images=None):
        self.title = title
        self.content = content
        self.user_id = user_id
        self.username = get_username(user_id)
        self.timestamp = timestamp
        self.likes = likes
        self.liked_by = liked_by if liked_by is not None else []
        self.dislikes = dislikes
        self.disliked_by = disliked_by if disliked_by is not None else []
        self._id = uuid.uuid4().hex if _id is None else _id
        self.images = images if images is not None else []

    def json(self):
        return {
            "title": self.title,
            "content": self.content,
            "user_id": self.user_id,
            "_id": self._id,
            "timestamp": self.timestamp,
            "username": self.username,
            "likes": self.likes,
            "dislikes": self.dislikes,
            "liked_by": self.liked_by,
            "disliked_by": self.disliked_by,
            "images": self.images
        }

    @classmethod
    def get_by_id(cls, _id):
        data = db.postdb.find_one({"_id": _id})
        if data is not None:
            return cls(**data)

    @classmethod
    def liked(cls, _id, userx):
        data = db.postdb.find_one({"_id": _id})
        if not data or userx == data['username']:
            return
        liked_by = set(data.get("liked_by", []))
        disliked_by = set(data.get("disliked_by", []))
        if userx in liked_by:
            liked_by.remove(userx)
        else:
            liked_by.add(userx)
            disliked_by.discard(userx)  # can't both like and dislike
        db.postdb.update_one(
            {"_id": _id},
            {
                "$set": {
                    "liked_by": list(liked_by),
                    "disliked_by": list(disliked_by),
                    "likes": len(liked_by),
                    "dislikes": len(disliked_by)
                }
            }
        )

    @classmethod
    def disliked(cls, _id, userx):
        data = db.postdb.find_one({"_id": _id})
        if not data or userx == data['username']:
            return
        liked_by = set(data.get("liked_by", []))
        disliked_by = set(data.get("disliked_by", []))
        if userx in disliked_by:
            disliked_by.remove(userx)
        else:
            disliked_by.add(userx)
            liked_by.discard(userx)
        db.postdb.update_one(
            {"_id": _id},
            {
                "$set": {
                    "liked_by": list(liked_by),
                    "disliked_by": list(disliked_by),
                    "likes": len(liked_by),
                    "dislikes": len(disliked_by)
                }
            }
        )

    @classmethod
    def get_by_user_id(cls, user_id):
        data = db.postdb.find({"user_id": user_id})
        if data is not None:
            return cls(**data)

    def save_to_db(self):
        self.content = markdown.markdown(self.content)
        db.postdb.insert_one(self.json())


class Comment:
    def __init__(self, username, post_id, user_id, content, parent_comment_id=None, _id=None, timestamp=None,
                 likes=None, liked_by=None):
        self.post_id = post_id
        self.user_id = user_id
        self.username = get_username(user_id)
        self.content = content
        self.parent_comment_id = parent_comment_id

        self._id = uuid.uuid4().hex if _id is None else _id
        self.timestamp = bruh.now() if timestamp is None else timestamp
        self.likes = 0 if likes is None else likes
        self.liked_by = [] if liked_by is None else liked_by

    def json(self):
        return {
            "_id": self._id,
            "post_id": self.post_id,
            "user_id": self.user_id,
            "username": self.username,
            "content": self.content,
            "parent_comment_id": self.parent_comment_id,
            "timestamp": self.timestamp,
            "likes": self.likes,
            "liked_by": self.liked_by
        }

    def save_to_db(self):
        db.commentdb.insert_one(self.json())

    @classmethod
    def create(cls, post_id, user_id, content, parent_comment_id=None):
        new_comment = cls(
            username=get_username(user_id),
            post_id=post_id,
            user_id=user_id,
            content=content,
            parent_comment_id=parent_comment_id
        )
        new_comment.save_to_db()
        return new_comment

    @classmethod
    def get_by_id(cls, _id):
        data = db.commentdb.find_one({"_id": _id})
        if data:
            return cls(**data)
        return None

    @classmethod
    def find_by_post_id(cls, post_id):
        comments_data = db.commentdb.find({"post_id": post_id}).sort("timestamp", 1)
        return [cls(**data) for data in comments_data]

    @classmethod
    def like(cls, _id, username):
        comment = db.commentdb.find_one({"_id": _id})
        if not comment or username == comment.get('username'):
            return

        liked_by = set(comment.get("liked_by", []))

        if username in liked_by:
            liked_by.remove(username)
        else:
            liked_by.add(username)

        db.commentdb.update_one(
            {"_id": _id},
            {
                "$set": {
                    "liked_by": list(liked_by),
                    "likes": len(liked_by)
                }
            }
        )
    @property
    def replies(self):
        reply_data = db.commentdb.find({
            "parent_comment_id": self._id
        }).sort("timestamp", 1)
        return [Comment(**data) for data in reply_data]


class Repository:
    def __init__(self, name, owner, description=None, _id=None, timestamp=None):
        self.name = name
        self.owner = owner
        self.description = description if description else "No description"
        self._id = uuid.uuid4().hex if _id is None else _id
        self.timestamp = bruh.now() if timestamp is None else timestamp

    def json(self):
        return {
            "_id": self._id,
            "name": self.name,
            "owner": self.owner,
            "description": self.description,
            "timestamp": self.timestamp
        }

    def save_to_db(self):
        db.reposdb.insert_one(self.json())

    @classmethod
    def get_by_id(cls, _id):
        data = db.reposdb.find_one({"_id": _id})
        if data:
            return cls(**data)
        return None

    @classmethod
    def get_by_owner_and_name(cls, owner, name):
        data = db.reposdb.find_one({
            "owner": re.compile(f"^{re.escape(owner)}$", re.I),
            "name": re.compile(f"^{re.escape(name)}$", re.I)
        })
        if data:
            return cls(**data)
        return None

    @classmethod
    def find_by_owner(cls, owner):
        repos_data = db.reposdb.find({"owner": re.compile(f"^{re.escape(owner)}$", re.I)}).sort("timestamp", -1)
        return [cls(**data) for data in repos_data]
