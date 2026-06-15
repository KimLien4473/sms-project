from flask import Flask, render_template, session, redirect
from database import get_db_connection
from config import Config
from routes.auth import auth

app = Flask(__name__)
app.config.from_object(Config)

# đăng ký blueprint auth
app.register_blueprint(auth)


# Trang mặc định
@app.route("/")
def home():
    return redirect("/login")


# test mysql
@app.route("/test")
def test():
    conn = get_db_connection()

    if conn:
        return "Kết nối database thành công"

    return "Lỗi kết nối"


# dashboard admin
@app.route("/dashboard")
def dashboard():

    if session.get("role") != "admin":
        return redirect("/login")

    return render_template("dashboard.html")


# student page
@app.route("/student")
def student():

    if session.get("role") != "student":
        return redirect("/login")

    return render_template("student.html")


# lecturer page
@app.route("/lecturer")
def lecturer():

    if session.get("role") != "lecturer":
        return redirect("/login")

    return render_template("lecturer.html")


if __name__ == "__main__":
    app.run(debug=True)