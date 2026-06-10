from models import *
from forms import *
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
import re
import subprocess
import shutil
import markdown
from datetime import datetime as dt
from core import app, db, ASCENDING, DESCENDING
from profanity import filter_profanity
from flask import request, jsonify
from hashlib import md5
import urllib.request

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
def home():
    posts = db.postdb.find().sort("timestamp", DESCENDING).limit(10)
    p2 = []
    for i in posts:
        i['content'] = markdown.markdown(i['content'])
        p2.append(i)
    return render_template('home.html', posts=p2)

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
            Comment.create(
                post_id=post_id,
                user_id=current_user._id,
                content=content
            )
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
            Comment.create(
            post_id=parent_comment.post_id,
            username=current_user.username,
            content=content,
            parent_comment_id=comment_id
        )
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
    avatar = User.avatar(user.username)
    aboutme = User.get_aboutme(user.username)
    posts = db.postdb.find({"user_id": user._id}).sort("timestamp", DESCENDING).limit(10)
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
def createnewpost():
    form = PostForm()
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
            new_post = Post(
                title=title,
                content=content,
                timestamp=timestamp,
                user_id=user_id,
                images=image_urls
            )
            new_post.save_to_db()
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
    return jsonify({
        "success": True,
        "likes": post.get("likes", 0),
        "dislikes": post.get("dislikes", 0)
    })


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

    if form.validate_on_submit():
        username = form.username.data
        aboutme = form.content.data.strip()
        email = form.email.data.strip()
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

@app.route('/avatar/<username>')
def avatar(username):
    static_dir = os.path.join(IMAGED,'users',get_idd(username))
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

    target = db.userdb.find_one({"_id": v})
    if not target:
        return jsonify({"success": False, "message": "User not found!"}), 404

    is_following = db.userdb.find_one({
        "_id": v,
        "followers": current_user._id
    })

    if is_following:
        db.userdb.update_one(
            {"_id": v},
            {"$pull": {"followers": current_user._id}}
        )
        db.userdb.update_one(
            {"_id": current_user._id},
            {"$pull": {"following": v}}
        )
        action = "unfollowed"
    else:
        db.userdb.update_one(
            {"_id": v},
            {"$addToSet": {"followers": current_user._id}}
        )
        db.userdb.update_one(
            {"_id": current_user._id},
            {"$addToSet": {"following": v}}
        )
        action = "followed"

    # Get updated count
    updated_user = db.userdb.find_one({"_id": v})
    follower_count = len(updated_user.get("followers", []))

    return jsonify({
        "success": True,
        "action": action,
        "is_following": not is_following,
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

@app.route("/api/user/data")
@login_required
def get_user_data():
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
    post = Post.get_by_id(post_id)

    if not post:
        flash("Post not found.", "danger")
        return redirect("/")

    if post.user_id != current_user._id:
        flash("You are not authorized to edit this post.", "danger")
        return redirect("/")

    form = PostForm()

    if request.method == 'GET':
        p = 1
        form.title.data = post.title
        form.content.data = post.content

    if form.validate_on_submit():
        content = filter_profanity(form.content.data)
        if len(content) in range(POST_MIN,POST_MAX+1):
            db.postdb.update_one(
                {"_id": post_id},
                {
                    "$set": {
                        "title": form.title.data,
                        "content": content
                    }
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