from models import *
from forms import *
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
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


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@appx.route("/upload/image", methods=["GET", "POST"])
@login_required
def upload_image():
    if request.method == "POST":
        if "image" not in request.files:
            flash("No file part", "danger")
            return redirect(request.url)

        file = request.files["image"]
        if file.filename == "":
            flash("No selected file", "warning")
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            user_folder = os.path.join(IMAGED, current_user._id)
            os.makedirs(user_folder, exist_ok=True)

            save_path = os.path.join(user_folder, filename)
            file.save(save_path)

            flash("Image uploaded successfully!", "success")
            return redirect(url_for("render_image", imageuid=filename))

        flash("Invalid file type!", "danger")
        return redirect(request.url)

    return render_template("upload_image.html")

@appx.route("/image/<imageuid>", methods=["GET", "POST"])
@login_required
def render_image(imageuid):
    return send_from_directory(IMAGED + "/" + current_user._id, imageuid)


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

    # Get posts
    posts = db.postdb.find({"user_id": user._id}).sort("timestamp", DESCENDING).limit(10)
    p2 = []
    for post in posts:
        post['content'] = markdown.markdown(post['content'])
        p2.append(post)

    # Gallery: fetch all images from user-specific folder
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


@appx.route("/upload/post", methods=['GET', 'POST'])
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
        # Unfollow
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
        # Follow
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


