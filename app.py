from flask import Flask, render_template, request, redirect

app = Flask(__name__)

@app.route("/")
def homepage():
    return render_template("homepage.html")

# Have to add the route to login page here
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        # We will check DB here
        print(email, password)

        return "Login attempt"

    return render_template("login.html")


if __name__ == "__main__":
    app.run(debug=True)