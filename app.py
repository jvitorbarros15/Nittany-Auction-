from flask import Flask, flash, render_template, request, redirect
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
                role = user[3].lower()     # This works based on the user tuple format due to using cursor.execute()
                                        # Example of user tuple: (id, email, password_hash, role)
                if role == "seller":
                    return redirect("/seller")
                elif role == "buyer":
                    return redirect("/buyer")
                elif role == "helpdesk":
                    return redirect("/helpdesk")
        
        flash("Invalid email or password.")
        return redirect("/login")

    return render_template("login.html")

@app.route("/seller")
def seller():
    return render_template("seller.html")

@app.route("/buyer")
def buyer():
    return render_template("buyer.html")

@app.route("/helpdesk")
def helpdesk():
    return render_template("helpdesk.html")


if __name__ == "__main__":
    app.run(debug=True)