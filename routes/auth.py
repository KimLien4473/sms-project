from flask import Blueprint, render_template, request, redirect, url_for, session
from database import get_db_connection

auth = Blueprint("auth", __name__)


@auth.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        connection = get_db_connection()

        cursor = connection.cursor(dictionary=True)
        

        sql = """
        SELECT * FROM account
        WHERE username=%s AND password=%s
        """

        cursor.execute(sql, (username, password))

        user = cursor.fetchone()

        connection.close()

        if user:

            session["user_id"] = user["id"]
            session["role"] = user["role"]

            # phân quyền
            if user["role"] == "admin":
                return redirect("/dashboard")

            elif user["role"] == "lecturer":
                return redirect("/lecturer")

            elif user["role"] == "student":
                return redirect("/student")

        else:
            return "Sai tài khoản hoặc mật khẩu"

    return render_template("login.html")
@auth.route("/logout")
def logout():

    session.clear()

    return redirect("/login")