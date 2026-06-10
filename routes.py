from models import *
from forms import *
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
import re
import time
import subprocess
import shutil
import markdown
from datetime import datetime as dt
from core import app, db, ASCENDING, DESCENDING
from profanity import filter_profanity
from flask import request, jsonify
from hashlib import md5
from functools import wraps
import urllib.request
def rate_limit(limit=500, period=60):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if current_user.is_authenticated:
                key = f"rate_limit:{current_user._id}:{f.__name__}"
                now = time.time()
                try:
                    db.ratelimits.delete_many({"key": key, "timestamp": {"$lt": now - period}})
                    calls = len(list(db.ratelimits.find({"key": key})))
                    if calls >= limit:
                        flash("You are doing that too much. Please wait a moment.", "warning")
                        return redirect(request.referrer or url_for('home'))
                    db.ratelimits.insert_one({"key": key, "timestamp": now})
                except Exception as e:
                    pass # Silently fail rate limiting if DB is down
            return f(*args, **kwargs)
        return wrapped
    return decorator

@app.route('/image/posts/<user_id>/<image_name>')
def image_post(user_id, image_name):
    user_folder = os.path.join(IMAGED, 'users',user_id,'posts')
    os.makedirs(user_folder, exist_ok=True)
    save_path = os.path.join(user_folder, image_name)
    return send_file(save_path, mimetype='image/png')

@app.template_filter('format_timestamp')
def format_timestamp(ts):
    if not ts:
        return ""
    if isinstance(ts, dt):
        return ts.strftime('%b %d, %Y - %H:%M')
    return str(ts)

@app.template_filter('render_post_content')
def render_post_content(post):
    content = ""
    media_files = []
    if isinstance(post, dict):
        content = post.get('content', '')
        media_files = post.get('images', [])
    else: # assuming it's a Post object
        content = post.content
        media_files = post.images

    if media_files:
        i = 0
        for media_url in media_files:
            placeholder = f"[image{i+1}]"
            if media_url.lower().endswith(('.mp4', '.webm')):
                media_tag = f'<video src="{media_url}" class="img-fluid rounded mb-2" controls></video>'
            else:
                media_tag = f'<img src="{media_url}" class="img-fluid rounded mb-2" alt="">'

            if placeholder in content:
                content = content.replace(placeholder, media_tag)
            else:
                # If placeholder not in content, append image to the end
                content += "\n\n" + media_tag
            i += 1

    # Remove any remaining placeholders that don't have a corresponding image
    content = re.sub(r'\[image\d+\]', '', content)

    return markdown.markdown(content)

@login.user_loader
def load_user(user_id):
    return User.get_by_id(user_id)



@app.route('/')
@app.route('/home', methods=['GET', 'POST'])
@login_required
def home():
    # Follow Feed: Show posts from people you follow + your own posts (excluding drafts)
    following = current_user.get_following()
    blocked = current_user.json().get('blocked_users', [])
    feed_users = [f for f in following if f not in blocked] + [current_user._id]

    posts = db.postdb.find({"user_id": {"$in": feed_users}, "is_draft": {"$ne": True}}).sort("timestamp", DESCENDING).limit(20)

    # If feed is too small, supplement with global posts
    p_list = list(posts)
    if len(p_list) < 5:
        global_posts = db.postdb.find({"user_id": {"$nin": feed_users}}).sort("timestamp", DESCENDING).limit(10)
        p_list.extend(list(global_posts))
        # Re-sort combined list
        p_list.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

    p2 = []
    for i in p_list:
        i['content'] = markdown.markdown(i['content'])
        p2.append(i)
    return render_template('home.html', posts=p2)

@app.route('/explore')
@login_required
def explore():
    # Global feed (excluding drafts and blocked users)
    blocked = current_user.json().get('blocked_users', [])
    posts = db.postdb.find({"is_draft": {"$ne": True}, "user_id": {"$nin": blocked}}).sort("timestamp", DESCENDING).limit(20)

    # Simple decay: score = count / (hours_since_last_post + 1)^1.5
    all_hashtags = db.hashtagsdb.find()
    hashtag_scores = []
    now = dt.now()
    for h in all_hashtags:
        last_used = h.get('last_used', now)
        if isinstance(last_used, str): last_used = dt.fromisoformat(last_used)
        hours_old = (now - last_used).total_seconds() / 3600
        score = h.get('count', 0) / ((hours_old + 1) ** 1.5)
        hashtag_scores.append((h, score))

    hashtag_scores.sort(key=lambda x: x[1], reverse=True)
    trending = [x[0] for x in hashtag_scores[:10]]

    # Suggested Users: People you don't follow but your follows follow
    following = current_user.get_following()
    suggested = []
    if following:
        # This is expensive O(N^2) for my simple DB, but okay for moderate size
        potential = []
        for f_id in following:
            f_user = User.get_by_id(f_id)
            if f_user:
                potential.extend(f_user.get_following())

        # Filter: not you, not already following
        potential = [p for p in potential if p != current_user._id and p not in following]
        # Count frequency
        from collections import Counter
        counts = Counter(potential).most_common(5)
        suggested = [User.get_by_id(u_id) for u_id, c in counts if User.get_by_id(u_id)]

    p2 = []
    for i in posts:
        i['content'] = markdown.markdown(i['content'])
        p2.append(i)
    return render_template('explore.html', posts=p2, trending=trending, suggested=suggested)

@app.route('/search')
@login_required
def search():
    q = request.args.get('q', '')
    if not q:
        return render_template('search.html')

    # Search users, posts, hashtags
    users = db.userdb.find({"username": {"$regex": q}})
    posts = db.postdb.find({"$or": [{"title": {"$regex": q}}, {"content": {"$regex": q}}]}).sort("timestamp", DESCENDING)
    hashtags = db.hashtagsdb.find({"name": {"$regex": q}})

    p2 = []
    for i in posts:
        i['content'] = markdown.markdown(i['content'])
        p2.append(i)

    return render_template('search.html', users=users, posts=p2, hashtags=hashtags, q=q)

@app.route('/hashtag/<name>')
@login_required
def hashtag_view(name):
    posts = db.postdb.find({"content": {"$regex": f"#{name}"}}).sort("timestamp", DESCENDING)
    p2 = []
    for i in posts:
        i['content'] = markdown.markdown(i['content'])
        p2.append(i)
    return render_template('home.html', posts=p2, title=f"#{name}")

@app.route("/poll/vote/<post_id>", methods=['POST'])
@login_required
def poll_vote(post_id):
    option_index = request.json.get('option')
    post = db.postdb.find_one({"_id": post_id})
    if not post or 'poll' not in post:
        return jsonify({"success": False, "message": "No poll found"}), 404

    # Check if user already voted
    for opt in post['poll']['options']:
        if current_user._id in opt.get('voters', []):
            return jsonify({"success": False, "message": "Already voted"}), 400

    # Add vote
    db.postdb.update_one(
        {"_id": post_id},
        {"$addToSet": {f"poll.options.{option_index}.voters": current_user._id}}
    )
    # Re-fetch for updated counts
    updated_post = db.postdb.find_one({"_id": post_id})
    return jsonify({"success": True, "poll": updated_post['poll']})

@app.route("/follow_request/<action>/<user_id>", methods=["POST"])
@login_required
def handle_follow_request(action, user_id):
    if action == "accept":
        db.userdb.update_one({"_id": current_user._id}, {"$pull": {"follow_requests": user_id}, "$addToSet": {"followers": user_id}})
        db.userdb.update_one({"_id": user_id}, {"$addToSet": {"following": current_user._id}})
        Notification.create(user_id, 'follow', current_user._id)
        flash("Follow request accepted.", "success")
    else:
        db.userdb.update_one({"_id": current_user._id}, {"$pull": {"follow_requests": user_id}})
        flash("Follow request rejected.", "info")
    return redirect(url_for('notifications'))

@app.route("/api/user/active", methods=["POST"])
@login_required
def user_active():
    db.userdb.update_one(
        {"_id": current_user._id},
        {"$set": {"last_seen": dt.now()}}
    )
    return jsonify({"success": True})


@app.route("/api/user/<username>/status", methods=["GET"])
@login_required
def user_status(username):
    user = User.get_by_username(username)
    if not user:
        return jsonify({"online": False, "last_seen": "Never"}), 404
    if user.last_seen and isinstance(user.last_seen, dt):
        # Compare current UTC time to last_seen
        is_online = (dt.utcnow() - user.last_seen).total_seconds() < 60
        last_seen_str = user.last_seen.strftime("%I:%M %p - %b %d, %Y")
    else:
        is_online = False
        last_seen_str = "Never"
    return jsonify({"online": is_online, "last_seen": last_seen_str})


@app.route("/post/<post_id>", methods=["GET", "POST"])
@login_required
def post_view(post_id):
    post = Post.get_by_id(post_id)
    if not post:
        abort(404)

    form = CommentForm()

    if form.validate_on_submit():
        content = filter_profanity(form.content.data)
        if len(content) in range(COMMENT_MIN,COMMENT_MAX+1):
            comment = Comment.create(
                post_id=post_id,
                user_id=current_user._id,
                content=content
            )
            # Notify post owner
            Notification.create(post.user_id, 'comment', current_user._id, post_id=post_id, comment_id=comment._id)

            # Check for mentions
            mentions = re.findall(r'@(\w+)', content)
            for m in set(mentions):
                target_user = User.get_by_username(m)
                if target_user:
                    Notification.create(target_user._id, 'mention', current_user._id, post_id=post_id, comment_id=comment._id)
            flash("Comment added.", "success")
            return redirect(url_for('post_view', post_id=post_id))
        else:
            if len(form.content.data) >= COMMENT_MAX:
                flash('comment reply too large','warning')
            else:
                flash('message is too small','warning')
    # Fetch comments for this post
    all_comments = Comment.find_by_post_id(post_id)

    # Separate top-level comments and replies
    comments_by_id = {c._id: c for c in all_comments}
    top_comments = []
    for comment in all_comments:
        if comment.parent_comment_id:
            parent = comments_by_id.get(comment.parent_comment_id)
            if parent:
                if not hasattr(parent, "replies"):
                    parent.replies = []
                parent.replies.append(comment)
            else:
                # If the parent doesn't exist (e.g., deleted), treat it as top-level
                top_comments.append(comment)
        else:
            top_comments.append(comment)

    return render_template(
        "post_view.html",
        post=post,
        form=form,
        comments=top_comments,
        User=User
    )

@app.route("/comment/reply/<comment_id>", methods=["POST"])
@login_required
def reply_to_comment(comment_id):
    parent_comment = Comment.get_by_id(comment_id)
    if not parent_comment:
        flash("Comment not found.", "danger")
        return redirect(request.referrer)

    content = request.form.get("reply_content")
    if content:
        content = filter_profanity(content)
        if len(content) in range(COMMENT_MIN,COMMENT_MAX+1):
            comment = Comment.create(
                post_id=parent_comment.post_id,
                user_id=current_user._id,
                content=content,
                parent_comment_id=comment_id
            )
            # Notify parent comment owner
            Notification.create(parent_comment.user_id, 'comment', current_user._id, post_id=parent_comment.post_id, comment_id=comment._id)

            # Check for mentions
            mentions = re.findall(r'@(\w+)', content)
            for m in set(mentions):
                target_user = User.get_by_username(m)
                if target_user:
                    Notification.create(target_user._id, 'mention', current_user._id, post_id=parent_comment.post_id, comment_id=comment._id)
            flash("Reply posted!", "success")
        else:
            if len(content) > COMMENT_MAX:
                flash("comment too large", 'warning')
            else:
                flash("comment too small",'warning')
    return redirect(request.referrer)

@app.route("/comment/delete/<comment_id>", methods=["POST"])
@login_required
def delete_comment(comment_id):
    comment = Comment.get_by_id(comment_id)
    if comment and (comment.user_id == current_user._id or current_user.is_admin):
        db.commentdb.delete_one({"_id": comment_id})
        flash("Comment deleted.", "success")
    else:
        flash("Unauthorized or comment not found.", "danger")
    return redirect(request.referrer)


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

ALLOWED_EXTENSIONS = ("png", "jpg", "jpeg", "gif", "mp4", "webm")


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload_content():
    if request.method == "POST":
        if "media[]" not in request.files:
            flash("No files found", "danger")
            return redirect(request.url)
        files = request.files.getlist("media[]")
        if not files or all(f.filename == "" for f in files):
            flash("No selected files", "warning")
            return redirect(request.url)
        user_folder = os.path.join(IMAGED, 'users', current_user._id,'images')
        os.makedirs(user_folder, exist_ok=True)
        saved_files = []
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                save_path = os.path.join(user_folder, filename)
                file.save(save_path)
                saved_files.append(filename)
        if saved_files:
            flash(f"{len(saved_files)} image(s) uploaded successfully!", "success")
            return redirect("/me")
        else:
            flash("No valid image files uploaded!", "danger")
            return redirect("/me")

    return render_template("forms/upload_content.html")


@app.route("/image/<userid>/<imageuid>", methods=["GET", "POST"])
@login_required
def render_image(userid,imageuid):
    return send_from_directory(IMAGED + '/users/' + userid +'/images', imageuid)

@app.route("/delete_image/<image_name>", methods=["POST"])
@login_required
def delete_image(image_name):
    image_name = secure_filename(image_name)
    image_path = os.path.join(IMAGED, 'users', current_user._id, 'images', image_name)
    if os.path.exists(image_path):
        os.remove(image_path)
        flash(f"Image {image_name} deleted.", "success")
    else:
        flash("Image not found.", "danger")
    return redirect(url_for('user', username='me'))


@app.route("/api/upload/message_image", methods=["POST"])
@login_required
def upload_message_image():
    if 'image' not in request.files:
        return jsonify({"success": False, "error": "No image provided"}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({"success": False, "error": "No image selected"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        user_folder = os.path.join(IMAGED, 'users',current_user._id,"messages")
        os.makedirs(user_folder, exist_ok=True)
        save_path = os.path.join(user_folder, unique_filename)
        file.save(save_path)
        image_url = f"/image/messages/{current_user._id}/{unique_filename}"
        return jsonify({"success": True, "image_url": image_url})

    return jsonify({"success": False, "error": "Invalid file type"}), 400


@app.route("/image/messages/<userid>/<imageuid>", methods=["GET"])
@login_required
def render_message_image(userid, imageuid):
    return send_from_directory(os.path.join(IMAGED,'users',userid, "messages"), imageuid)


@app.route("/<username>")
@login_required
def user(username):
    if username == "me":
        user = current_user
    else:
        user = User.get_by_username(username)
        if user is None:
            return redirect('/404')

    # Check if blocked
    blocked_by_them = current_user._id in user.json().get('blocked_users', [])
    blocked_by_me = user._id in current_user.json().get('blocked_users', [])
    if blocked_by_them or blocked_by_me:
        flash("Profile unavailable.", "danger")
        return redirect(url_for('home'))

    avatar = User.avatar(user.username)
    aboutme = User.get_aboutme(user.username)

    # User Stats
    user_posts = db.postdb.find({"user_id": user._id})
    total_likes = sum(p.get('likes', 0) for p in user_posts)
    stats = {
        "total_posts": len(list(db.postdb.find({"user_id": user._id}))),
        "total_likes": total_likes,
        "member_since": user.json().get('timestamp', 'Unknown')
    }

    # Post visibility logic
    query = {"user_id": user._id}
    if user._id == current_user._id:
        # User viewing their own profile sees everything
        pass
    else:
        query["is_draft"] = {"$ne": True}
    if user._id != current_user._id:
        is_following = current_user._id in user.get_followers()
        if user.json().get('is_private') and not is_following:
            return render_template('user.html', user=user, posts=[], avatar=avatar, aboutme=aboutme, private=True)

        # Filter visibility levels
        visible_levels = ['public']
        if is_following:
            visible_levels.append('followers')
        query['visibility'] = {"$in": visible_levels}

    posts = db.postdb.find(query).sort("timestamp", DESCENDING).limit(10)
    p2 = []
    for post in posts:
        post['content'] = markdown.markdown(post['content'])
        p2.append(post)
    image_dir = os.path.join(IMAGED,'users', user._id, 'images')
    user_images = []
    if os.path.exists(image_dir):
        user_images = [f for f in os.listdir(image_dir) if f.lower().endswith(ALLOWED_EXTENSIONS)]
    video = []
    non_video = []
    for k in user_images:
        if k.lower().endswith(("png", "jpg", "jpeg", "gif")):
            non_video.append(k)
        else:
            video.append(k)
    return render_template(
        'user.html',
        user=user,
        posts=p2,
        avatar=avatar,
        aboutme=aboutme,
        videos = video,
        non_videos = non_video,
        stats = stats
    )

@app.route("/register", methods=['GET', 'POST'])
def register():
    form = CreateUserForm()
    if form.validate_on_submit():
        if request.method == 'POST':
            username = request.form["username"]
            email = request.form["email"]
            invcode = "idk123"
            password = generate_password_hash(request.form["password"])  # .decode('utf-8')
            find_user = User.get_by_email(email)
            if find_user is None:
                if len(username) in range(USERNAME_MIN,USERNAME_MAX+1):
                    if len(request.form["password"]) in range(PASSWORD_MIN,PASSWORD_MAX+1):
                        User.register(username, email, password, invcode)
                        flash(f'Account created for {form.username.data}!', 'success')
                        return redirect(url_for('home'))
                    else:
                        if len(request.form["password"]) > PASSWORD_MAX:
                            flash('password too long','warning')
                        else:
                            flash('password too short','warning')
                else:
                    flash('username does not meet requirements')
            else:
                flash(f'Account already exists for {form.username.data}!', 'success')
    return render_template('forms/register.html', title='Register', form=form)


@app.route("/login", methods=['GET', 'POST'])
def login():
    next = request.args.get('next')
    form = LoginForm()
    if form.validate_on_submit():
        if request.method == 'POST':
            username = request.form["username"]
            password = request.form["password"]
            user = User.get_by_username(username)
            if user and user.json().get('is_banned'):
                flash("Your account has been banned.", "danger")
                return redirect(url_for('login'))

            if user is not None and User.login_valid(username, password):
                login_user(user)
                current_user.is_authenticated = True
                db.userdb.update_one(
                    {"_id": user._id},
                    {"$set": {"last_seen": dt.now()}}
                )
                flash(f'You are now logged in as {form.username.data}!', 'success')
                return redirect(next or url_for('home'))
            else:
                flash(f'Invalid login!', 'danger')
    return render_template('forms/login.html', title='Login', form=form)





@app.route("/upload/post", methods=['GET', 'POST'])
@login_required
@rate_limit(limit=50, period=300) # Limit post creation
def createnewpost():
    form = PostForm()
    # Populate communities
    user_groups = db.groupsdb.find({"members": current_user._id})
    group_choices = [('account', 'My Account')]
    for g in user_groups:
        group_choices.append((g['_id'], f"Group: {g['name']}"))
    form.post_to.choices = group_choices

    p = 0
    if form.validate_on_submit():
        title = form.title.data
        content = form.content.data
        user_id = current_user._id
        timestamp = dt.now().strftime('%H:%M:%S %Y-%m-%d')

        image_urls = []
        if "images" or "Images" in request.files:
            files = request.files.getlist("images")
            for file in files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    unique_filename = f"{uuid.uuid4().hex}_{filename}"
                    user_folder = os.path.join(IMAGED, 'users', current_user._id, "posts")
                    os.makedirs(user_folder, exist_ok=True)
                    save_path = os.path.join(user_folder, unique_filename)
                    file.save(save_path)
                    image_urls.append(f"/image/posts/{current_user._id}/{unique_filename}")
        content = filter_profanity(content)

        if len(content) in range(POST_MIN, POST_MAX+1):
            visibility = form.visibility.data
            is_draft = form.is_draft.data
            post_to = form.post_to.data
            poll_data = None
            if form.is_poll.data and form.poll_options.data:
                # If posting to group, must be owner or mod
                if post_to != 'account':
                    group = Group.get_by_id(post_to)
                    if group.owner_id != current_user._id and current_user._id not in group.mods:
                        flash("Only moderators can create polls in this community.", "danger")
                        return render_template('forms/edit_post.html', form=form, p=p)

                options = [o.strip() for o in form.poll_options.data.split(',')]
                poll_data = {"options": [{"text": o, "voters": []} for o in options]}

            new_post_data = {
                "title": title,
                "content": content,
                "timestamp": timestamp,
                "user_id": user_id,
                "images": image_urls,
                "visibility": visibility,
                "poll": poll_data,
                "is_draft": is_draft,
                "group_id": post_to if post_to != 'account' else None
            }
            try:
                res = db.postdb.insert_one(new_post_data)
                if not res:
                    flash("Failed to save post. Please try again.", "danger")
                    return render_template('forms/edit_post.html', form=form, p=p)
                new_post = Post(**res)
            except Exception as e:
                flash(f"Database error: {e}", "danger")
                return render_template('forms/edit_post.html', form=form, p=p)

            # Parse hashtags
            hashtags = re.findall(r'#(\w+)', content)
            for h in set(hashtags):
                db.hashtagsdb.update_one({"name": h.lower()}, {"$addToSet": {"posts": new_post._id}, "$inc": {"count": 1}}, upsert=True)

            # Check for mentions
            mentions = re.findall(r'@(\w+)', content)
            for m in set(mentions):
                target_user = User.get_by_username(m)
                if target_user:
                    Notification.create(target_user._id, 'mention', current_user._id, post_id=new_post._id)
            flash('Your post has been created!', 'success')
            return redirect('/me')
        else:
            if len(content) > POST_MAX:
                flash('exceeds the maximum word limit by '+str(-(POST_MAX - len(content)))+', sorry', 'danger')
            else:
                flash('post content is too less','warning')
    return render_template('forms/edit_post.html', form=form, p=p)


@app.route("/image/posts/<userid>/<imageuid>", methods=["GET"])
@login_required
def render_post_image(userid, imageuid):
    return send_from_directory(os.path.join(IMAGED, 'users', userid, "posts"), imageuid)



@app.route("/deletepost", methods=['GET', 'POST'])
@login_required
def deletepost():
    x = request.args
    post_id = x.get("post_id")
    db.postdb.delete_one({"_id": post_id, "user_id": current_user._id})
    return redirect('/me')


@app.route("/like", methods=['POST'])
@login_required
def like():
    post_id = request.args.get("post_id")
    if not post_id:
        return jsonify({"success": False, "message": "Missing post ID"}), 400

    Post.liked(_id=post_id, userx=current_user._id)
    post = db.postdb.find_one({"_id": post_id})

    # Notify post owner if it was a like (not a removal)
    if current_user._id in post.get('liked_by', []):
        Notification.create(post['user_id'], 'like', current_user._id, post_id=post_id)
    return jsonify({
        "success": True,
        "likes": post.get("likes", 0),
        "dislikes": post.get("dislikes", 0)
    })


@app.route("/repost/<post_id>", methods=['POST'])
@login_required
def repost(post_id):
    original_post = Post.get_by_id(post_id)
    if not original_post:
        abort(404)

    # Create a new post that references the original
    new_post = Post(
        title=f"Repost: {original_post.title}",
        content=f"Reposted from @{original_post.username}\n\n{original_post.content}",
        timestamp=dt.now().strftime('%H:%M:%S %Y-%m-%d'),
        user_id=current_user._id,
        images=original_post.images
    )
    new_post.save_to_db()

    # Notify original owner
    Notification.create(original_post.user_id, 'repost', current_user._id, post_id=new_post._id)

    flash("Post reposted!", "success")
    return redirect(url_for('home'))

@app.route("/bookmark/<post_id>", methods=['POST'])
@login_required
def bookmark(post_id):
    # We store bookmarks in the user document
    user_data = db.userdb.find_one({"_id": current_user._id})
    is_bookmarked = post_id in user_data.get('bookmarks', [])
    if is_bookmarked:
        db.userdb.update_one({"_id": current_user._id}, {"$pull": {"bookmarks": post_id}})
        action = "removed from bookmarks"
    else:
        db.userdb.update_one({"_id": current_user._id}, {"$addToSet": {"bookmarks": post_id}})
        action = "added to bookmarks"

    return jsonify({"success": True, "action": action})

@app.route("/bookmarks")
@login_required
def bookmarks():
    user_data = db.userdb.find_one({"_id": current_user._id})
    bookmark_ids = user_data.get('bookmarks', [])
    posts = db.postdb.find({"_id": {"$in": bookmark_ids}}).sort("timestamp", DESCENDING)

    p2 = []
    for i in posts:
        i['content'] = markdown.markdown(i['content'])
        p2.append(i)
    return render_template('home.html', posts=p2, title="My Bookmarks")

@app.route("/block/<username>", methods=["POST"])
@login_required
def block_user(username):
    v = get_idd(username)
    if v == current_user._id:
        return jsonify({"success": False, "message": "You cannot block yourself!"}), 400

    db.userdb.update_one({"_id": current_user._id}, {"$addToSet": {"blocked_users": v}})
    # Also unfollow
    db.userdb.update_one({"_id": current_user._id}, {"$pull": {"following": v}})
    db.userdb.update_one({"_id": v}, {"$pull": {"followers": current_user._id}})

    return jsonify({"success": True, "message": f"User {username} blocked."})

@app.route("/react/<post_id>", methods=['POST'])
@login_required
def post_react(post_id):
    reaction_type = request.json.get('type')
    # Use existing reactions logic in db or create new
    db.postdb.update_one(
        {"_id": post_id},
        {"$addToSet": {f"reactions.{reaction_type}": current_user._id}}
    )
    post = db.postdb.find_one({"_id": post_id})
    return jsonify({"success": True, "reactions": post.get('reactions', {})})

@app.route("/report/<type>/<id>", methods=['POST'])
@login_required
def report_content(type, id):
    reason = request.json.get('reason', 'No reason provided')
    db.reportsdb.insert_one({
        "type": type, # 'post', 'comment', 'user'
        "target_id": id,
        "reporter_id": current_user._id,
        "reason": reason,
        "timestamp": dt.now(),
        "status": "pending"
    })
    return jsonify({"success": True, "message": "Report submitted."})

@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    if not current_user.json().get('is_admin'):
        abort(403)

    reports = db.reportsdb.find({"status": "pending"}).sort("timestamp", -1)
    users = db.userdb.find().limit(50)
    return render_template('admin/dashboard.html', reports=reports, users=users)

@app.route("/admin/ban/<user_id>", methods=['POST'])
@login_required
def ban_user(user_id):
    if not current_user.json().get('is_admin'):
        abort(403)

    db.userdb.update_one({"_id": user_id}, {"$set": {"is_banned": True}})
    db.audit_logs.insert_one({
        "action": "ban_user",
        "admin_id": current_user._id,
        "target_id": user_id,
        "timestamp": dt.now()
    })
    flash("User banned.", "success")
    return redirect(url_for('admin_dashboard'))



@app.route("/api/post/<post_id>/view", methods=['POST'])
@login_required
def track_view(post_id):
    db.postdb.update_one({"_id": post_id}, {"$inc": {"views": 1}})
    return jsonify({"success": True})

@app.route("/groups")
@login_required
def groups_list():
    groups = db.groupsdb.find()
    return render_template('groups/list.html', groups=groups)

@app.route("/group/create", methods=['GET', 'POST'])
@login_required
def create_group():
    if request.method == 'POST':
        name = request.form.get('name')
        desc = request.form.get('description')
        db.groupsdb.insert_one({
            "name": name,
            "description": desc,
            "owner_id": current_user._id,
            "members": [current_user._id],
            "timestamp": dt.now()
        })
        flash("Group created!", "success")
        return redirect(url_for('groups_list'))
    return render_template('forms/create_group.html')

@app.route("/group/<group_id>")
@login_required
def group_view(group_id):
    group_data = db.groupsdb.find_one({"_id": group_id})
    if not group_data:
        abort(404)
    group = Group(**group_data)
    posts = db.postdb.find({"group_id": group_id, "is_draft": {"$ne": True}}).sort("timestamp", DESCENDING)
    is_member = current_user._id in group.members
    is_mod = current_user._id in group.mods or group.owner_id == current_user._id

    # Sidebar data
    owner = User.get_by_id(group.owner_id)
    mods = [User.get_by_id(uid) for uid in group.mods]
    members = [User.get_by_id(uid) for uid in group.members[:10]] # Limit preview

    p2 = []
    for i in posts:
        i['content'] = markdown.markdown(i['content'])
        p2.append(i)

    return render_template('groups/view.html',
                           group=group,
                           posts=p2,
                           is_member=is_member,
                           is_mod=is_mod,
                           owner=owner,
                           mods=mods,
                           members=members,
                           User=User)

@app.route("/group/<group_id>/stats")
@login_required
def group_stats(group_id):
    group = Group.get_by_id(group_id)
    if not group or (group.owner_id != current_user._id and current_user._id not in group.mods):
        abort(403)

    group_posts = db.postdb.find({"group_id": group_id})
    total_views = sum(p.get('views', 0) for p in group_posts)

    stats = {
        "member_count": len(group.members),
        "post_count": len(list(db.postdb.find({"group_id": group_id}))),
        "total_views": total_views,
        "request_count": len(group.join_requests)
    }
    return render_template('groups/stats.html', group=group, stats=stats)

@app.route("/group/<group_id>/appoint_mod/<user_id>", methods=['POST'])
@login_required
def appoint_mod(group_id, user_id):
    group = Group.get_by_id(group_id)
    if not group or group.owner_id != current_user._id:
        abort(403)

    db.groupsdb.update_one({"_id": group_id}, {"$addToSet": {"mods": user_id}})
    flash("Moderator appointed.", "success")
    return redirect(url_for('group_view', group_id=group_id))

@app.route("/group/join/<group_id>", methods=['POST'])
@login_required
def join_group(group_id):
    group = Group.get_by_id(group_id)
    if not group:
        abort(404)
    if current_user._id in group.members:
        flash("Already a member.", "info")
    elif current_user._id in group.join_requests:
        flash("Request already pending.", "info")
    else:
        db.groupsdb.update_one({"_id": group_id}, {"$addToSet": {"join_requests": current_user._id}})
        Notification.create(group.owner_id, 'group_request', current_user._id, comment_id=group_id)
        flash("Join request sent!", "success")
    return redirect(url_for('groups_list'))

@app.route("/group/leave/<group_id>", methods=['POST'])
@login_required
def leave_group(group_id):
    group = Group.get_by_id(group_id)
    if not group:
        abort(404)
    if group.owner_id == current_user._id:
        flash("Owners cannot leave their community. Delete it instead?", "warning")
    else:
        db.groupsdb.update_one({"_id": group_id}, {"$pull": {"members": current_user._id, "mods": current_user._id}})
        flash("You have left the community.", "info")
    return redirect(url_for('groups_list'))

@app.route("/group/manage/<group_id>")
@login_required
def group_manage(group_id):
    group = Group.get_by_id(group_id)
    if not group or (group.owner_id != current_user._id and current_user._id not in group.mods):
        abort(403)

    requests = [User.get_by_id(uid) for u_id in group.join_requests if (uid := u_id)]
    return render_template('groups/manage.html', group=group, requests=requests)

@app.route("/group/request/<action>/<group_id>/<user_id>", methods=["POST"])
@login_required
def handle_group_request(action, group_id, user_id):
    group = Group.get_by_id(group_id)
    if not group or (group.owner_id != current_user._id and current_user._id not in group.mods):
        abort(403)

    if action == "accept":
        db.groupsdb.update_one({"_id": group_id}, {"$pull": {"join_requests": user_id}, "$addToSet": {"members": user_id}})
        Notification.create(user_id, 'group_accept', current_user._id, comment_id=group_id)
        flash("Request accepted.", "success")
    else:
        db.groupsdb.update_one({"_id": group_id}, {"$pull": {"join_requests": user_id}})
        flash("Request rejected.", "info")
    return redirect(url_for('group_manage', group_id=group_id))

@app.route("/dislike", methods=['POST'])
@login_required
def dislike():
    post_id = request.args.get("post_id")
    if not post_id:
        return jsonify({"success": False, "message": "Missing post ID"}), 400

    Post.disliked(_id=post_id, userx=current_user._id)
    post = db.postdb.find_one({"_id": post_id})
    return jsonify({
        "success": True,
        "likes": post.get("likes", 0),
        "dislikes": post.get("dislikes", 0)
    })

@app.route("/set/aboutme", methods=['GET', 'POST'])
@login_required
def setaboutme():
    return redirect('/settings')


@app.route("/settings", methods=['GET', 'POST'])
@login_required
def settings():
    form = SettingsForm()

    if request.method == "GET":
        form.username.data = current_user.username
        form.content.data = User.get_aboutme(current_user._id)
        form.email.data = current_user.email
        form.is_private.data = current_user.json().get('is_private', False)

    if form.validate_on_submit():
        username = form.username.data
        aboutme = form.content.data.strip()
        email = form.email.data.strip()
        is_private = form.is_private.data
        check = db.userdb.find_one({"username": form.username.data})
        if current_user.username == username:
            pass
        else:
            db.postdb.update_many({"user_id": current_user._id},
                {
                    "$set": {
                        "username": username,
                    }
                })
        k = 0
        if len(form.username.data) in range(USERNAME_MIN, USERNAME_MAX+1):
            if len(aboutme) in range(ABOUT_ME_MIN, ABOUT_ME_MAX + 1):
                if check is None:
                    k = 1
                else:
                    if check['_id'] == current_user._id:
                        k = 1
                    else:
                        k = 0
                        flash('This username is already taken','warning')
            else:
                if len(aboutme) > ABOUT_ME_MAX:
                    flash('Your "About Me" is too long.', 'warning')
                else:
                    flash('Your "About Me" is too short.', 'warning')
        else:
            if len(form.username.data) > USERNAME_MAX:
                flash('This username is too long.', 'warning')
            else:
                flash('This username is too short', 'warning')
        if k == 1:
            User.change_username(current_user._id, username)
            User.addaboutme(current_user._id, aboutme)
            User.change_email(current_user._id, email)
            db.userdb.update_one({"_id": current_user._id}, {"$set": {"is_private": is_private}})
            file = request.files.get("pfp")
            if file:
                if file.filename == "":
                    flash("Empty file name", "warning")
                elif not allowed_file(file.filename):
                    flash("Invalid file type", "danger")
                else:
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    user_dir = os.path.join(IMAGED, 'users', current_user._id)
                    os.makedirs(user_dir, exist_ok=True)

                    # Remove old avatars
                    for old_ext in ['jpg', 'jpeg', 'png', 'gif']:
                        old_path = os.path.join(user_dir, f"pfp.{old_ext}")
                        if os.path.exists(old_path):
                            os.remove(old_path)

                    save_path = os.path.join(user_dir, f"pfp.{ext}")
                    file.save(save_path)
                    flash("Profile picture updated.", "success")
            else:
                flash("No profile picture uploaded", "info")

            flash('Your changes have been saved', 'success')
            return redirect('/me')

    return render_template('forms/settings.html', title='Settings', form=form)




@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html')


@app.route('/404')
def x404():
    return render_template('errors/404.html')


@app.route('/git_help')
def git_help():
    path = "git_help.txt"
    return send_file(path, as_attachment=True)


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    logout_user()
    flash('bye bye!','success')
    return redirect('/')


@app.route('/request_reset_password', methods=['GET', 'POST'])
def request_reset_password():
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.get_by_email(form.email.data)
        if user:
            User.reset_password(form.email.data)
            flash('An email has been sent with instructions to reset your password.', 'info')
        else:
            flash('There is no account with that email. You must register first.', 'warning')
        return redirect(url_for('login'))
    return render_template('forms/request_reset_password.html', title='Reset Password', form=form)


@app.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    user = User.verify_reset_token(token)
    if user is None:
        flash('That is an invalid or expired token', 'warning')
        return redirect(url_for('request_reset_password'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        user.password = hashed_password
        db.userdb.update_one({"_id": user.get_id()}, {"$set": {"password": user.password}})
        flash('Your password has been updated! You are now able to log in', 'success')
        return redirect(url_for('login'))
    return render_template('forms/reset_password.html', title='Reset Password', form=form)


@app.route("/messaging/dashboard", methods=['GET', 'POST'])
@login_required
def messagingdashboard():
    conversations = Messages.get_conversations(current_user._id)
    return render_template('messages/mdashboard.html', conversations=conversations, User=User)


@app.route('/deletemsg')
@login_required
def deletemsg():
    x = request.args
    msg_id = x.get("msg_id")
    is_ajax = x.get("ajax")
    db.messagesdb.delete_one({"_id": msg_id, "sender":current_user._id})

    if is_ajax:
        return jsonify({"success": True})

    red = x.get("redirect")
    red = "/message/" + red if red else "/messaging/dashboard"
    return redirect(red)

@app.route("/message/<username>")
@login_required
def message_page(username):
    other_user = User.get_by_username(username)
    if not other_user:
        abort(404)
    return render_template("messages/message-page.html", recipient=get_idd(username), other_user=other_user, User=User,username=username)

@app.route("/api/messages")
@login_required
def get_messages():
    user2 = request.args.get("with")
    before = request.args.get("before")
    after = request.args.get("after") # Added 'after' for efficient polling
    if not user2:
        return jsonify([])

    query = {"$or": [{"sender": current_user._id, "receiver": user2}, {"sender": user2, "receiver": current_user._id}]}

    if before:
        before_msg = db.messagesdb.find_one({"_id": before})
        if before_msg: query["timestamp"] = {"$lt": before_msg["timestamp"]}
    elif after:
        after_msg = db.messagesdb.find_one({"_id": after})
        if after_msg: query["timestamp"] = {"$gt": after_msg["timestamp"]}

    chats = list(db.messagesdb.find(query).sort("timestamp", -1).limit(50))
    if not after:
        chats.reverse()

    # Automatically mark messages as read when fetched via API
    Messages.mark_as_read(user2, current_user._id)
    # Update current user's last_seen
    db.userdb.update_one({"_id": current_user._id}, {"$set": {"last_seen": dt.utcnow()}})

    return jsonify([Messages(**m).json() for m in chats])

@app.route("/api/messages/send", methods=["POST"])
@login_required
def send_message_v2():
    data = request.get_json()
    recipient = data.get("recipient")
    content = filter_profanity(data.get("message"))

    if not recipient or not content:
        return jsonify({"success": False, "error": "Missing data"}), 400

    # Check blocking
    recipient_user = User.get_by_id(recipient)
    if recipient_user:
        if current_user._id in recipient_user.blocked_users or recipient in current_user.json().get('blocked_users', []):
            return jsonify({"success": False, "error": "Message blocked."}), 403

    msg = Messages.send_message(sender=current_user._id, receiver=recipient, message=content)
    db.userdb.update_one({"_id": current_user._id}, {"$set": {"last_seen": dt.utcnow()}})
    return jsonify({"success": True, "message": msg})

@app.route('/save_theme', methods=['POST'])
def save_theme():
    data = request.get_json()
    theme = data.get('theme')
    if theme in ['light', 'dark']:
        session['theme'] = theme
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Invalid theme'}), 400



@app.route("/api/conversations")
@login_required
def get_conversations_api():
    conversations = Messages.get_conversations(current_user._id)
    # Map to JSON serializable format
    res = []
    for c in conversations:
        res.append({
            "username": c["_id"],
            "last_message": Messages(**c["last_message"]).json(),
            "unread_count": c["unread_count"],
            "avatar": User.avatar(c["_id"])
        })
    return jsonify(res)

@app.route("/api/message/react", methods=["POST"])
@login_required
def react_to_message():
    data = request.get_json()
    message_id = data.get("message_id")
    emoji = data.get("emoji")

    if not message_id or not emoji:
        return jsonify({"success": False, "error": "Missing data"}), 400

    message = db.messagesdb.find_one({"_id": message_id})
    if not message:
        return jsonify({"success": False, "error": "Message not found"}), 404

    reactions = message.get("reactions", {})

    if emoji not in reactions:
        reactions[emoji] = []

    # Toggle the user's reaction
    if current_user._id in reactions[emoji]:
        reactions[emoji].remove(current_user._id)
        if not reactions[emoji]:
            del reactions[emoji]
    else:
        reactions[emoji].append(current_user._id)

    db.messagesdb.update_one(
        {"_id": message_id},
        {"$set": {"reactions": reactions}}
    )

    return jsonify({"success": True, "reactions": reactions})

@app.route('/avatar/<identifier>')
def avatar(identifier):
    # identifier could be ID or username
    user = User.get_by_id(identifier) or User.get_by_username(identifier)

    if not user:
        # Check if the identifier is already an ID and try to find by username
        user = User.get_by_username(identifier)

    if not user:
        return send_from_directory('static', 'noavatar.jpeg')

    static_dir = os.path.join(IMAGED,'users',user._id)
    k = 0
    for ext in ['jpg', 'jpeg', 'png', 'gif']:
        path = os.path.join(static_dir, f"pfp.{ext}")
        if os.path.isfile(path):
            return send_from_directory(static_dir, f"pfp.{ext}")
            k = 1
        else:
            k = 0
    if k == 0:
        j = User.get_email(get_idd(username))
        if j:
            digest = md5(j.lower().encode('utf-8')).hexdigest()
            url = 'https://www.gravatar.com/avatar/{}?d=identicon&s={}'.format(
                digest, 128)
            os.makedirs(static_dir, exist_ok=True)
            with urllib.request.urlopen(url) as response:
                image_data = response.read()
                with open(path, "wb") as file:
                    file.write(image_data)
            return send_from_directory(static_dir, f"pfp.{ext}")
    return None


app.jinja_env.globals.update(get_username2=get_username)


@app.route("/follow/<username>", methods=["POST"])
@login_required
def toggle_follow(username):
    v = get_idd(username)
    if v == current_user._id:
        return jsonify({"success": False, "message": "You cannot follow yourself!"}), 400

    target_data = db.userdb.find_one({"_id": v})
    if not target_data:
        return jsonify({"success": False, "message": "User not found!"}), 404

    target = User(**target_data)

    is_following = current_user._id in target.followers

    if is_following:
        db.userdb.update_one({"_id": v}, {"$pull": {"followers": current_user._id}})
        db.userdb.update_one({"_id": current_user._id}, {"$pull": {"following": v}})
        action = "unfollowed"
    else:
        if target.is_private:
            if current_user._id in target.follow_requests:
                db.userdb.update_one({"_id": v}, {"$pull": {"follow_requests": current_user._id}})
                action = "request cancelled"
            else:
                db.userdb.update_one({"_id": v}, {"$addToSet": {"follow_requests": current_user._id}})
                Notification.create(v, 'follow_request', current_user._id)
                action = "requested"
        else:
            db.userdb.update_one({"_id": v}, {"$addToSet": {"followers": current_user._id}})
            db.userdb.update_one({"_id": current_user._id}, {"$addToSet": {"following": v}})
            Notification.create(v, 'follow', current_user._id)
            action = "followed"

    # Get updated count
    updated_user_data = db.userdb.find_one({"_id": v})
    follower_count = len(updated_user_data.get("followers", []))

    return jsonify({
        "success": True,
        "action": action,
        "is_following": current_user._id in updated_user_data.get("followers", []),
        "follower_count": follower_count
    })

@app.route("/followers/<username>")
@login_required
def get_followers(username):
    v = get_idd(username)
    user = db.userdb.find_one({"_id": v})
    if not user:
        return jsonify({"success": False, "message": "User not found!"}), 404
    j = []
    if user.get("followers", []):
        for i in user.get("followers", []):
            j.append(get_username(i))
    return jsonify({
        "success": True,
        "type": "followers",
        "users": j
    })

@app.route("/following/<username>")
@login_required
def get_following(username):
    v = get_idd(username)
    user = db.userdb.find_one({"_id": v})
    if not user:
        return jsonify({"success": False, "message": "User not found!"}), 404
    j = []
    if user.get("following", []):
        for i in user.get("following", []):
            j.append(get_username(i))
    return jsonify({
        "success": True,
        "type": "following",
        "users": j
    })


@app.route("/repos/<username>")
@login_required
def user_repos(username):
    user = User.get_by_id(get_idd(username))
    if not user:
        abort(404)
    repos = Repository.find_by_owner(get_idd(username))
    return render_template("repo/repos.html", user=user, repos=repos)


@app.route("/repo/create", methods=["GET", "POST"])
@login_required
def create_repo():
    form = RepositoryForm()
    if form.validate_on_submit():
        name = secure_filename(form.name.data)
        if not name:
            flash("Invalid repository name.", "danger")
            return render_template("forms/create_repo.html", form=form)

        existing = Repository.get_by_owner_and_name(current_user._id, name)
        if existing:
            flash("You already have a repository with that name.", "danger")
            return render_template("forms/create_repo.html", form=form)

        repo_dir = os.path.join(REPOS_PATH, current_user._id, f"{name}.git")
        if os.path.exists(repo_dir):
            shutil.rmtree(repo_dir)

        os.makedirs(repo_dir, exist_ok=True)
        try:
            subprocess.run(["git", "init", "--bare"], cwd=repo_dir, check=True)
            # Enable git-http-backend
            subprocess.run(["git", "config", "http.receivepack", "true"], cwd=repo_dir, check=True)

            new_repo = Repository(name=name, owner=current_user._id, description=form.description.data)
            new_repo.save_to_db()
            flash(f"Repository {name} created successfully!", "success")
            return redirect(url_for("repo_view", username=current_user._id, reponame=name,current_user=current_user))
        except subprocess.CalledProcessError:
            flash("Error initializing repository.", "danger")
            return render_template("forms/create_repo.html", form=form)

    return render_template("forms/create_repo.html", form=form)


@app.route("/repo/<username>/<reponame>")
@app.route("/repo/<username>/<reponame>/tree/<ref>/")
@app.route("/repo/<username>/<reponame>/tree/<ref>/<path:path>")
@login_required
def repo_view(username, reponame, ref=None, path=""):
    v = get_idd(username)
    repo = Repository.get_by_owner_and_name(v, reponame)
    if not repo:
        abort(404)

    repo_dir = os.path.join(REPOS_PATH, v, f"{reponame}.git")
    if not ref:
        ref = get_git_default_branch(repo_dir)

    try:
        branches = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/"],
            cwd=repo_dir, capture_output=True, text=True
        ).stdout.strip().splitlines()
    except:
        branches = []
    check = subprocess.run(["git", "rev-parse", "--verify", ref],
                          cwd=repo_dir, capture_output=True)
    ref_exists = (check.returncode == 0)

    entries = list_git_tree(repo_dir, ref, path)

    latest_commit = get_latest_commit(repo_dir, ref) if ref_exists else None

    readme_content = None
    if not path and ref_exists:
        for entry in entries:
            if entry['name'].lower() in ['readme.md', 'readme.markdown']:
                blob = get_git_blob(repo_dir, ref, entry['name'])
                if blob:
                    try:
                        # Basic sanitization could go here, but using the project's markdown pattern
                        readme_content = markdown.markdown(blob.decode('utf-8'))
                    except:
                        pass
                break

    clone_url = f"{request.url_root.rstrip('/')}/git/{username}/{reponame}.git"
    return render_template(
        "repo/repo_view.html",
        repo=repo,
        clone_url=clone_url,
        entries=entries,
        ref=ref,
        path=path,
        ref_exists=ref_exists,
        branches=branches,
        latest_commit=latest_commit,
        readme_content=readme_content,
        User=User
    )


@app.route("/repo/<username>/<reponame>/commits/<ref>")
@login_required
def repo_commits(username, reponame, ref):
    v = get_idd(username)
    repo = Repository.get_by_owner_and_name(v, reponame)
    if not repo:
        abort(404)

    repo_dir = os.path.join(REPOS_PATH, v, f"{reponame}.git")
    commits = get_commit_history(repo_dir, ref)

    return render_template(
        "repo/repo_commits.html",
        repo=repo,
        ref=ref,
        commits=commits,
        User=User
    )


@app.route("/repo/<username>/<reponame>/branches")
@login_required
def repo_branches(username, reponame):
    v = get_idd(username)
    repo = Repository.get_by_owner_and_name(v, reponame)
    if not repo:
        abort(404)

    repo_dir = os.path.join(REPOS_PATH, v, f"{reponame}.git")
    try:
        result = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname:short) %(authordate:relative) %(subject)", "refs/heads/"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True
        )
        branches = []
        for line in result.stdout.strip().splitlines():
            parts = line.split(None, 2)
            if len(parts) >= 1:
                branches.append({
                    "name": parts[0],
                    "date": parts[1] if len(parts) >= 2 else "",
                    "message": parts[2] if len(parts) >= 3 else ""
                })
    except subprocess.CalledProcessError:
        branches = []
    return render_template("repo/repo_branches.html", repo=repo, branches=branches)


@app.route("/repo/<username>/<reponame>/blob/<ref>/<path:path>")
@login_required
def repo_blob(username, reponame, ref, path):
    v = get_idd(username)
    repo = Repository.get_by_owner_and_name(v, reponame)
    if not repo:
        abort(404)

    repo_dir = os.path.join(REPOS_PATH, v, f"{reponame}.git")
    blob_content = get_git_blob(repo_dir, ref, path)

    if blob_content is None:
        abort(404)

    try:
        content = blob_content.decode("utf-8")
    except UnicodeDecodeError:
        content = "[Binary content]"

    return render_template(
        "repo/repo_blob.html",
        repo=repo,
        ref=ref,
        path=path,
        content=content
    )


@app.route("/repo/<username>/<reponame>/edit/<ref>/<path:path>", methods=["GET", "POST"])
@login_required
def repo_edit(username, reponame, ref, path):
    v = get_idd(username)
    repo = Repository.get_by_owner_and_name(v, reponame)
    if not repo or repo.owner != current_user._id:
        flash("Unauthorized or repository not found.", "danger")
        return redirect(url_for('repo_view', username=v, reponame=reponame))

    repo_dir = os.path.join(os.path.abspath(REPOS_PATH), v, f"{reponame}.git")

    if request.method == "POST":
        new_path = request.form.get("path", path)
        new_content = request.form.get("content", "")

        try:
            # We use a temporary index to create a commit without a working directory
            env = os.environ.copy()
            index_file = os.path.join(repo_dir, f"temp_index_{uuid.uuid4().hex}")
            env["GIT_INDEX_FILE"] = index_file

            # 1. Read existing tree into index
            subprocess.run(["git", "read-tree", ref], cwd=repo_dir, env=env, check=True)

            # 2. Hash the new content into a blob
            result = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                                   cwd=repo_dir, env=env, input=new_content.encode("utf-8"),
                                   capture_output=True, check=True)
            blob_hash = result.stdout.decode("utf-8").strip()

            # 3. Update index with the new blob at the new path
            # Remove old path if it changed
            if new_path != path:
                subprocess.run(["git", "rm", "--cached", "--ignore-unmatch", path],
                               cwd=repo_dir, env=env, check=True)

            subprocess.run(["git", "update-index", "--add", "--cacheinfo", "100644", blob_hash, new_path],
                           cwd=repo_dir, env=env, check=True)

            # 4. Write tree
            result = subprocess.run(["git", "write-tree"], cwd=repo_dir, env=env, capture_output=True, check=True)
            tree_hash = result.stdout.decode("utf-8").strip()

            # 5. Create commit
            parent_commit = subprocess.run(["git", "rev-parse", ref],
                                         cwd=repo_dir, env=env, capture_output=True, check=True).stdout.decode("utf-8").strip()

            commit_msg = f"Update {new_path}"
            result = subprocess.run(["git", "commit-tree", tree_hash, "-p", parent_commit, "-m", commit_msg],
                                   cwd=repo_dir, env=env, capture_output=True, check=True)
            new_commit_hash = result.stdout.decode("utf-8").strip()

            # 6. Update ref
            subprocess.run(["git", "update-ref", f"refs/heads/{ref}", new_commit_hash], cwd=repo_dir, env=env, check=True)

            if os.path.exists(index_file):
                os.remove(index_file)

            flash(f"File {new_path} updated successfully!", "success")
            return redirect(url_for('repo_blob', username=username, reponame=reponame, ref=ref, path=new_path))

        except subprocess.CalledProcessError as e:
            flash(f"Error committing changes: {e.stderr.decode('utf-8') if e.stderr else str(e)}", "danger")
            if 'index_file' in locals() and os.path.exists(index_file):
                os.remove(index_file)

    blob_content = get_git_blob(repo_dir, ref, path)
    if blob_content is None:
        abort(404)

    try:
        content = blob_content.decode("utf-8")
    except UnicodeDecodeError:
        content = "[Binary content]"

    return render_template(
        "forms/templates/repo/repo_edit.html",
        repo=repo,
        ref=ref,
        path=path,
        content=content
    )


@app.route("/repo/delete/<repo_id>", methods=["POST"])
@login_required
def delete_repo(repo_id):
    repo = Repository.get_by_id(repo_id)
    if not repo or repo.owner != current_user._id:
        flash("Unauthorized or repository not found.", "danger")
        return redirect(url_for("user_repos", username=current_user._id))

    repo_dir = os.path.join(REPOS_PATH, repo.owner, f"{repo.name}.git")
    if os.path.exists(repo_dir):
        shutil.rmtree(repo_dir)

    db.reposdb.delete_one({"_id": repo_id})
    flash(f"Repository {repo.name} deleted.", "success")
    return redirect(url_for("user_repos", username=current_user._id))

@app.route("/notifications")
@login_required
def notifications():
    notifs = Notification.find_by_user(current_user._id)
    Notification.mark_all_read(current_user._id)
    return render_template("notifications.html", notifications=notifs, User=User)

@app.route("/api/notifications/unread_count")
@login_required
def unread_notifications_count():
    count = len(db.notificationsdb.find({"user_id": current_user._id, "read": False}))
    return jsonify({"count": count})

@app.route("/api/user/data")
@login_required
def get_user_data():
    # Limit: 1 per month (30 days)
    last_export = current_user.json().get('last_data_export')
    if last_export:
        if isinstance(last_export, str):
            last_export = dt.fromisoformat(last_export)
        if (dt.now() - last_export).days < 30:
            return jsonify({"error": "Data export is limited to once every 30 days."}), 429

    db.userdb.update_one({"_id": current_user._id}, {"$set": {"last_data_export": dt.now()}})

    limit = request.args.get("limit", default=100, type=int)

    user_data = {
        "profile": current_user.json(),
        "posts": [p for p in db.postdb.find({"user_id": current_user._id}).limit(limit)],
        "comments": [c for c in db.commentdb.find({"user_id": current_user._id}).limit(limit)],
        "repositories": [r for r in db.reposdb.find({"owner": current_user._id}).limit(limit)],
        "messages_sent": [m for m in db.messagesdb.find({"sender": current_user._id}).limit(limit)],
        "messages_received": [m for m in db.messagesdb.find({"receiver": current_user._id}).limit(limit)]
    }

    return jsonify(user_data)
def get_git_default_branch(repo_dir):
    try:
        # Check symbolic-ref first
        result = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True
        )
        branch = result.stdout.strip()
        # Verify if branch has any commits
        check = subprocess.run(["git", "rev-parse", "--verify", branch],
                              cwd=repo_dir, capture_output=True)
        if check.returncode == 0:
            return branch

        # If HEAD's branch is unborn, try to find any other branch
        branches = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/"],
            cwd=repo_dir,
            capture_output=True,
            text=True
        ).stdout.strip().splitlines()

        if branches:
            return branches[0]

        return branch # Fallback to unborn branch name
    except subprocess.CalledProcessError:
        return "master"


def list_git_tree(repo_dir, ref, path=""):
    try:
        # Use ref:path syntax
        tree_ref = f"{ref}:{path}" if path else ref
        result = subprocess.run(
            ["git", "ls-tree", "-l", tree_ref],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True
        )
        lines = result.stdout.strip().splitlines()
        entries = []
        for line in lines:
            parts = line.split(None, 4)
            if len(parts) < 5:
                continue
            entry = {
                "mode": parts[0],
                "type": parts[1],
                "object": parts[2],
                "size": parts[3],
                "name": parts[4]
            }
            entries.append(entry)
        # Sort: directories first, then files
        entries.sort(key=lambda x: (x["type"] != "tree", x["name"]))
        return entries
    except subprocess.CalledProcessError:
        return []


def get_git_blob(repo_dir, ref, path):
    try:
        result = subprocess.run(
            ["git", "cat-file", "-p", f"{ref}:{path}"],
            cwd=repo_dir,
            capture_output=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return None


def get_latest_commit(repo_dir, ref):
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H%n%an%n%at%n%s", ref],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True
        )
        lines = result.stdout.strip().splitlines()
        if len(lines) >= 4:
            return {
                "hash": lines[0],
                "author": lines[1],
                "date": dt.fromtimestamp(int(lines[2])),
                "message": lines[3]
            }
    except:
        return None


def get_commit_history(repo_dir, ref):
    try:
        # Format: hash | author | date | subject | graph
        # Using %ad with --date=short for date
        result = subprocess.run(
            ["git", "log", "--graph", "--format=format:%H%x09%an%x09%at%x09%s", ref],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True
        )
        commits = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue

            # Find the tab characters used as separators
            parts = line.split('\t')
            if len(parts) >= 4:
                # The first part contains the graph and the hash
                graph_and_hash = parts[0]
                hash_match = re.search(r'([0-9a-f]{40})', graph_and_hash)
                if hash_match:
                    commit_hash = hash_match.group(1)
                    graph = graph_and_hash[:hash_match.start()]
                    commits.append({
                        "graph": graph,
                        "hash": commit_hash,
                        "author": parts[1],
                        "date": dt.fromtimestamp(int(parts[2])),
                        "message": parts[3]
                    })
                else:
                    # Line with just graph characters
                    commits.append({
                        "graph": line,
                        "hash": None
                    })
            else:
                # Line with just graph characters or malformed
                commits.append({
                    "graph": line,
                    "hash": None
                })
        return commits
    except:
        return []


@app.route("/git/<username>/<reponame>.git/<path:rest>", methods=["GET", "POST"])
def git_backend(username, reponame, rest):
    # Fetch repository (now case-insensitive)
    v = get_idd(username)
    repo = Repository.get_by_owner_and_name(v, reponame)
    if not repo:
        abort(404)

    # Use canonical names
    username = get_username(repo.owner)
    reponame = repo.name

    # Simple Basic Auth for push operations using git_token
    auth = request.authorization
    authenticated_user = None
    if auth:
        user = User.get_by_username(auth.username)
        if user and user.git_token == auth.password:
            authenticated_user = user

    # Git protocol detection
    is_push = (rest == "git-receive-pack" or
               (rest == "info/refs" and request.args.get("service") == "git-receive-pack"))

    if is_push:
        if not authenticated_user or authenticated_user.username.lower() != username.lower():
            return Response("Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="Git Login"'})

    repo_dir = os.path.join(os.path.abspath(REPOS_PATH), v, f"{reponame}.git")

    env = os.environ.copy()
    env["GIT_PROJECT_ROOT"] = os.path.dirname(repo_dir)
    env["GIT_HTTP_EXPORT_ALL"] = "1"
    env["PATH_INFO"] = f"/{reponame}.git/{rest}"
    env["REMOTE_USER"] = authenticated_user.username if authenticated_user else "anonymous"
    env["REQUEST_METHOD"] = request.method
    env["QUERY_STRING"] = request.query_string.decode("utf-8")
    env["CONTENT_TYPE"] = request.content_type if request.content_type else ""
    env["REMOTE_ADDR"] = request.remote_addr
    env["SERVER_PROTOCOL"] = request.environ.get("SERVER_PROTOCOL", "HTTP/1.1")

    backend_path = "/usr/lib/git-core/git-http-backend"

    process = subprocess.Popen(
        [backend_path],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    stdout, stderr = process.communicate(input=request.data)

    if process.returncode != 0:
        return Response(stderr, 500)

    # git-http-backend returns HTTP headers followed by the body
    header_end = stdout.find(b"\r\n\r\n")
    if header_end == -1:
        header_end = stdout.find(b"\n\n")
        body_start = header_end + 2
    else:
        body_start = header_end + 4

    headers_raw = stdout[:header_end].decode("utf-8")
    body = stdout[body_start:]

    response_headers = []
    status_code = 200
    for line in headers_raw.splitlines():
        if line.startswith("Status: "):
            try:
                status_code = int(line.split(" ")[1])
            except (IndexError, ValueError):
                pass
        elif ":" in line:
            key, value = line.split(":", 1)
            # Avoid duplicate Content-Length or Transfer-Encoding if Flask handles them
            if key.strip().lower() not in ["content-length", "transfer-encoding", "connection"]:
                response_headers.append((key.strip(), value.strip()))

    return Response(body, status_code, response_headers)


@app.route("/edit/post/<post_id>", methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post_data = db.postdb.find_one({"_id": post_id})
    if not post_data:
        flash("Post not found.", "danger")
        return redirect("/")

    post = Post(**post_data)

    if post.user_id != current_user._id:
        flash("You are not authorized to edit this post.", "danger")
        return redirect("/")

    form = PostForm()

    # Populate communities
    user_groups = db.groupsdb.find({"members": current_user._id})
    group_choices = [('account', 'My Account')]
    for g in user_groups:
        group_choices.append((g['_id'], f"Group: {g['name']}"))
    form.post_to.choices = group_choices

    if request.method == 'GET':
        p = 1
        form.title.data = post.title
        form.content.data = post.content
        form.visibility.data = post.visibility
        form.is_draft.data = post.is_draft
        form.post_to.data = post_data.get('group_id', 'account')

    if form.validate_on_submit():
        content = filter_profanity(form.content.data)
        if len(content) in range(POST_MIN,POST_MAX+1):
            # Save current state to edit history before updating
            db.postdb.update_one(
                {"_id": post_id},
                {
                    "$set": {
                        "title": form.title.data,
                        "content": content,
                        "visibility": form.visibility.data,
                        "is_draft": form.is_draft.data,
                        "group_id": form.post_to.data if form.post_to.data != 'account' else None
                    },
                    "$addToSet": {"edit_history": {
                        "title": post.title,
                        "content": post.content,
                        "timestamp": dt.now()
                    }}
                }
            )
            flash("Post updated successfully!", "success")
            return redirect(url_for('post_view', post_id=post_id))
        else:
            if len(form.content.data) > POST_MAX:
                flash("Post content too long", "warning")
            else:
                flash("Post content too short", "danger")
    return render_template("forms/edit_post.html", form=form, p=p)