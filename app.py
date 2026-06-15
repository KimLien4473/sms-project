from flask import Flask, render_template, request, redirect, url_for, session

from config import Config
from database import get_db_connection


app = Flask(__name__)
app.config.from_object(Config)


# =========================
# 1. ĐĂNG NHẬP
# =========================
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        # Kết nối database
        conn = get_db_connection()

        if conn:

            cursor = conn.cursor(dictionary=True)

            sql = "SELECT * FROM account WHERE username=%s"

            cursor.execute(sql, (username,))

            user = cursor.fetchone()

            # Tạm thời chưa kiểm tra password thật
            if user:

                # Lưu session đăng nhập
                session["username"] = username

                return redirect(url_for("dashboard"))

            else:
                return "Sai tài khoản hoặc mật khẩu"

    return render_template("login.html")


# =========================
# 2. DASHBOARD
# =========================
@app.route("/dashboard")
def dashboard():

    # Kiểm tra đăng nhập
    if "username" not in session:
        return redirect(url_for("login"))

    return render_template("dashboard.html")


# =========================
# 3. QUẢN LÝ SINH VIÊN
# =========================
@app.route("/students")
def students():

    if "username" not in session:
        return redirect(url_for("login"))

    return render_template("student.html")


# =========================
# 4. QUẢN LÝ GIẢNG VIÊN
# =========================
@app.route("/lecturers")
def lecturers():

    if "username" not in session:
        return redirect(url_for("login"))

    return render_template("lecturer.html")


# =========================
# 5. ĐIỂM DANH
# =========================
@app.route("/attendance")
def attendance():

    if "username" not in session:
        return redirect(url_for("login"))

    return render_template("attendance.html")


# =========================
# 6. QUẢN LÝ ĐIỂM
# =========================
@app.route("/scores")
def scores():

    if "username" not in session:
        return redirect(url_for("login"))

    return render_template("score.html")


# =========================
# 7. QUÊN MẬT KHẨU
# =========================
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":

        phone = request.form["phone"]

        # sau này thêm xử lý OTP ở đây

        return "Đã gửi mã OTP"

    return render_template("forgot_password.html")


# =========================
# 8. ĐỔI MẬT KHẨU
# =========================
@app.route("/change-password", methods=["GET", "POST"])
def change_password():

    if "username" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        old_password = request.form["old_password"]
        new_password = request.form["new_password"]

        # sau này xử lý update database

        return "Đổi mật khẩu thành công"

    return render_template("change_password.html")


# =========================
# 9. ĐĂNG XUẤT
# =========================
@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# =========================
# CHẠY CHƯƠNG TRÌNH
# =========================
if __name__ == "__main__":
    app.run(debug=True)
