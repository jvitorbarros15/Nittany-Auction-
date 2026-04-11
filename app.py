from flask import Flask, flash, render_template, request, redirect, session
import sqlite3
import hashlib
app = Flask(__name__)
app.secret_key = "your_secret_key" 

@app.route("/")
def homepage():
    return render_template("homepage.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    # When user submits the form
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        # Connect to SQLite database
        connection = sqlite3.connect("nittanyauction.db")
        cursor = connection.cursor()
        cursor.execute(
            "SELECT email, password_hash, salt, role FROM auth_users WHERE email = ?", (email,)) # Look for a user with this email 
        user = cursor.fetchone()  
        connection.close()  

        if user:
            stored_password_hash = user[1]
            salt = user[2]
            role = user[3].lower()

            # This checks if the password matches the hash stored in the database and gets the role from the database (seller, buyer, helpdesk)
            hashed_input = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

            if stored_password_hash == hashed_input:
                session["email"] = user[0]
                session["role"]  = role
                if role == "seller":
                    return redirect("/seller")
                elif role == "buyer":
                    return redirect("/buyer")
                elif role == "helpdesk":
                    return redirect("/helpdesk")
        
        flash("Invalid email or password.", "error")
        return redirect("/login")

    return render_template("login.html")

def seller_required():
    if session.get("role") != "seller":
        flash("Please log in as a seller to access that page.", "error")
        return redirect("/login")
    return None


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect("/login")


@app.route("/seller")
def seller():
    guard = seller_required()
    if guard:
        return guard
    return render_template("seller_welcome.html", email=session["email"])

@app.route("/buyer")
def buyer():
    return render_template("buyer_welcome.html")

@app.route("/helpdesk")
def helpdesk():
    return render_template("helpdesk_welcome.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        role = request.form.get("role")

        valid_roles = ["seller", "buyer", "helpdesk"]
        if role not in valid_roles:
            flash("Invalid role selected.")
            return redirect("/register")

        connection = sqlite3.connect("nittanyauction.db")
        cursor = connection.cursor()

        # Here we are checking if user already exists
        cursor.execute("SELECT * FROM auth_users WHERE email = ?", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            connection.close()
            flash("Email already registered.", "error")
            return redirect("/register")
        salt = hashlib.sha256(email.encode("utf-8")).hexdigest()[:16]
        password_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

        # Insert new user
        cursor.execute(
            "INSERT INTO auth_users (email, password_hash, salt, role) VALUES (?, ?, ?, ?)",
            (email, password_hash, salt, role)
        )
        connection.commit()
        connection.close()

        flash("Welcome to NittanyAuction. Your account has been created.", "success")
        return redirect("/login")

    return render_template("register.html")


if __name__ == "__main__":
    app.run(debug=True)