from models import *
from forms import *
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
@login.user_loader
def load_user(user_id):
    return User.get_by_id(user_id)



@appx.route('/')
@appx.route('/home', methods=['GET', 'POST'])
def home():
    posts = db.postdb.find().sort("timestamp", DESCENDING).limit(10)
    p2 = []
    for i in posts:
        i['content'] = markdown.markdown(i['content'])
        p2.append(i)
    return render_template('home.html', posts=p2)


@appx.route("/post/<post_id>", methods=["GET", "POST"])
@login_required
def post_view(post_id):
    post = Post.get_by_id(post_id)
    if not post:
        abort(404)

    form = CommentForm()

    if form.validate_on_submit():
        if len(form.content.data) <= COMMENT_MAX:
            Comment.create(
                post_id=post_id,
                user_id=current_user._id,
                username=current_user.username,
                content=form.content.data
            )
            flash("Comment added.", "success")
            return redirect(url_for('post_view', post_id=post_id))
        else:
            flash('comment reply too large','warning')
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

@appx.route("/comment/reply/<comment_id>", methods=["POST"])
@login_required
def reply_to_comment(comment_id):
    parent_comment = Comment.get_by_id(comment_id)
    if not parent_comment:
        flash("Comment not found.", "danger")
        return redirect(request.referrer)

    content = request.form.get("reply_content")
    if content:
        if len(content) <= COMMENT_MAX:
            Comment.create(
            post_id=parent_comment.post_id,
            user_id=current_user._id,
            username=current_user.username,
            content=content,
            parent_comment_id=comment_id
        )
            flash("Reply posted!", "success")
        else:
            flash("comment too large", 'warning')
    return redirect(request.referrer)

@appx.route("/comment/delete/<comment_id>", methods=["POST"])
@login_required
def delete_comment(comment_id):
    comment = Comment.get_by_id(comment_id)
    if comment and (comment.user_id == current_user._id or current_user.is_admin):
        db.commentdb.delete_one({"_id": comment_id})
        flash("Comment deleted.", "success")
    else:
        flash("Unauthorized or comment not found.", "danger")
    return redirect(request.referrer)


@appx.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(appx.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@appx.route("/upload/image", methods=["GET", "POST"])
@login_required
def upload_image():
    if request.method == "POST":
        if "image[]" not in request.files:
            flash("No files found", "danger")
            return redirect(request.url)
        files = request.files.getlist("image[]")
        if not files or all(f.filename == "" for f in files):
            flash("No selected files", "warning")
            return redirect(request.url)
        user_folder = os.path.join(IMAGED, current_user._id)
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

    return render_template("upload_image.html")


@appx.route("/image/<userid>/<imageuid>", methods=["GET", "POST"])
@login_required
def render_image(userid,imageuid):
    return send_from_directory(IMAGED + "/" + userid, imageuid)


@appx.route("/<username>")
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
    image_dir = os.path.join(IMAGED, user._id)
    user_images = []
    if os.path.exists(image_dir):
        user_images = [f for f in os.listdir(image_dir) if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif"))]
    return render_template(
        'user.html',
        user=user,
        posts=p2,
        avatar=avatar,
        aboutme=aboutme,
        user_images=user_images
    )

@appx.route("/register", methods=['GET', 'POST'])
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
                    if len(request.form["password"]) <= PASSWORD_MAX:
                        User.register(username, email, password, invcode)
                        flash(f'Account created for {form.username.data}!', 'success')
                        return redirect(url_for('home'))
                    else:
                        flash('password too long','warning')
                else:
                    flash('username does not meet requirements')
            else:
                flash(f'Account already exists for {form.username.data}!', 'success')
    return render_template('register.html', title='Register', form=form)


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





@appx.route("/upload/post", methods=['GET', 'POST'])
@login_required
def createnewpost():
    form = PostForm()

    if form.validate_on_submit():
        title = form.title.data
        content = form.content.data
        user_id = current_user._id
        timestamp = bruh.now().strftime('%H:%M:%S %Y-%m-%d')
        if len(content) <= POST_MAX:
            new_post = Post(
                username=current_user.username,
                title=title,
                content=content,
                timestamp=timestamp,
                user_id=user_id
            )
            new_post.save_to_mongo()
            flash('Your post has been created!', 'success')
            return redirect('/me')
        else:
            flash('exceeds the maximum word limit by '+str(-(POST_MAX - len(content)))+', sorry', 'danger')
    return render_template('create_post.html', title='New Post', form=form)



@appx.route("/deletepost", methods=['GET', 'POST'])
@login_required
def deletepost():
    x = request.args
    post_id = x.get("post_id")
    db.postdb.delete_one({"_id": post_id, "username": current_user.username})
    return redirect('/me')


@appx.route("/like", methods=['POST'])
@login_required
def like():
    post_id = request.args.get("post_id")
    if not post_id:
        return jsonify({"success": False, "message": "Missing post ID"}), 400

    Post.liked(_id=post_id, userx=current_user.username)
    post = db.postdb.find_one({"_id": post_id})
    return jsonify({
        "success": True,
        "likes": post.get("likes", 0),
        "dislikes": post.get("dislikes", 0)
    })


@appx.route("/dislike", methods=['POST'])
@login_required
def dislike():
    post_id = request.args.get("post_id")
    if not post_id:
        return jsonify({"success": False, "message": "Missing post ID"}), 400

    Post.disliked(_id=post_id, userx=current_user.username)
    post = db.postdb.find_one({"_id": post_id})
    return jsonify({
        "success": True,
        "likes": post.get("likes", 0),
        "dislikes": post.get("dislikes", 0)
    })

@appx.route("/set/aboutme", methods=['GET', 'POST'])
@login_required
def setaboutme():
    return redirect('/settings')


@appx.route("/settings", methods=['GET', 'POST'])
@login_required
def settings():
    form = AboutMeForm()

    if request.method == "GET":
        form.content.data = User.get_aboutme(current_user.username)
        form.email.data = current_user.email

    if form.validate_on_submit():
        aboutme = form.content.data.strip()
        email = form.email.data.strip()

        if len(aboutme) <= ABOUT_ME_MAX:
            User.addaboutme(current_user.username, aboutme)
            User.change_email(current_user.username, email)

            file = request.files.get("pfp")
            if file:
                if file.filename == "":
                    flash("Empty file name", "warning")
                elif not allowed_file(file.filename):
                    flash("Invalid file type", "danger")
                else:
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    user_dir = os.path.join(STATIC_FOLDER, current_user.username)
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
        else:
            flash('Your "About Me" is too long.', 'warning')

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
    flash('bye bye!','success')
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

@appx.route("/message/<username>")
@login_required
def message_page(username):
    return render_template("message-page.html", username=username)

@appx.route("/messages6")
@login_required
def get_messages():
    user2 = request.args.get("with")
    if not user2:
        return jsonify([])
    chat = Messages.get_chat(current_user.username, user2)
    return jsonify([m.json() for m in chat])

@appx.route("/api/send_message", methods=["POST"])
@login_required
def send_message_api():
    data = request.get_json()
    recipient = data.get("username")
    content = data.get("message")

    if not recipient or not content:
        return jsonify({"success": False, "error": "Missing data"}), 400

    if len(content) > MESSAGE_MAX:
        return jsonify({"success": False, "error": "Message too long"}), 400

    Messages.send_message(current_user.username, recipient, content)
    return jsonify({"success": True})

@appx.route('/avatar/<username>')
def avatar(username):
    static_dir = os.path.join(STATIC_FOLDER, username)
    for ext in ['jpg', 'jpeg', 'png', 'gif']:
        path = os.path.join(static_dir, f"pfp.{ext}")
        if os.path.isfile(path):
            return send_from_directory(static_dir, f"pfp.{ext}")
    # Default fallback
    return send_from_directory("static",f"noavatar.jpg")




@appx.route("/follow/<username>", methods=["POST"])
@login_required
def toggle_follow(username):
    if username == current_user.username:
        return jsonify({"success": False, "message": "You cannot follow yourself!"}), 400

    target = db.userdb.find_one({"username": username})
    if not target:
        return jsonify({"success": False, "message": "User not found!"}), 404

    is_following = db.userdb.find_one({
        "username": username,
        "followers": current_user.username
    })

    if is_following:
        db.userdb.update_one(
            {"username": username},
            {"$pull": {"followers": current_user.username}}
        )
        db.userdb.update_one(
            {"username": current_user.username},
            {"$pull": {"following": username}}
        )
        action = "unfollowed"
    else:
        db.userdb.update_one(
            {"username": username},
            {"$addToSet": {"followers": current_user.username}}
        )
        db.userdb.update_one(
            {"username": current_user.username},
            {"$addToSet": {"following": username}}
        )
        action = "followed"

    # Get updated count
    updated_user = db.userdb.find_one({"username": username})
    follower_count = len(updated_user.get("followers", []))

    return jsonify({
        "success": True,
        "action": action,
        "is_following": not is_following,
        "follower_count": follower_count
    })

@appx.route("/followers/<username>")
@login_required
def get_followers(username):
    user = db.userdb.find_one({"username": username})
    if not user:
        return jsonify({"success": False, "message": "User not found!"}), 404
    return jsonify({
        "success": True,
        "type": "followers",
        "users": user.get("followers", [])
    })

@appx.route("/following/<username>")
@login_required
def get_following(username):
    user = db.userdb.find_one({"username": username})
    if not user:
        return jsonify({"success": False, "message": "User not found!"}), 404
    return jsonify({
        "success": True,
        "type": "following",
        "users": user.get("following", [])
    })

@appx.route("/edit/post/<post_id>", methods=['GET', 'POST'])
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
        form.title.data = post.title
        form.content.data = post.content

    if form.validate_on_submit():
        if len(form.content.data) <= POST_MAX:
            db.postdb.update_one(
                {"_id": post_id},
                {
                    "$set": {
                        "title": form.title.data,
                        "content": form.content.data
                    }
                }
            )
            flash("Post updated successfully!", "success")
            return redirect(url_for('post_view', post_id=post_id))
        else:
            flash("Post content too long", "warning")

    return render_template("edit_post.html", form=form)

