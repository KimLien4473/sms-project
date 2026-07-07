
import bcrypt
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
import pymysql
from pymysql.cursors import DictCursor
from functools import wraps

# ============================================================
# 1. CẤU HÌNH FLASK VÀ DATABASE
# ============================================================
app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',         
    'database': 'sms_db',
    'charset': 'utf8mb4',
    'cursorclass': DictCursor,
    'autocommit': True
}

# ============================================================
# 2. HÀM KẾT NỐI DATABASE
# ============================================================
def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

def execute_query(sql, params=None, fetch_one=False, fetch_all=False):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params or ())
            if fetch_one:
                return cursor.fetchone()
            if fetch_all:
                return cursor.fetchall()
            conn.commit()
            return cursor.lastrowid
    except Exception as e:
        print(f"Lỗi database: {e}")
        conn.rollback()
        raise e
    finally:
        conn.close()

# ============================================================
# 3. HÀM TIỆN ÍCH
# ============================================================
def get_account_by_username(username):
    sql = """
        SELECT a.*, r.RoleName
        FROM Account a
        JOIN Role r ON a.RoleID = r.RoleID
        WHERE a.Username = %s
    """
    return execute_query(sql, (username,), fetch_one=True)

def get_user_info(account):
    if account['RoleName'] == 'student' and account['StudentID']:
        return execute_query("SELECT * FROM Student WHERE StudentID = %s", (account['StudentID'],), fetch_one=True)
    elif account['RoleName'] == 'lecturer' and account['LecturerID']:
        return execute_query("SELECT * FROM Lecturer WHERE LecturerID = %s", (account['LecturerID'],), fetch_one=True)
    return None

def get_user_display_name(account):
    if account['RoleName'] == 'student' and account['StudentID']:
        user = get_user_info(account)
        return user['FullName'] if user else account['Username']
    elif account['RoleName'] == 'lecturer' and account['LecturerID']:
        user = get_user_info(account)
        return user['FullName'] if user else account['Username']
    return account['Username']

def redirect_by_role(role):
    """Chuyển hướng người dùng đến trang tương ứng sau đăng nhập."""
    if role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif role == 'lecturer':
        return redirect(url_for('lecturer_profile'))
    elif role == 'student':
        return redirect(url_for('student_profile'))
    else:
        flash('Vai trò không xác định.', 'err')
        return redirect(url_for('logout'))

# ============================================================
# 4. DECORATORS
# ============================================================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Vui lòng đăng nhập để tiếp tục.', 'warn')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'role' not in session or session['role'] != role:
                flash('Bạn không có quyền truy cập trang này.', 'err')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator

# ============================================================
# 5. LOGIN - LOGOUT - RESET PASSWORD
# ============================================================
@app.route('/')
def index():
    """Trang chủ - luôn hiển thị login khi chưa đăng nhập."""
    if 'user_id' in session:
        return redirect_by_role(session.get('role'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        # Nếu đã đăng nhập thì chuyển đến dashboard
        if 'user_id' in session:
            return redirect_by_role(session.get('role'))
        return render_template('login.html')

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'student')

    if not username or not password:
        flash('Vui lòng nhập đầy đủ thông tin.', 'err')
        return redirect(url_for('login'))

    account = get_account_by_username(username)
    if not account:
        flash('Sai username hoặc password.', 'err')
        return redirect(url_for('login'))

    # Kiểm tra mật khẩu (hỗ trợ cả plaintext và bcrypt)
    if account['PasswordHash'].startswith('$2b$'):
        valid = bcrypt.checkpw(password.encode('utf-8'), account['PasswordHash'].encode('utf-8'))
    else:
        valid = (password == account['PasswordHash'])
    if not valid:
        flash('Sai username hoặc password.', 'err')
        return redirect(url_for('login'))

    if account['RoleName'] != role:
        flash('Vai trò không khớp. Hãy chọn đúng vai trò.', 'err')
        return redirect(url_for('login'))

    if account['Status'] == 'Inactive':
        flash('Tài khoản đã bị khóa. Vui lòng liên hệ admin.', 'err')
        return redirect(url_for('login'))

    session['user_id'] = account['AccountID']
    session['username'] = account['Username']
    session['role'] = account['RoleName']
    session['full_name'] = get_user_display_name(account)

    execute_query("UPDATE Account SET LastLogin = NOW() WHERE AccountID = %s", (account['AccountID'],))
    flash('Đăng nhập thành công!', 'ok')
    return redirect_by_role(account['RoleName'])

@app.route('/resetpassword', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'GET':
        return render_template('resetpassword.html')

    phone = request.form.get('phone', '').strip()
    new_password = request.form.get('new_password', '').strip()
    confirm = request.form.get('confirm_password', '').strip()

    if new_password != confirm:
        flash('Mật khẩu xác nhận không khớp.', 'err')
        return redirect(url_for('resetpassword'))
    if len(new_password) < 8:
        flash('Mật khẩu phải có ít nhất 8 ký tự.', 'err')
        return redirect(url_for('resetpassword'))

    sql = """
        SELECT a.AccountID FROM Account a
        LEFT JOIN Student s ON a.StudentID = s.StudentID
        LEFT JOIN Lecturer l ON a.LecturerID = l.LecturerID
        WHERE a.PhoneNumber = %s OR s.PhoneNumber = %s OR l.PhoneNumber = %s
    """
    account = execute_query(sql, (phone, phone, phone), fetch_one=True)
    if not account:
        flash('Số điện thoại không tồn tại trong hệ thống.', 'err')
        return redirect(url_for('resetpassword'))

    hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    execute_query("UPDATE Account SET PasswordHash = %s WHERE AccountID = %s", (hashed, account['AccountID']))
    flash('Đặt lại mật khẩu thành công. Vui lòng đăng nhập.', 'ok')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    role = session.get('role')
    if role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif role == 'lecturer':
        return redirect(url_for('lecturer_profile'))
    elif role == 'student':
        return redirect(url_for('student_profile'))
    else:
        flash('Vai trò không xác định.', 'err')
        return redirect(url_for('logout'))

# ---------- 6.1 Admin Dashboard ----------
@app.route('/admin/dashboard', methods=['GET'])
@login_required
@role_required('admin')
def admin_dashboard():
    try:
        total_students = execute_query("SELECT COUNT(*) AS total FROM Student", fetch_one=True)['total']
        total_lecturers = execute_query("SELECT COUNT(*) AS total FROM Lecturer", fetch_one=True)['total']
        total_faculties = execute_query("SELECT COUNT(*) AS total FROM Faculty", fetch_one=True)['total']
        total_majors = execute_query("SELECT COUNT(*) AS total FROM Major", fetch_one=True)['total']

        chart_data = execute_query("""
            SELECT f.FacultyName, COUNT(s.StudentID) AS student_count
            FROM Faculty f
            LEFT JOIN Student s ON f.FacultyID = s.FacultyID
            GROUP BY f.FacultyID
            ORDER BY student_count DESC
        """, fetch_all=True)

        faculty_stats = []
        if chart_data:
            max_count = max(item['student_count'] for item in chart_data)
            for item in chart_data:
                width_percent = int((item['student_count'] / max_count) * 100) if max_count > 0 else 0
                faculty_stats.append({
                    'name': item['FacultyName'],
                    'count': item['student_count'],
                    'width_percent': width_percent
                })

        top_faculties = execute_query("""
            SELECT f.FacultyName,
                   COUNT(s.StudentID) AS total_students,
                   NULL AS head_name
            FROM Faculty f
            LEFT JOIN Student s ON f.FacultyID = s.FacultyID
            GROUP BY f.FacultyID
            ORDER BY total_students DESC
            LIMIT 4
        """, fetch_all=True)

        activities = execute_query("""
            SELECT 
                CONCAT(
                    CASE 
                        WHEN action = 'INSERT' THEN 'Added '
                        WHEN action = 'UPDATE' THEN 'Updated '
                        WHEN action = 'DELETE' THEN 'Deleted '
                        ELSE action 
                    END,
                    target,
                    IFNULL(CONCAT(' (ID ', target_id, ')'), '')
                ) AS activity,
                (SELECT Username FROM Account WHERE AccountID = al.AccountID) AS actor,
                al.timestamp AS time
            FROM ActivityLog al
            ORDER BY al.timestamp DESC
            LIMIT 10
        """, fetch_all=True)

        if not activities:
            activities = [{'activity': 'No recent activities', 'actor': 'System', 'time': ''}]

        return render_template('admin/admin_dashboard.html',
                               total_students=total_students,
                               total_lecturers=total_lecturers,
                               total_faculties=total_faculties,
                               total_majors=total_majors,
                               faculty_stats=faculty_stats,
                               top_faculties=top_faculties,
                               chart_data = chart_data,
                               activities=activities,
                               user_name=session.get('full_name', 'Admin'),
                               role_name='System Administrator')
    except Exception as e:
        import traceback
        traceback.print_exc()  # in lỗi ra console để debug
        flash('Không thể tải dữ liệu thống kê. Vui lòng thử lại sau.', 'err')
        return render_template('admin/admin_dashboard.html',
                               total_students=0,
                               total_lecturers=0,
                               total_faculties=0,
                               total_majors=0,
                               chart_data = [],
                               faculty_stats=[],
                               top_faculties=[],
                               activities=[{'activity': 'Lỗi tải dữ liệu', 'actor': 'System', 'time': ''}],
                               user_name=session.get('full_name', 'Admin'),
                               role_name='System Administrator')

# ============================================================
# 7. LECTURER MODULES
# ============================================================

# ---------- 7.1 Lecturer Profile ----------
@app.route('/lecturer/profile', methods=['GET', 'POST'])
@login_required
@role_required('lecturer')
def lecturer_profile():
    lecturer_id = session.get('username')
    lecturer = execute_query("""
        SELECT l.*, f.FacultyName
        FROM Lecturer l
        LEFT JOIN Faculty f ON l.FacultyID = f.FacultyID
        WHERE l.LecturerID = %s
    """, (lecturer_id,), fetch_one=True)

    if not lecturer:
        flash('Không tìm thấy thông tin giảng viên.', 'err')
        return redirect(url_for('logout'))

    if request.method == 'GET':
        return render_template('lecturer/profile_lecturer.html',
                               lecturer=lecturer,
                               user_name=session.get('full_name', 'Lecturer'),
                               role_name='Lecturer')

    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    if not phone or not email:
        flash('Vui lòng nhập đầy đủ số điện thoại và email.', 'err')
        return redirect(url_for('lecturer_profile'))

    execute_query("UPDATE Lecturer SET PhoneNumber = %s, Email = %s WHERE LecturerID = %s", (phone, email, lecturer_id))
    execute_query("UPDATE Account SET PhoneNumber = %s WHERE LecturerID = %s", (phone, lecturer_id))
    flash('Cập nhật thông tin thành công.', 'ok')
    return redirect(url_for('lecturer_profile'))

# ============================================================
# 8. STUDENT MODULES
# ============================================================

# ---------- 8.1 Student Dashboard ----------
@app.route('/student/dashboard', methods=['GET'])
@login_required
@role_required('student')
def student_dashboard():
    return redirect(url_for('student_profile'))


# ============================================================
# 9. CHẠY ỨNG DỤNG
# ============================================================
if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=8000)