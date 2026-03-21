from flask import Flask, render_template, request, redirect

app = Flask(__name__)

@app.route("/")
def homepage():
    return render_template("homepage.html")

# Have to add the route to login page here

if __name__ == "__main__":
    app.run(debug=True)