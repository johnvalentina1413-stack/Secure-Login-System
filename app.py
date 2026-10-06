from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime, timedelta
import re

app = Flask(__name__)

# Secret key for securely signing sessions
app.secret_key = "change-this-secret-key-in-production"

DATABASE = "database.db"

# Security settings
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_TIME = 60  # seconds


# ---------------------------------------------------
# DATABASE CONNECTION
# ---------------------------------------------------

def get_db_connection():
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------
# CREATE DATABASE
# ---------------------------------------------------

def init_db():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            failed_attempts INTEGER DEFAULT 0,
            locked_until TEXT DEFAULT NULL
        )
    """)

    conn.commit()
    conn.close()


# ---------------------------------------------------
# PASSWORD VALIDATION
# ---------------------------------------------------

def validate_password(password):

    if len(password) < 8:
        return False, "Password must contain at least 8 characters."

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."

    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one number."

    if not re.search(r"[^A-Za-z0-9]", password):
        return False, "Password must contain at least one special character."

    return True, "Password is valid."


# ---------------------------------------------------
# HOME PAGE
# ---------------------------------------------------

@app.route("/")
def home():

    if "username" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# ---------------------------------------------------
# REGISTER
# ---------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        # Check username
        if len(username) < 3:
            flash("Username must contain at least 3 characters.", "error")
            return redirect(url_for("register"))

        # Confirm password
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("register"))

        # Validate password
        valid, message = validate_password(password)

        if not valid:
            flash(message, "error")
            return redirect(url_for("register"))

        # Hash password
        hashed_password = generate_password_hash(password)

        try:

            conn = get_db_connection()

            conn.execute(
                """
                INSERT INTO users (username, password)
                VALUES (?, ?)
                """,
                (username, hashed_password)
            )

            conn.commit()
            conn.close()

            flash("Registration successful. You can now log in.", "success")

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:

            flash("Username already exists.", "error")

            return redirect(url_for("register"))

    return render_template("register.html")


# ---------------------------------------------------
# LOGIN
# ---------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_db_connection()

        user = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        # User does not exist
        if user is None:

            conn.close()

            flash("Invalid username or password.", "error")

            return redirect(url_for("login"))

        # ---------------------------------------------------
        # CHECK ACCOUNT LOCK
        # ---------------------------------------------------

        if user["locked_until"]:

            locked_until = datetime.fromisoformat(user["locked_until"])

            if datetime.now() < locked_until:

                remaining = int(
                    (locked_until - datetime.now()).total_seconds()
                )

                conn.close()

                flash(
                    f"Account temporarily locked. Try again in {remaining} seconds.",
                    "error"
                )

                return redirect(url_for("login"))

            else:

                # Lockout expired
                conn.execute(
                    """
                    UPDATE users
                    SET failed_attempts = 0,
                        locked_until = NULL
                    WHERE username = ?
                    """,
                    (username,)
                )

                conn.commit()

                user = conn.execute(
                    "SELECT * FROM users WHERE username = ?",
                    (username,)
                ).fetchone()

        # ---------------------------------------------------
        # CHECK PASSWORD
        # ---------------------------------------------------

        if check_password_hash(user["password"], password):

            # Successful login
            conn.execute(
                """
                UPDATE users
                SET failed_attempts = 0,
                    locked_until = NULL
                WHERE username = ?
                """,
                (username,)
            )

            conn.commit()
            conn.close()

            session["username"] = username

            flash("Login successful!", "success")

            return redirect(url_for("dashboard"))

        else:

            # Wrong password
            failed_attempts = user["failed_attempts"] + 1

            if failed_attempts >= MAX_LOGIN_ATTEMPTS:

                locked_until = datetime.now() + timedelta(
                    seconds=LOCKOUT_TIME
                )

                conn.execute(
                    """
                    UPDATE users
                    SET failed_attempts = ?,
                        locked_until = ?
                    WHERE username = ?
                    """,
                    (
                        failed_attempts,
                        locked_until.isoformat(),
                        username
                    )
                )

                conn.commit()
                conn.close()

                flash(
                    "Too many failed login attempts. "
                    "Your account has been temporarily locked.",
                    "error"
                )

                return redirect(url_for("login"))

            else:

                conn.execute(
                    """
                    UPDATE users
                    SET failed_attempts = ?
                    WHERE username = ?
                    """,
                    (failed_attempts, username)
                )

                conn.commit()
                conn.close()

                remaining_attempts = (
                    MAX_LOGIN_ATTEMPTS - failed_attempts
                )

                flash(
                    f"Invalid username or password. "
                    f"{remaining_attempts} attempts remaining.",
                    "error"
                )

                return redirect(url_for("login"))

    return render_template("login.html")


# ---------------------------------------------------
# DASHBOARD
# ---------------------------------------------------

@app.route("/dashboard")
def dashboard():

    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        username=session["username"]
    )


# ---------------------------------------------------
# LOGOUT
# ---------------------------------------------------

@app.route("/logout")
def logout():

    session.clear()

    flash("You have been logged out.", "success")

    return redirect(url_for("login"))


# ---------------------------------------------------
# START APPLICATION
# ---------------------------------------------------

if __name__ == "__main__":

    init_db()

    app.run(debug=True)