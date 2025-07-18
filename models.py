from core import *
from werkzeug.security import check_password_hash
import markdown
from hashlib import md5
import uuid
from datetime import datetime as bruh

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
    def avatar(cls, username):
        return f'/avatar/{username}'
        '''
        user = db.userdb.find_one({"username": username})
        email = user.get("email", "").strip().lower() if user else ""
        email_hash = md5(email.encode()).hexdigest()
        return f"https://www.gravatar.com/avatar/{email_hash}?d=identicon"
        '''

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
        self.s_av = User.avatar(sender)

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
        chats = list(chats)
        chats.sort(key=lambda x: x["timestamp"])
        return [i for i in chats][-1]



class Post:
    def __init__(self, username, title, content, timestamp, user_id, _id=None,likes=0,dislikes=0,liked_by=[],disliked_by=[]):
        self.title = title
        self.content = content
        self.user_id = user_id
        self.username = username
        self.timestamp = timestamp
        self.likes = likes
        self.liked_by = liked_by
        self.dislikes = dislikes
        self.disliked_by = disliked_by
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
            "dislikes": self.dislikes,
            "liked_by": self.liked_by,
            "disliked_by": self.disliked_by,
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

    def save_to_mongo(self):
        self.content = markdown.markdown(self.content)
        db.postdb.insert_one(self.json())


class Comment:
    def __init__(self, post_id, user_id, username, content, parent_comment_id=None, _id=None, timestamp=None,
                 likes=None, liked_by=None):
        self.post_id = post_id
        self.user_id = user_id
        self.username = username
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

    def save_to_mongo(self):
        db.commentdb.insert_one(self.json())

    @classmethod
    def create(cls, post_id, user_id, username, content, parent_comment_id=None):
        new_comment = cls(
            post_id=post_id,
            user_id=user_id,
            username=username,
            content=content,
            parent_comment_id=parent_comment_id
        )
        new_comment.save_to_mongo()
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
