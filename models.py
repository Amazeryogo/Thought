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
    def __init__(self, username=None, email=None, password=None, invcode=None, _id=None, aboutme=None, followers=None, following=None, last_seen=None, git_token=None, **kwargs):
        self.username = username or kwargs.get('username')
        self.email = email or kwargs.get('email')
        self.password = password or kwargs.get('password')
        self.invcode = invcode or kwargs.get('invcode')
        self._id = _id or uuid.uuid4().hex
        self.aboutme = aboutme or "New to Thought"
        self.git_token = git_token or uuid.uuid4().hex
        self.last_seen = last_seen

        # Load from DB to ensure arrays are present, or use kwargs
        self.followers = followers or kwargs.get('followers') or []
        self.following = following or kwargs.get('following') or []
        self.follow_requests = kwargs.get('follow_requests', [])
        self.blocked_users = kwargs.get('blocked_users', [])
        self.is_private = kwargs.get('is_private', False)
        self.is_admin = kwargs.get('is_admin', False)
        self.is_banned = kwargs.get('is_banned', False)
        self.last_data_export = kwargs.get('last_data_export')
        self.bookmarks = kwargs.get('bookmarks', [])

        # Store other extra kwargs
        for k, v in kwargs.items():
            if not hasattr(self, k):
                setattr(self, k, v)
    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return self._id
    def get_followers(self):
        user_data = db.userdb.find_one({"_id": self._id})
        return user_data.get("followers", []) if user_data else []
    def get_following(self):
        user_data = db.userdb.find_one({"_id": self._id})
        return user_data.get("following", []) if user_data else []
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
            "follow_requests": self.follow_requests,
            "blocked_users": self.blocked_users,
            "is_private": self.is_private,
            "is_admin": self.is_admin,
            "is_banned": self.is_banned,
            "last_seen": self.last_seen,
            "git_token": self.git_token,
            "last_data_export": self.last_data_export,
            "bookmarks": self.bookmarks
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

class Group:
    def __init__(self, name=None, description=None, owner_id=None, members=None, mods=None, join_requests=None, timestamp=None, _id=None, **kwargs):
        self._id = _id or kwargs.get('_id') or uuid.uuid4().hex
        self.name = name or kwargs.get('name')
        self.description = description or kwargs.get('description')
        self.owner_id = owner_id or kwargs.get('owner_id')
        self.members = members or kwargs.get('members') or ([self.owner_id] if self.owner_id else [])
        self.mods = mods or kwargs.get('mods') or []
        self.join_requests = join_requests or kwargs.get('join_requests') or []
        self.timestamp = timestamp or kwargs.get('timestamp') or bruh.now()

    def json(self):
        return {
            "_id": self._id,
            "name": self.name,
            "description": self.description,
            "owner_id": self.owner_id,
            "members": self.members,
            "mods": self.mods,
            "join_requests": self.join_requests,
            "timestamp": self.timestamp
        }

    def save_to_db(self):
        db.groupsdb.insert_one(self.json())

    @classmethod
    def get_by_id(cls, _id):
        data = db.groupsdb.find_one({"_id": _id})
        return cls(**data) if data else None

class Notification:
    def __init__(self, user_id, type, sender_id, post_id=None, comment_id=None, timestamp=None, read=False, _id=None, **kwargs):
        self._id = uuid.uuid4().hex if _id is None else _id
        self.user_id = user_id
        self.type = type # 'like', 'comment', 'follow', 'mention'
        self.sender_id = sender_id
        self.post_id = post_id
        self.comment_id = comment_id
        self.timestamp = bruh.now() if timestamp is None else timestamp
        self.read = read

    def json(self):
        return {
            "_id": self._id,
            "user_id": self.user_id,
            "type": self.type,
            "sender_id": self.sender_id,
            "post_id": self.post_id,
            "comment_id": self.comment_id,
            "timestamp": self.timestamp,
            "read": self.read
        }

    def save_to_db(self):
        db.notificationsdb.insert_one(self.json())

    @classmethod
    def create(cls, user_id, type, sender_id, post_id=None, comment_id=None):
        if user_id == sender_id: return # Don't notify self
        notif = cls(user_id, type, sender_id, post_id, comment_id)
        notif.save_to_db()
        return notif

    @classmethod
    def find_by_user(cls, user_id, limit=20):
        data = db.notificationsdb.find({"user_id": user_id}).sort("timestamp", -1).limit(limit)
        return [cls(**d) for d in data]

    @classmethod
    def mark_all_read(cls, user_id):
        db.notificationsdb.update_many({"user_id": user_id, "read": False}, {"$set": {"read": True}})
class Messages:
    def __init__(self, sender=None, receiver=None, timestamp=None, message=None, _id=None, reactions=None, media=None, read=False, **kwargs):
        self.sender = sender or kwargs.get('sender')
        self.receiver = receiver or kwargs.get('receiver')
        self.timestamp = timestamp or kwargs.get('timestamp')
        self.message = message or kwargs.get('message')
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
    def __init__(self, title=None, content=None, timestamp=None, user_id=None, username=None, _id=None,likes=0,dislikes=0,liked_by=None,disliked_by=None,images=None, **kwargs):
        self.title = title or kwargs.get('title')
        self.content = content or kwargs.get('content')
        self.user_id = user_id or kwargs.get('user_id')
        self.username = username or get_username(user_id)
        self.timestamp = timestamp
        self.likes = likes
        self.liked_by = liked_by if liked_by is not None else []
        self.dislikes = dislikes
        self.disliked_by = disliked_by if disliked_by is not None else []
        self._id = _id or uuid.uuid4().hex
        self.images = images if images is not None else []

        self.visibility = kwargs.get('visibility', 'public')
        self.poll = kwargs.get('poll')
        self.is_draft = kwargs.get('is_draft', False)
        self.edit_history = kwargs.get('edit_history', [])
        self.reactions = kwargs.get('reactions', {})
        self.views = kwargs.get('views', 0)

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
            "images": self.images,
            "visibility": self.visibility,
            "poll": self.poll,
            "is_draft": self.is_draft,
            "edit_history": self.edit_history,
            "reactions": self.reactions,
            "views": self.views
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
    def __init__(self, username=None, post_id=None, user_id=None, content=None, parent_comment_id=None, _id=None, timestamp=None,
                 likes=None, liked_by=None, **kwargs):
        self.post_id = post_id or kwargs.get('post_id')
        self.user_id = user_id or kwargs.get('user_id')
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
    def __init__(self, name=None, owner=None, description=None, _id=None, timestamp=None, **kwargs):
        self.name = name or kwargs.get('name')
        self.owner = owner or kwargs.get('owner')
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
