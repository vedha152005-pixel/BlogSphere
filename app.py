import os

from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import pymysql


app = Flask(__name__)

app.secret_key = "your-secret-key"


# =========================
# UPLOAD SETTINGS
# =========================

UPLOAD_FOLDER = os.path.join(
    "static",
    "uploads"
)

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp"
}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# =========================
# DATABASE CONNECTION
# =========================

def get_db_connection():

    print("DB HOST:", os.environ.get("DB_HOST"))
    print("DB PORT:", os.environ.get("DB_PORT"))
    print("DB USER:", os.environ.get("DB_USER"))
    print("DB NAME:", os.environ.get("DB_NAME"))
    
    connection = pymysql.connect(
        host=os.environ.get("DB_HOST"),
        port=int(os.environ.get("DB_PORT", 4000)),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD"),
        database=os.environ.get("DB_NAME", "blog_platform"),
        cursorclass=pymysql.cursors.DictCursor,

        ssl_ca=os.path.join(
            os.path.dirname(__file__),
            "ca.pem"
        ),

        ssl_verify_cert=True,
        ssl_verify_identity=True
    )

    return connection

# =========================
# CHECK IMAGE EXTENSION
# =========================

def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


# =========================
# HOME
# =========================

@app.route("/")
def home():

    # User must login/register before entering home
    if "user_id" not in session:
        return redirect(url_for("register"))

    return render_template("index.html")


# =========================
# VIEW POSTS
# =========================

@app.route("/view-posts")
def view_posts():

    # Only logged-in users can view posts
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    # Get all posts
    cursor.execute("""
        SELECT
            posts.*,
            users.name
        FROM posts
        JOIN users
            ON posts.user_id = users.id
        ORDER BY posts.created_at DESC
    """)

    posts = cursor.fetchall()

    # Get comments and reactions for every post
    for post in posts:

        # =========================
        # COMMENTS
        # =========================

        cursor.execute("""
            SELECT
                comments.*,
                users.name
            FROM comments
            JOIN users
                ON comments.user_id = users.id
            WHERE comments.post_id = %s
            ORDER BY comments.created_at ASC
        """, (post["id"],))

        post["comments"] = cursor.fetchall()


        # =========================
        # REACTIONS
        # =========================

        cursor.execute("""
            SELECT
                reaction_type,
                COUNT(*) AS reaction_count
            FROM reactions
            WHERE post_id = %s
            GROUP BY reaction_type
        """, (post["id"],))

        reaction_rows = cursor.fetchall()

        post["like_count"] = 0
        post["dislike_count"] = 0
        post["cheer_count"] = 0

        for reaction in reaction_rows:

            if reaction["reaction_type"] == "like":

                post["like_count"] = reaction["reaction_count"]

            elif reaction["reaction_type"] == "dislike":

                post["dislike_count"] = reaction["reaction_count"]

            elif reaction["reaction_type"] == "cheer":

                post["cheer_count"] = reaction["reaction_count"]


    cursor.close()
    connection.close()

    return render_template(
        "view_posts.html",
        posts=posts
    )


# =========================
# TEST DATABASE
# =========================

@app.route("/test-db")
def test_db():

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT 1")

    result = cursor.fetchone()

    cursor.close()
    connection.close()

    return f"Database connected successfully! Result: {result}"


# =========================
# REGISTER
# =========================

@app.route("/register", methods=["GET", "POST"])
def register():

    # If already logged in, go to home
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]

        if not name or not email or not password:
            return render_template(
                "register.html",
                error="Please fill all fields."
            )

        connection = get_db_connection()
        cursor = connection.cursor()

        # Check whether email already exists
        cursor.execute("""
            SELECT id
            FROM users
            WHERE email = %s
        """, (email,))

        existing_user = cursor.fetchone()

        if existing_user:

            cursor.close()
            connection.close()

            return render_template(
                "register.html",
                error="Email already registered. Please login."
            )

        hashed_password = generate_password_hash(password)

        cursor.execute("""
            INSERT INTO users
            (name, email, password)
            VALUES (%s, %s, %s)
        """, (
            name,
            email,
            hashed_password
        ))

        connection.commit()

        cursor.close()
        connection.close()

        return redirect(url_for("login"))

    return render_template("register.html")

# =========================
# LOGIN
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():

    # If already logged in, go to home
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":

        email = request.form["email"].strip()
        password = request.form["password"]

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT *
            FROM users
            WHERE email = %s
        """, (email,))

        user = cursor.fetchone()

        cursor.close()
        connection.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user_id"] = user["id"]
            session["user_name"] = user["name"]

            return redirect(url_for("home"))

        return "Invalid email or password"

    return render_template("login.html")


# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("register"))


# =========================
# CREATE POST
# =========================

@app.route("/create-post", methods=["GET", "POST"])
def create_post():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        title = request.form["title"].strip()
        content = request.form["content"].strip()

        image = request.files.get("image")

        image_name = None

        # =========================
        # IMAGE UPLOAD
        # =========================

        if image and image.filename:

            if allowed_file(image.filename):

                image_name = secure_filename(
                    image.filename
                )

                image.save(
                    os.path.join(
                        UPLOAD_FOLDER,
                        image_name
                    )
                )

            else:

                return "Invalid image format"

        # =========================
        # SAVE POST
        # =========================

        if not title or not content:
            return "Title and content are required"

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO posts
            (
                user_id,
                title,
                content,
                image
            )
            VALUES (%s, %s, %s, %s)
        """, (
            session["user_id"],
            title,
            content,
            image_name
        ))

        connection.commit()

        cursor.close()
        connection.close()

        return redirect(url_for("view_posts"))

    return render_template("create_post.html")


# =========================
# ADD COMMENT
# =========================

@app.route(
    "/post/<int:post_id>/comment",
    methods=["POST"]
)
def add_comment(post_id):

    # User should already be logged in
    if "user_id" not in session:
        return redirect(url_for("login"))

    comment_text = request.form["comment_text"].strip()

    if comment_text:

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO comments
            (
                user_id,
                post_id,
                comment_text
            )
            VALUES (%s, %s, %s)
        """, (
            session["user_id"],
            post_id,
            comment_text
        ))

        connection.commit()

        cursor.close()
        connection.close()

    return redirect(url_for("view_posts"))


# =========================
# ADD / CHANGE REACTION
# =========================

@app.route(
    "/post/<int:post_id>/reaction",
    methods=["POST"]
)
def react_to_post(post_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    reaction_type = request.form["reaction_type"]

    allowed_reactions = {
        "like",
        "dislike",
        "cheer"
    }

    if reaction_type not in allowed_reactions:
        return redirect(url_for("view_posts"))

    connection = get_db_connection()
    cursor = connection.cursor()

    # Check whether user already reacted
    cursor.execute("""
        SELECT id
        FROM reactions
        WHERE user_id = %s
        AND post_id = %s
    """, (
        session["user_id"],
        post_id
    ))

    existing_reaction = cursor.fetchone()

    if existing_reaction:

        cursor.execute("""
            UPDATE reactions
            SET reaction_type = %s
            WHERE id = %s
        """, (
            reaction_type,
            existing_reaction["id"]
        ))

    else:

        cursor.execute("""
            INSERT INTO reactions
            (
                user_id,
                post_id,
                reaction_type
            )
            VALUES (%s, %s, %s)
        """, (
            session["user_id"],
            post_id,
            reaction_type
        ))

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(url_for("view_posts"))


# =========================
# MY POSTS
# =========================

@app.route("/my-posts")
def my_posts():

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM posts
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (
        session["user_id"],
    ))

    posts = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "my_posts.html",
        posts=posts
    )


# =========================
# DELETE POST
# =========================

@app.route("/delete-post/<int:post_id>")
def delete_post(post_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM posts
        WHERE id = %s
        AND user_id = %s
    """, (
        post_id,
        session["user_id"]
    ))

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(url_for("my_posts"))


# =========================
# EDIT POST
# =========================

@app.route(
    "/edit-post/<int:post_id>",
    methods=["GET", "POST"]
)
def edit_post(post_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM posts
        WHERE id = %s
        AND user_id = %s
    """, (
        post_id,
        session["user_id"]
    ))

    post = cursor.fetchone()

    if not post:

        cursor.close()
        connection.close()

        return "Post not found"

    if request.method == "POST":

        title = request.form["title"].strip()
        content = request.form["content"].strip()

        if not title or not content:
            return "Title and content are required"

        cursor.execute("""
            UPDATE posts
            SET title = %s,
                content = %s
            WHERE id = %s
            AND user_id = %s
        """, (
            title,
            content,
            post_id,
            session["user_id"]
        ))

        connection.commit()

        cursor.close()
        connection.close()

        return redirect(url_for("my_posts"))

    cursor.close()
    connection.close()

    return render_template(
        "edit_post.html",
        post=post
    )


# =========================
# RUN APP
# =========================

if __name__ == "__main__":
    app.run(debug=True)