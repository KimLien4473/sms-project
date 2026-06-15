from flask import Flask, render_template, request, redirect, url_for, session
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# 1. Route cho trang Đăng nhập
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Thành viên Backend sẽ viết xử lý kiểm tra tài khoản ở đây
        return redirect(url_for('dashboard'))
    return render_template('login.html')

# 2. Route cho trang Tổng quan (Dashboard)
@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

# 3. Route cho trang Quản lý sinh viên
@app.route('/students')
def students():
    return render_template('student.html')

# 4. Route cho trang Quản lý giảng viên
@app.route('/lecturers')
def lecturers():
    return render_template('lecturer.html')

# 5. Route cho trang Điểm danh
@app.route('/attendance')
def attendance():
    return render_template('attendance.html')

# 6. Route cho trang Bảng điểm
@app.route('/scores')
def scores():
    return render_template('score.html')

if __name__ == '__main__':
    app.run(debug=True)
