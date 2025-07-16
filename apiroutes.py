from routes import *
import jwt
from datetime import datetime, timedelta
from functools import wraps

'''
JWT_SECRET = os.environ.get("JWT_SECRET", SECRET_KEY)
JWT_ALGORITHM = "HS256"
JWT_EXP_DELTA_SECONDS = 3600


def generate_jwt(user_id):
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(seconds=JWT_EXP_DELTA_SECONDS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

# Helper: Decorator to protect API routes
def jwt_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        if not token:
            return jsonify({"message": "Missing token"}), 401
        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user = User.get_by_id(data["user_id"])
            if not user:
                raise Exception("User not found")
            g.current_user = user
        except Exception as e:
            return jsonify({"message": "Invalid or expired token", "error": str(e)}), 401
        return f(*args, **kwargs)
    return decorated_function

@appx.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    user = User.get_by_username(username)
    if user and User.login_valid(username, password):
        token = generate_jwt(user.get_id())
        return jsonify({"success": True, "token": token, "username": username})
    return jsonify({"success": False, "message": "Invalid credentials"}), 401

@appx.route('/api/me', methods=['GET'])
@jwt_required
def get_me():
    user = g.current_user
    return jsonify({
        "username": user.username,
        "email": user.email,
        "aboutme": user.aboutme,
        "avatar": User.avatar(user.username)
    })

@appx.route('/api/user/<username>', methods=['GET'])
@jwt_required
def get_user_profile(username):
    user = User.get_by_username(username)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({
        "username": user.username,
        "email": user.email,
        "aboutme": user.aboutme,
        "followers": user.get_followers(),
        "following": user.get_following(),
        "avatar": User.avatar(user.username)
    })

@appx.route('/api/user/<username>/follow', methods=['POST'])
@jwt_required
def api_toggle_follow(username):
    if username == g.current_user.username:
        return jsonify({"success": False, "message": "You cannot follow yourself!"}), 400

    target = db.userdb.find_one({"username": username})
    if not target:
        return jsonify({"success": False, "message": "User not found!"}), 404

    is_following = db.userdb.find_one({
        "username": username,
        "followers": g.current_user.username
    })

    if is_following:
        db.userdb.update_one({"username": username}, {"$pull": {"followers": g.current_user.username}})
        db.userdb.update_one({"username": g.current_user.username}, {"$pull": {"following": username}})
        action = "unfollowed"
    else:
        db.userdb.update_one({"username": username}, {"$addToSet": {"followers": g.current_user.username}})
        db.userdb.update_one({"username": g.current_user.username}, {"$addToSet": {"following": username}})
        action = "followed"

    updated_user = db.userdb.find_one({"username": username})
    follower_count = len(updated_user.get("followers", []))

    return jsonify({
        "success": True,
        "action": action,
        "is_following": not is_following,
        "follower_count": follower_count
    })

@appx.route('/api/posts', methods=['GET'])
@jwt_required
def get_all_posts():
    posts = db.postdb.find().sort("timestamp", DESCENDING)
    result = []
    for post in posts:
        result.append({
            "_id": post["_id"],
            "username": post["username"],
            "title": post["title"],
            "content": post["content"],
            "timestamp": post["timestamp"],
            "likes": post.get("likes", 0),
            "dislikes": post.get("dislikes", 0)
        })
    return jsonify(result)

@appx.route('/api/post/<post_id>/like', methods=['POST'])
@jwt_required
def api_like_post(post_id):
    Post.liked(_id=post_id, userx=g.current_user.username)
    post = db.postdb.find_one({"_id": post_id})
    return jsonify({
        "success": True,
        "likes": post.get("likes", 0),
        "dislikes": post.get("dislikes", 0)
    })

@appx.route('/api/post/<post_id>/dislike', methods=['POST'])
@jwt_required
def api_dislike_post(post_id):
    Post.disliked(_id=post_id, userx=g.current_user.username)
    post = db.postdb.find_one({"_id": post_id})
    return jsonify({
        "success": True,
        "likes": post.get("likes", 0),
        "dislikes": post.get("dislikes", 0)
    })

@appx.route('/api/messages/<username>', methods=['GET'])
@jwt_required
def get_chat_with_user(username):
    messages = Messages.get_chat(g.current_user.username, username)
    return jsonify([m.json() for m in messages])

@appx.route('/api/message/send', methods=['POST'])
@jwt_required
def send_message():
    data = request.get_json()
    receiver = data.get('receiver')
    message = data.get('message')
    if not receiver or not message:
        return jsonify({"error": "Missing receiver or message"}), 400
    msg = Messages.send_message(g.current_user.username, receiver, message)
    return jsonify(msg)
'''