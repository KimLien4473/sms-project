
import re
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

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    flash('Đã đăng xuất.', 'ok')
    return redirect(url_for('login'))

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

# ============================================================
# 6. ADMIN MODULES
# ============================================================

# ---------- 6.1 Admin Dashboard ----------
@app.route('/admin/dashboard', methods=['GET'])
@login_required
@role_required('admin')
def admin_dashboard():
    account_count = execute_query("SELECT COUNT(*) AS total FROM Account", fetch_one=True)['total']
    student_count = execute_query("SELECT COUNT(*) AS total FROM Student", fetch_one=True)['total']
    lecturer_count = execute_query("SELECT COUNT(*) AS total FROM Lecturer", fetch_one=True)['total']
    faculty_count = execute_query("SELECT COUNT(*) AS total FROM Faculty", fetch_one=True)['total']
    major_count = execute_query("SELECT COUNT(*) AS total FROM Major", fetch_one=True)['total']
    subject_count = execute_query("SELECT COUNT(*) AS total FROM Subject", fetch_one=True)['total']

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
               ANY_VALUE((SELECT FullName FROM Lecturer l WHERE l.LecturerID = (SELECT HomeroomLecturerID FROM ClassGroup c WHERE c.ClassID = s.ClassID LIMIT 1))) AS head_name
        FROM Faculty f
        LEFT JOIN Student s ON f.FacultyID = s.FacultyID
        GROUP BY f.FacultyID
        ORDER BY total_students DESC
        LIMIT 4
    """, fetch_all=True)

    activities = execute_query("""
        SELECT 'New student batch imported' AS activity, 'By Admin User' AS actor, NOW() AS time
        UNION ALL
        SELECT 'Course catalog updated', 'System Auto-sync', NOW() - INTERVAL 2 HOUR
        UNION ALL
        SELECT 'Lecturer profile updated', 'By HR Department', NOW() - INTERVAL 5 HOUR
        UNION ALL
        SELECT 'Failed login attempt detected', 'Security Alert', NOW() - INTERVAL 1 DAY
        LIMIT 4
    """, fetch_all=True)

    return render_template('admin/admin_dashboard.html',
                           total_students=student_count,
                           total_lecturers=lecturer_count,
                           total_faculties=faculty_count,
                           total_majors=major_count,
                           total_subjects=subject_count,
                           total_accounts=account_count,
                           faculty_stats=faculty_stats,
                           top_faculties=top_faculties,
                           activities=activities,
                           user_name=session.get('full_name', 'Admin'),
                           role_name='System Administrator')

# ---------- 6.2 Account Management ----------
@app.route('/admin/account_management', methods=['GET'])
@login_required
@role_required('admin')
def admin_accounts():
    search = request.args.get('q', '').strip()
    role_filter = request.args.get('role', '')

    sql = """
        SELECT
            a.AccountID        AS account_id,
            a.Username         AS username,
            a.PhoneNumber      AS phone,
            a.Status           AS status,
            a.IsFirstLogin     AS first_login,
            a.LastLogin        AS last_login,
            r.RoleName         AS role,
            COALESCE(s.FullName, l.FullName, '') AS full_name
        FROM Account a
        JOIN Role r ON a.RoleID = r.RoleID
        LEFT JOIN Student s ON a.StudentID = s.StudentID
        LEFT JOIN Lecturer l ON a.LecturerID = l.LecturerID
        WHERE 1=1
    """
    params = []
    if search:
        sql += " AND (a.Username LIKE %s OR COALESCE(s.FullName, l.FullName) LIKE %s)"
        params.extend([f'%{search}%', f'%{search}%'])
    if role_filter:
        sql += " AND r.RoleName = %s"
        params.append(role_filter)
    sql += " ORDER BY a.AccountID"
    accounts = execute_query(sql, tuple(params), fetch_all=True)

    roles = execute_query("SELECT RoleName FROM Role", fetch_all=True)
    return render_template('admin/account_management.html',
                           accounts=accounts,
                           roles=roles,
                           search=search,
                           role_filter=role_filter,
                           user_name=session.get('full_name', 'Admin'),
                           role_name='System Administrator')

@app.route('/admin/account_management/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_accounts_create():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role_name = request.form.get('role', '').strip()
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()

    if not username or not password or not role_name:
        flash('Vui lòng nhập đầy đủ thông tin bắt buộc.', 'err')
        return redirect(url_for('admin_accounts'))

    exist = execute_query("SELECT AccountID FROM Account WHERE Username = %s", (username,), fetch_one=True)
    if exist:
        flash('Username đã tồn tại.', 'err')
        return redirect(url_for('admin_accounts'))

    role = execute_query("SELECT RoleID FROM Role WHERE RoleName = %s", (role_name,), fetch_one=True)
    if not role:
        flash('Vai trò không hợp lệ.', 'err')
        return redirect(url_for('admin_accounts'))

    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    sql = "INSERT INTO Account (Username, PasswordHash, PhoneNumber, IsFirstLogin, Status, RoleID) VALUES (%s, %s, %s, %s, %s, %s)"
    execute_query(sql, (username, hashed, phone, True, 'Active', role['RoleID']))

    flash('Tạo tài khoản thành công.', 'ok')
    return redirect(url_for('admin_accounts'))

@app.route('/admin/account_management/toggle_status', methods=['POST'])
@login_required
@role_required('admin')
def admin_accounts_toggle_status():
    username = request.form.get('username', '').strip()
    if not username:
        flash('Thiếu thông tin tài khoản.', 'err')
        return redirect(url_for('admin_accounts'))

    account = execute_query("SELECT Status FROM Account WHERE Username = %s", (username,), fetch_one=True)
    if not account:
        flash('Tài khoản không tồn tại.', 'err')
        return redirect(url_for('admin_accounts'))

    new_status = 'Inactive' if account['Status'] == 'Active' else 'Active'
    execute_query("UPDATE Account SET Status = %s WHERE Username = %s", (new_status, username))
    flash(f'Đã {"khóa" if new_status == "Inactive" else "mở khóa"} tài khoản.', 'ok')
    return redirect(url_for('admin_accounts'))

@app.route('/admin/account_management/resetpassword', methods=['POST'])
@login_required
@role_required('admin')
def admin_accounts_reset_password():
    username = request.form.get('username', '').strip()
    if not username:
        flash('Thiếu thông tin tài khoản.', 'err')
        return redirect(url_for('admin_accounts'))

    account = execute_query("SELECT AccountID FROM Account WHERE Username = %s", (username,), fetch_one=True)
    if not account:
        flash('Tài khoản không tồn tại.', 'err')
        return redirect(url_for('admin_accounts'))

    hashed = bcrypt.hashpw('123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    execute_query("UPDATE Account SET PasswordHash = %s WHERE AccountID = %s", (hashed, account['AccountID']))
    flash(f'Đã reset mật khẩu tài khoản {username} thành "123".', 'ok')
    return redirect(url_for('admin_accounts'))

# ---------- 6.3 Student Management ----------
@app.route('/admin/students', methods=['GET'])
@login_required
@role_required('admin')
def admin_students():
    search = request.args.get('q', '').strip()
    faculty_filter = request.args.get('faculty', '')
    major_filter = request.args.get('major', '')

    sql = """
        SELECT s.*, f.FacultyName, m.MajorName, c.ClassName
        FROM Student s
        LEFT JOIN Faculty f ON s.FacultyID = f.FacultyID
        LEFT JOIN Major m ON s.MajorID = m.MajorID
        LEFT JOIN ClassGroup c ON s.ClassID = c.ClassID
        WHERE 1=1
    """
    params = []
    if search:
        sql += " AND (s.StudentID LIKE %s OR s.FullName LIKE %s)"
        params.extend([f'%{search}%', f'%{search}%'])
    if faculty_filter:
        sql += " AND s.FacultyID = %s"
        params.append(faculty_filter)
    if major_filter:
        sql += " AND s.MajorID = %s"
        params.append(major_filter)
    sql += " ORDER BY s.StudentID"
    students = execute_query(sql, tuple(params), fetch_all=True)

    faculties = execute_query("SELECT FacultyID, FacultyName FROM Faculty", fetch_all=True)
    majors = execute_query("SELECT MajorID, MajorName FROM Major", fetch_all=True)
    return render_template('admin/student_management.html',
                           students=students,
                           faculties=faculties,
                           majors=majors,
                           search=search,
                           faculty_filter=faculty_filter,
                           major_filter=major_filter,
                           user_name=session.get('full_name', 'Admin'),
                           role_name='System Administrator')

@app.route('/admin/students/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_students_create():
    student_id = request.form.get('student_id', '').strip()
    full_name = request.form.get('name', '').strip()
    gender = request.form.get('gender', '')
    dob = request.form.get('dob', '')
    faculty_id = request.form.get('faculty', '')
    major_id = request.form.get('major', '')
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    status = request.form.get('status', 'Studying')

    if not student_id or not full_name:
        flash('Vui lòng nhập đầy đủ thông tin bắt buộc.', 'err')
        return redirect(url_for('admin_students'))

    exist = execute_query("SELECT StudentID FROM Student WHERE StudentID = %s", (student_id,), fetch_one=True)
    if exist:
        flash('Mã sinh viên đã tồn tại.', 'err')
        return redirect(url_for('admin_students'))

    enrollment_year = dob[:4] if dob else None
    sql = """
        INSERT INTO Student (StudentID, FullName, DateOfBirth, Gender, PhoneNumber, Email, FacultyID, MajorID, Status, EnrollmentYear)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    execute_query(sql, (student_id, full_name, dob, gender, phone, email, faculty_id, major_id, status, enrollment_year))

    hashed = bcrypt.hashpw('123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    role = execute_query("SELECT RoleID FROM Role WHERE RoleName = 'student'", fetch_one=True)
    if role:
        execute_query("INSERT INTO Account (Username, PasswordHash, PhoneNumber, IsFirstLogin, Status, RoleID, StudentID) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                      (student_id, hashed, phone, True, 'Active', role['RoleID'], student_id))

    flash('Thêm sinh viên thành công.', 'ok')
    return redirect(url_for('admin_students'))

@app.route('/admin/students/edit', methods=['POST'])
@login_required
@role_required('admin')
def admin_students_edit():
    student_id = request.form.get('student_id', '').strip()
    full_name = request.form.get('name', '').strip()
    gender = request.form.get('gender', '')
    dob = request.form.get('dob', '')
    faculty_id = request.form.get('faculty', '')
    major_id = request.form.get('major', '')
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    status = request.form.get('status', 'Studying')

    if not student_id or not full_name:
        flash('Thiếu thông tin.', 'err')
        return redirect(url_for('admin_students'))

    sql = """
        UPDATE Student SET FullName=%s, DateOfBirth=%s, Gender=%s, PhoneNumber=%s,
               Email=%s, FacultyID=%s, MajorID=%s, Status=%s
        WHERE StudentID=%s
    """
    execute_query(sql, (full_name, dob, gender, phone, email, faculty_id, major_id, status, student_id))
    flash('Cập nhật sinh viên thành công.', 'ok')
    return redirect(url_for('admin_students'))

@app.route('/admin/students/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_students_delete():
    student_id = request.form.get('student_id', '').strip()
    if not student_id:
        flash('Thiếu thông tin.', 'err')
        return redirect(url_for('admin_students'))

    execute_query("DELETE FROM Account WHERE StudentID = %s", (student_id,))
    execute_query("DELETE FROM Student WHERE StudentID = %s", (student_id,))
    flash('Xóa sinh viên thành công.', 'ok')
    return redirect(url_for('admin_students'))

# ---------- 6.4 Lecturer Management ----------
EMAIL_DOMAIN = '@gmail.com'
PHONE_REGEX = r'^\d{10}$'

def generate_next_lecturer_id():
    """Sinh mã giảng viên kế tiếp dạng GVxxx dựa theo mã lớn nhất hiện có."""
    last = execute_query("SELECT LecturerID FROM Lecturer ORDER BY LecturerID DESC LIMIT 1", fetch_one=True)
    if not last or not last.get('LecturerID'):
        return 'GV001'
    last_id = last['LecturerID']
    prefix = ''.join(ch for ch in last_id if not ch.isdigit())
    digits = ''.join(ch for ch in last_id if ch.isdigit())
    if not digits:
        return f"{last_id}001"
    next_num = int(digits) + 1
    return f"{prefix}{str(next_num).zfill(len(digits))}"

def normalize_gmail(local_part):
    """Chuẩn hóa email: chỉ lấy phần trước @ do người dùng nhập, luôn gắn đuôi @gmail.com."""
    local_part = (local_part or '').strip()
    if '@' in local_part:
        local_part = local_part.split('@')[0]
    return f"{local_part}{EMAIL_DOMAIN}" if local_part else ''

@app.route('/admin/lecturers', methods=['GET'])
@login_required
@role_required('admin')
def admin_lecturers():
    search = request.args.get('q', '').strip()
    faculty_filter = request.args.get('faculty', '')

    sql = """
        SELECT l.*, f.FacultyName
        FROM Lecturer l
        LEFT JOIN Faculty f ON l.FacultyID = f.FacultyID
        WHERE 1=1
    """
    params = []
    if search:
        sql += " AND (l.LecturerID LIKE %s OR l.FullName LIKE %s)"
        params.extend([f'%{search}%', f'%{search}%'])
    if faculty_filter:
        sql += " AND l.FacultyID = %s"
        params.append(faculty_filter)
    sql += " ORDER BY l.LecturerID"
    lecturers = execute_query(sql, tuple(params), fetch_all=True)

    faculties = execute_query("SELECT FacultyID, FacultyName FROM Faculty", fetch_all=True)
    return render_template('admin/lecturer_management.html',
                           lecturers=lecturers,
                           faculties=faculties,
                           search=search,
                           faculty_filter=faculty_filter,
                           next_lecturer_id=generate_next_lecturer_id(),
                           user_name=session.get('full_name', 'Admin'),
                           role_name='System Administrator')

@app.route('/admin/lecturers/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_lecturers_create():
    # Mã giảng viên LUÔN do hệ thống tự sinh, bỏ qua giá trị người dùng gửi lên (nếu có)
    lecturer_id = generate_next_lecturer_id()
    full_name = request.form.get('name', '').strip()
    faculty_id = request.form.get('faculty', '')
    email = normalize_gmail(request.form.get('email_local', ''))
    phone = request.form.get('phone', '').strip()

    if not full_name:
        flash('Vui lòng nhập đầy đủ thông tin bắt buộc.', 'err')
        return redirect(url_for('admin_lecturers'))

    if not re.match(PHONE_REGEX, phone):
        flash('Số điện thoại phải gồm đúng 10 chữ số.', 'err')
        return redirect(url_for('admin_lecturers'))

    exist = execute_query("SELECT LecturerID FROM Lecturer WHERE LecturerID = %s", (lecturer_id,), fetch_one=True)
    if exist:
        flash('Mã giảng viên đã tồn tại.', 'err')
        return redirect(url_for('admin_lecturers'))

    sql = "INSERT INTO Lecturer (LecturerID, FullName, FacultyID, Email, PhoneNumber) VALUES (%s, %s, %s, %s, %s)"
    execute_query(sql, (lecturer_id, full_name, faculty_id, email, phone))

    hashed = bcrypt.hashpw('123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    role = execute_query("SELECT RoleID FROM Role WHERE RoleName = 'lecturer'", fetch_one=True)
    if role:
        execute_query("INSERT INTO Account (Username, PasswordHash, PhoneNumber, IsFirstLogin, Status, RoleID, LecturerID) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                      (lecturer_id, hashed, phone, True, 'Active', role['RoleID'], lecturer_id))

    flash(f'Thêm giảng viên thành công. Mã giảng viên: {lecturer_id}.', 'ok')
    return redirect(url_for('admin_lecturers'))

@app.route('/admin/lecturers/edit', methods=['POST'])
@login_required
@role_required('admin')
def admin_lecturers_edit():
    lecturer_id = request.form.get('lecturer_id', '').strip()
    full_name = request.form.get('name', '').strip()
    faculty_id = request.form.get('faculty', '')
    email = normalize_gmail(request.form.get('email_local', ''))
    phone = request.form.get('phone', '').strip()

    if not lecturer_id or not full_name:
        flash('Thiếu thông tin.', 'err')
        return redirect(url_for('admin_lecturers'))

    if not re.match(PHONE_REGEX, phone):
        flash('Số điện thoại phải gồm đúng 10 chữ số.', 'err')
        return redirect(url_for('admin_lecturers'))

    sql = "UPDATE Lecturer SET FullName=%s, FacultyID=%s, Email=%s, PhoneNumber=%s WHERE LecturerID=%s"
    execute_query(sql, (full_name, faculty_id, email, phone, lecturer_id))
    flash('Cập nhật giảng viên thành công.', 'ok')
    return redirect(url_for('admin_lecturers'))

@app.route('/admin/lecturers/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_lecturers_delete():
    lecturer_id = request.form.get('lecturer_id', '').strip()
    if not lecturer_id:
        flash('Thiếu thông tin.', 'err')
        return redirect(url_for('admin_lecturers'))

    execute_query("DELETE FROM Account WHERE LecturerID = %s", (lecturer_id,))
    execute_query("DELETE FROM Lecturer WHERE LecturerID = %s", (lecturer_id,))
    flash('Xóa giảng viên thành công.', 'ok')
    return redirect(url_for('admin_lecturers'))

# ---------- 6.5 Faculty Management ----------
@app.route('/admin/faculties', methods=['GET'])
@login_required
@role_required('admin')
def admin_faculties():
    search = request.args.get('q', '').strip()
    sql = "SELECT * FROM Faculty WHERE 1=1"
    params = []
    if search:
        sql += " AND (FacultyID LIKE %s OR FacultyName LIKE %s)"
        params.extend([f'%{search}%', f'%{search}%'])
    sql += " ORDER BY FacultyID"
    faculties = execute_query(sql, tuple(params), fetch_all=True)
    return render_template('admin/faculty_management.html',
                           faculties=faculties,
                           search=search,
                           user_name=session.get('full_name', 'Admin'),
                           role_name='System Administrator')

@app.route('/admin/faculties/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_faculties_create():
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    if not code or not name:
        flash('Vui lòng nhập đầy đủ thông tin.', 'err')
        return redirect(url_for('admin_faculties'))

    exist = execute_query("SELECT FacultyID FROM Faculty WHERE FacultyID = %s", (code,), fetch_one=True)
    if exist:
        flash('Mã khoa đã tồn tại.', 'err')
        return redirect(url_for('admin_faculties'))

    execute_query("INSERT INTO Faculty (FacultyID, FacultyName, Description) VALUES (%s, %s, %s)", (code, name, description))
    flash('Thêm khoa thành công.', 'ok')
    return redirect(url_for('admin_faculties'))

@app.route('/admin/faculties/edit', methods=['POST'])
@login_required
@role_required('admin')
def admin_faculties_edit():
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    if not code or not name:
        flash('Thiếu thông tin.', 'err')
        return redirect(url_for('admin_faculties'))

    execute_query("UPDATE Faculty SET FacultyName=%s, Description=%s WHERE FacultyID=%s", (name, description, code))
    flash('Cập nhật khoa thành công.', 'ok')
    return redirect(url_for('admin_faculties'))

@app.route('/admin/faculties/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_faculties_delete():
    code = request.form.get('code', '').strip()
    if not code:
        flash('Thiếu thông tin.', 'err')
        return redirect(url_for('admin_faculties'))
    try:
        execute_query("DELETE FROM Faculty WHERE FacultyID = %s", (code,))
        flash('Xóa khoa thành công.', 'ok')
    except Exception:
        flash('Không thể xóa khoa vì đang có dữ liệu liên quan.', 'err')
    return redirect(url_for('admin_faculties'))

# ---------- 6.6 Major Management ----------
@app.route('/admin/majors', methods=['GET'])
@login_required
@role_required('admin')
def admin_majors():
    search = request.args.get('q', '').strip()
    sql = """
        SELECT m.*, f.FacultyName
        FROM Major m
        LEFT JOIN Faculty f ON m.FacultyID = f.FacultyID
        WHERE 1=1
    """
    params = []
    if search:
        sql += " AND (m.MajorID LIKE %s OR m.MajorName LIKE %s OR f.FacultyName LIKE %s)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    sql += " ORDER BY m.MajorID"
    majors = execute_query(sql, tuple(params), fetch_all=True)
    faculties = execute_query("SELECT FacultyID, FacultyName FROM Faculty", fetch_all=True)
    return render_template('admin/major_management.html',
                           majors=majors,
                           faculties=faculties,
                           search=search,
                           user_name=session.get('full_name', 'Admin'),
                           role_name='System Administrator')

@app.route('/admin/majors/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_majors_create():
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    faculty_id = request.form.get('faculty', '').strip()
    if not code or not name or not faculty_id:
        flash('Vui lòng nhập đầy đủ thông tin.', 'err')
        return redirect(url_for('admin_majors'))

    exist = execute_query("SELECT MajorID FROM Major WHERE MajorID = %s", (code,), fetch_one=True)
    if exist:
        flash('Mã ngành đã tồn tại.', 'err')
        return redirect(url_for('admin_majors'))

    execute_query("INSERT INTO Major (MajorID, MajorName, FacultyID) VALUES (%s, %s, %s)", (code, name, faculty_id))
    flash('Thêm ngành thành công.', 'ok')
    return redirect(url_for('admin_majors'))

@app.route('/admin/majors/edit', methods=['POST'])
@login_required
@role_required('admin')
def admin_majors_edit():
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    faculty_id = request.form.get('faculty', '').strip()
    if not code or not name or not faculty_id:
        flash('Thiếu thông tin.', 'err')
        return redirect(url_for('admin_majors'))

    execute_query("UPDATE Major SET MajorName=%s, FacultyID=%s WHERE MajorID=%s", (name, faculty_id, code))
    flash('Cập nhật ngành thành công.', 'ok')
    return redirect(url_for('admin_majors'))

@app.route('/admin/majors/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_majors_delete():
    code = request.form.get('code', '').strip()
    if not code:
        flash('Thiếu thông tin.', 'err')
        return redirect(url_for('admin_majors'))
    try:
        execute_query("DELETE FROM Major WHERE MajorID = %s", (code,))
        flash('Xóa ngành thành công.', 'ok')
    except Exception:
        flash('Không thể xóa ngành vì đang có sinh viên thuộc ngành này.', 'err')
    return redirect(url_for('admin_majors'))

# ---------- 6.7 Course Management ----------
@app.route('/admin/courses', methods=['GET'])
@login_required
@role_required('admin')
def admin_courses():
    search = request.args.get('q', '').strip()
    sql = """
        SELECT c.*, f.FacultyName
        FROM Subject c
        LEFT JOIN Faculty f ON c.FacultyID = f.FacultyID
        WHERE 1=1
    """
    params = []
    if search:
        sql += " AND (c.SubjectID LIKE %s OR c.SubjectName LIKE %s)"
        params.extend([f'%{search}%', f'%{search}%'])
    sql += " ORDER BY c.SubjectID"
    courses = execute_query(sql, tuple(params), fetch_all=True)
    faculties = execute_query("SELECT FacultyID, FacultyName FROM Faculty", fetch_all=True)
    return render_template('admin/course_management.html',
                           courses=courses,
                           faculties=faculties,
                           search=search,
                           user_name=session.get('full_name', 'Admin'),
                           role_name='System Administrator')

@app.route('/admin/courses/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_courses_create():
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    credits = request.form.get('credits', '').strip()
    faculty_id = request.form.get('faculty', '').strip()

    if not code or not name or not credits:
        flash('Vui lòng nhập đầy đủ thông tin.', 'err')
        return redirect(url_for('admin_courses'))

    try:
        credits = int(credits)
        if credits <= 0:
            raise ValueError
    except ValueError:
        flash('Số tín chỉ phải là số nguyên dương.', 'err')
        return redirect(url_for('admin_courses'))

    exist = execute_query("SELECT SubjectID FROM Subject WHERE SubjectID = %s", (code,), fetch_one=True)
    if exist:
        flash('Mã môn học đã tồn tại.', 'err')
        return redirect(url_for('admin_courses'))

    execute_query("INSERT INTO Subject (SubjectID, SubjectName, Credits, FacultyID) VALUES (%s, %s, %s, %s)", (code, name, credits, faculty_id))
    flash('Thêm môn học thành công.', 'ok')
    return redirect(url_for('admin_courses'))

@app.route('/admin/courses/edit', methods=['POST'])
@login_required
@role_required('admin')
def admin_courses_edit():
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    credits = request.form.get('credits', '').strip()
    faculty_id = request.form.get('faculty', '').strip()

    if not code or not name or not credits:
        flash('Thiếu thông tin.', 'err')
        return redirect(url_for('admin_courses'))

    try:
        credits = int(credits)
        if credits <= 0:
            raise ValueError
    except ValueError:
        flash('Số tín chỉ phải là số nguyên dương.', 'err')
        return redirect(url_for('admin_courses'))

    execute_query("UPDATE Subject SET SubjectName=%s, Credits=%s, FacultyID=%s WHERE SubjectID=%s", (name, credits, faculty_id, code))
    flash('Cập nhật môn học thành công.', 'ok')
    return redirect(url_for('admin_courses'))

@app.route('/admin/courses/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_courses_delete():
    code = request.form.get('code', '').strip()
    if not code:
        flash('Thiếu thông tin.', 'err')
        return redirect(url_for('admin_courses'))
    try:
        execute_query("DELETE FROM Subject WHERE SubjectID = %s", (code,))
        flash('Xóa môn học thành công.', 'ok')
    except Exception:
        flash('Không thể xóa môn học vì đang có lớp học phần liên quan.', 'err')
    return redirect(url_for('admin_courses'))

# ---------- 6.8 Academic Structure Management ----------
@app.route('/admin/academic_structure', methods=['GET'])
@login_required
@role_required('admin')
def admin_academic_structure():
    homerooms = execute_query("""
        SELECT c.*, l.FullName AS AdvisorName,
               (SELECT COUNT(*) FROM Student s WHERE s.ClassID = c.ClassID) AS StudentCount
        FROM ClassGroup c
        LEFT JOIN Lecturer l ON c.HomeroomLecturerID = l.LecturerID
        ORDER BY c.ClassID
    """, fetch_all=True)

    course_sections = execute_query("""
        SELECT cs.*, s.SubjectName, l.FullName AS LecturerName
        FROM CourseSection cs
        JOIN Subject s ON cs.SubjectID = s.SubjectID
        JOIN Lecturer l ON cs.LecturerID = l.LecturerID
        ORDER BY cs.CourseSectionID
    """, fetch_all=True)

    lecturers = execute_query("SELECT LecturerID, FullName FROM Lecturer ORDER BY FullName", fetch_all=True)
    subjects = execute_query("SELECT SubjectID, SubjectName FROM Subject ORDER BY SubjectName", fetch_all=True)
    faculties = execute_query("SELECT FacultyID, FacultyName FROM Faculty ORDER BY FacultyName", fetch_all=True)
    semesters = execute_query("SELECT DISTINCT Semester FROM CourseSection ORDER BY Semester DESC", fetch_all=True)

    return render_template('admin/academic_structure_management.html',
                           homerooms=homerooms,
                           course_sections=course_sections,
                           lecturers=lecturers,
                           subjects=subjects,
                           faculties=faculties,
                           semesters=semesters,
                           user_name=session.get('full_name', 'Admin'),
                           role_name='System Administrator')

# Homeroom CRUD
@app.route('/admin/academic_structure/homeroom/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_homeroom_create():
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    advisor = request.form.get('advisor', '').strip()
    capacity = request.form.get('capacity', '').strip()
    academic_year = request.form.get('academic_year', '').strip()
    semester = request.form.get('semester', '').strip()

    if not code or not name:
        flash('Vui lòng nhập đầy đủ thông tin bắt buộc.', 'err')
        return redirect(url_for('admin_academic_structure'))

    capacity = int(capacity) if capacity else None
    sql = """
        INSERT INTO ClassGroup (ClassID, ClassName, MaxSize, HomeroomLecturerID, AcademicYear, Semester)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    execute_query(sql, (code, name, capacity, advisor, academic_year, semester))
    flash('Thêm lớp homeroom thành công.', 'ok')
    return redirect(url_for('admin_academic_structure'))

@app.route('/admin/academic_structure/homeroom/edit', methods=['POST'])
@login_required
@role_required('admin')
def admin_homeroom_edit():
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    advisor = request.form.get('advisor', '').strip()
    capacity = request.form.get('capacity', '').strip()
    academic_year = request.form.get('academic_year', '').strip()
    semester = request.form.get('semester', '').strip()

    if not code or not name:
        flash('Thiếu thông tin.', 'err')
        return redirect(url_for('admin_academic_structure'))

    capacity = int(capacity) if capacity else None
    sql = """
        UPDATE ClassGroup SET ClassName=%s, MaxSize=%s, HomeroomLecturerID=%s, AcademicYear=%s, Semester=%s WHERE ClassID=%s
    """
    execute_query(sql, (name, capacity, advisor, academic_year, semester, code))
    flash('Cập nhật lớp homeroom thành công.', 'ok')
    return redirect(url_for('admin_academic_structure'))

@app.route('/admin/academic_structure/homeroom/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_homeroom_delete():
    code = request.form.get('code', '').strip()
    if not code:
        flash('Thiếu thông tin.', 'err')
        return redirect(url_for('admin_academic_structure'))
    try:
        execute_query("DELETE FROM ClassGroup WHERE ClassID = %s", (code,))
        flash('Xóa lớp homeroom thành công.', 'ok')
    except Exception:
        flash('Không thể xóa lớp homeroom vì đang có sinh viên thuộc lớp này.', 'err')
    return redirect(url_for('admin_academic_structure'))

# Course Section CRUD
@app.route('/admin/academic_structure/course_section/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_course_section_create():
    code = request.form.get('code', '').strip()
    course = request.form.get('course', '').strip()
    lecturer = request.form.get('lecturer', '').strip()
    semester = request.form.get('semester', '').strip()
    capacity = request.form.get('capacity', '').strip()

    if not code or not course or not lecturer or not semester:
        flash('Vui lòng nhập đầy đủ thông tin bắt buộc.', 'err')
        return redirect(url_for('admin_academic_structure'))

    capacity = int(capacity) if capacity else None
    sql = """
        INSERT INTO CourseSection (CourseSectionID, SubjectID, LecturerID, Semester, MaxSize)
        VALUES (%s, %s, %s, %s, %s)
    """
    execute_query(sql, (code, course, lecturer, semester, capacity))
    flash('Thêm lớp học phần thành công.', 'ok')
    return redirect(url_for('admin_academic_structure'))

@app.route('/admin/academic_structure/course_section/edit', methods=['POST'])
@login_required
@role_required('admin')
def admin_course_section_edit():
    code = request.form.get('code', '').strip()
    course = request.form.get('course', '').strip()
    lecturer = request.form.get('lecturer', '').strip()
    semester = request.form.get('semester', '').strip()
    capacity = request.form.get('capacity', '').strip()

    if not code or not course or not lecturer or not semester:
        flash('Thiếu thông tin.', 'err')
        return redirect(url_for('admin_academic_structure'))

    capacity = int(capacity) if capacity else None
    sql = """
        UPDATE CourseSection SET SubjectID=%s, LecturerID=%s, Semester=%s, MaxSize=%s WHERE CourseSectionID=%s
    """
    execute_query(sql, (course, lecturer, semester, capacity, code))
    flash('Cập nhật lớp học phần thành công.', 'ok')
    return redirect(url_for('admin_academic_structure'))

@app.route('/admin/academic_structure/course_section/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_course_section_delete():
    code = request.form.get('code', '').strip()
    if not code:
        flash('Thiếu thông tin.', 'err')
        return redirect(url_for('admin_academic_structure'))
    try:
        execute_query("DELETE FROM CourseSection WHERE CourseSectionID = %s", (code,))
        flash('Xóa lớp học phần thành công.', 'ok')
    except Exception:
        flash('Không thể xóa lớp học phần vì đang có đăng ký liên quan.', 'err')
    return redirect(url_for('admin_academic_structure'))

# ---------- 6.9 Statistics ----------
@app.route('/admin/statistics', methods=['GET'])
@login_required
@role_required('admin')
def admin_statistics():
    total_students = execute_query("SELECT COUNT(*) AS total FROM Student", fetch_one=True)['total']
    total_lecturers = execute_query("SELECT COUNT(*) AS total FROM Lecturer", fetch_one=True)['total']
    total_faculties = execute_query("SELECT COUNT(*) AS total FROM Faculty", fetch_one=True)['total']
    total_majors = execute_query("SELECT COUNT(*) AS total FROM Major", fetch_one=True)['total']
    total_subjects = execute_query("SELECT COUNT(*) AS total FROM Subject", fetch_one=True)['total']
    total_sections = execute_query("SELECT COUNT(*) AS total FROM CourseSection", fetch_one=True)['total']
    total_accounts = execute_query("SELECT COUNT(*) AS total FROM Account", fetch_one=True)['total']

    chart_data = execute_query("""
        SELECT f.FacultyName, COUNT(s.StudentID) AS student_count
        FROM Faculty f
        LEFT JOIN Student s ON f.FacultyID = s.FacultyID
        GROUP BY f.FacultyID
        ORDER BY student_count DESC
    """, fetch_all=True)

    enrollment_chart_data = execute_query("""
        SELECT EnrollmentYear AS year, COUNT(*) AS count
        FROM Student
        WHERE EnrollmentYear IS NOT NULL
        GROUP BY EnrollmentYear
        ORDER BY EnrollmentYear ASC
    """, fetch_all=True)

    faculty_distribution = execute_query("""
        SELECT f.FacultyName,
               COUNT(DISTINCT s.StudentID) AS student_count,
               COUNT(DISTINCT l.LecturerID) AS lecturer_count,
               COUNT(DISTINCT m.MajorID) AS major_count
        FROM Faculty f
        LEFT JOIN Student s ON f.FacultyID = s.FacultyID
        LEFT JOIN Lecturer l ON f.FacultyID = l.FacultyID
        LEFT JOIN Major m ON f.FacultyID = m.FacultyID
        GROUP BY f.FacultyID
        ORDER BY student_count DESC
    """, fetch_all=True)

    year_filter = request.args.get('year', 'all')
    semester_filter = request.args.get('semester', 'all')

    enrollment_years = execute_query("""
        SELECT DISTINCT YEAR(RegistrationDate) AS year
        FROM CourseRegistration
        ORDER BY year DESC
    """, fetch_all=True)

    return render_template('admin/statistics.html',
                           total_students=total_students,
                           total_lecturers=total_lecturers,
                           total_faculties=total_faculties,
                           total_majors=total_majors,
                           total_subjects=total_subjects,
                           total_sections=total_sections,
                           total_accounts=total_accounts,
                           chart_data=chart_data,
                           enrollment_chart_data=enrollment_chart_data,
                           faculty_distribution=faculty_distribution,
                           year_filter=year_filter,
                           semester_filter=semester_filter,
                           enrollment_years=enrollment_years,
                           user_name=session.get('full_name', 'Admin'),
                           role_name='System Administrator')

# ---------- 6.10 Admin Profile ----------
@app.route('/admin/profile', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_profile():
    account = get_account_by_username(session.get('username'))
    if request.method == 'GET':
        return render_template('admin/personal_profile.html',
                               account=account,
                               user_name=session.get('full_name', 'Admin'),
                               role_name='System Administrator')
    phone = request.form.get('phone', '').strip()
    if phone:
        execute_query("UPDATE Account SET PhoneNumber = %s WHERE AccountID = %s", (phone, account['AccountID']))
        flash('Cập nhật thông tin thành công.', 'ok')
    else:
        flash('Số điện thoại không được để trống.', 'err')
    return redirect(url_for('admin_profile'))

# ---------- 6.11 Admin Change Password ----------
@app.route('/admin/change_password', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_change_password():
    if request.method == 'GET':
        return render_template('admin/change_password.html',
                               user_name=session.get('full_name', 'Admin'),
                               role_name='System Administrator')

    current = request.form.get('current_password', '').strip()
    new_pass = request.form.get('new_password', '').strip()
    confirm = request.form.get('confirm_password', '').strip()

    if new_pass != confirm:
        flash('Mật khẩu xác nhận không khớp.', 'err')
        return redirect(url_for('admin_change_password'))
    if len(new_pass) < 8:
        flash('Mật khẩu mới phải có ít nhất 8 ký tự.', 'err')
        return redirect(url_for('admin_change_password'))

    account = execute_query("SELECT PasswordHash FROM Account WHERE AccountID = %s", (session['user_id'],), fetch_one=True)
    if not account:
        flash('Tài khoản không tồn tại.', 'err')
        return redirect(url_for('admin_change_password'))

    if account['PasswordHash'].startswith('$2b$'):
        valid = bcrypt.checkpw(current.encode('utf-8'), account['PasswordHash'].encode('utf-8'))
    else:
        valid = (current == account['PasswordHash'])
    if not valid:
        flash('Mật khẩu hiện tại không đúng.', 'err')
        return redirect(url_for('admin_change_password'))

    hashed = bcrypt.hashpw(new_pass.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    execute_query("UPDATE Account SET PasswordHash = %s WHERE AccountID = %s", (hashed, session['user_id']))
    flash('Đổi mật khẩu thành công.', 'ok')
    return redirect(url_for('admin_profile'))

# ---------- 6.12 Admin Logout ----------
@app.route('/admin/logout', methods=['GET', 'POST']) 
@login_required
def admin_logout():
    if request.method == 'GET':
        session.clear()
        flash('Đã đăng xuất thành công.', 'ok')
        return redirect(url_for('login'))
        
    return render_template('admin/logout.html',
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

# ---------- 7.2 Learning Records ----------
@app.route('/lecturer/learning_records', methods=['GET'])
@login_required
@role_required('lecturer')
def lecturer_learning_records():
    lecturer_id = session.get('username')
    sections = execute_query("""
        SELECT cs.*, s.SubjectName,
               (SELECT COUNT(*) FROM CourseRegistration WHERE CourseSectionID = cs.CourseSectionID AND Status = 'enrolled') AS student_count
        FROM CourseSection cs
        JOIN Subject s ON cs.SubjectID = s.SubjectID
        WHERE cs.LecturerID = %s
        ORDER BY cs.Semester DESC, cs.CourseSectionID
    """, (lecturer_id,), fetch_all=True)

    selected_section = request.args.get('section_id')
    if not selected_section and sections:
        selected_section = sections[0]['CourseSectionID']

    students = []
    attendance_data = {}
    grades_data = {}
    today = datetime.now().date()

    if selected_section:
        students = execute_query("""
            SELECT r.RegistrationID, s.StudentID, s.FullName, s.Email, s.PhoneNumber
            FROM CourseRegistration r
            JOIN Student s ON r.StudentID = s.StudentID
            WHERE r.CourseSectionID = %s AND r.Status = 'enrolled'
            ORDER BY s.StudentID
        """, (selected_section,), fetch_all=True)

        for stu in students:
            att = execute_query("SELECT Status FROM Attendance WHERE RegistrationID = %s AND AttendanceDate = %s",
                                (stu['RegistrationID'], today), fetch_one=True)
            attendance_data[stu['RegistrationID']] = att['Status'] if att else None

            grade = execute_query("SELECT ProcessScore, FinalScore, AverageScore, GradeStatus FROM Grade WHERE RegistrationID = %s",
                                  (stu['RegistrationID'],), fetch_one=True)
            if grade:
                grades_data[stu['RegistrationID']] = grade

    return render_template('lecturer/learning_records_management.html',
                           sections=sections,
                           selected_section=selected_section,
                           students=students,
                           attendance_data=attendance_data,
                           grades_data=grades_data,
                           today=today,
                           user_name=session.get('full_name', 'Lecturer'),
                           role_name='Lecturer')

@app.route('/lecturer/learning_records/select', methods=['POST'])
@login_required
@role_required('lecturer')
def lecturer_select_section():
    section_id = request.form.get('section_id', '').strip()
    if section_id:
        return redirect(url_for('lecturer_learning_records', section_id=section_id))
    return redirect(url_for('lecturer_learning_records'))

@app.route('/lecturer/attendance/save', methods=['POST'])
@login_required
@role_required('lecturer')
def lecturer_attendance_save():
    section_id = request.form.get('course_section_id', '').strip()
    date_str = request.form.get('date', '').strip()
    if not section_id or not date_str:
        flash('Thiếu thông tin.', 'err')
        return redirect(url_for('lecturer_learning_records'))

    try:
        att_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Ngày không hợp lệ.', 'err')
        return redirect(url_for('lecturer_learning_records'))

    lecturer_id = session.get('username')
    check = execute_query("SELECT CourseSectionID FROM CourseSection WHERE CourseSectionID = %s AND LecturerID = %s",
                          (section_id, lecturer_id), fetch_one=True)
    if not check:
        flash('Bạn không có quyền điểm danh lớp học phần này.', 'err')
        return redirect(url_for('lecturer_learning_records'))

    registrations = execute_query("SELECT RegistrationID FROM CourseRegistration WHERE CourseSectionID = %s AND Status = 'enrolled'",
                                  (section_id,), fetch_all=True)
    for reg in registrations:
        status_key = f'attendance_{reg["RegistrationID"]}'
        status = request.form.get(status_key, '').strip()
        if status in ('Present', 'Absent'):
            exist = execute_query("SELECT AttendanceID FROM Attendance WHERE RegistrationID = %s AND AttendanceDate = %s",
                                  (reg['RegistrationID'], att_date), fetch_one=True)
            if exist:
                execute_query("UPDATE Attendance SET Status = %s WHERE AttendanceID = %s", (status, exist['AttendanceID']))
            else:
                execute_query("INSERT INTO Attendance (RegistrationID, AttendanceDate, Status) VALUES (%s, %s, %s)",
                              (reg['RegistrationID'], att_date, status))

    flash('Điểm danh đã được lưu.', 'ok')
    return redirect(url_for('lecturer_learning_records', section_id=section_id))

@app.route('/lecturer/grades/save', methods=['POST'])
@login_required
@role_required('lecturer')
def lecturer_grades_save():
    section_id = request.form.get('course_section_id', '').strip()
    if not section_id:
        flash('Thiếu thông tin lớp học phần.', 'err')
        return redirect(url_for('lecturer_learning_records'))

    lecturer_id = session.get('username')
    check = execute_query("SELECT CourseSectionID FROM CourseSection WHERE CourseSectionID = %s AND LecturerID = %s",
                          (section_id, lecturer_id), fetch_one=True)
    if not check:
        flash('Bạn không có quyền nhập điểm cho lớp học phần này.', 'err')
        return redirect(url_for('lecturer_learning_records'))

    registrations = execute_query("SELECT RegistrationID FROM CourseRegistration WHERE CourseSectionID = %s AND Status = 'enrolled'",
                                  (section_id,), fetch_all=True)
    for reg in registrations:
        rid = reg['RegistrationID']
        process = request.form.get(f'process_{rid}', '').strip()
        final = request.form.get(f'final_{rid}', '').strip()

        process_val = float(process) if process else None
        final_val = float(final) if final else None

        if process_val is not None and (process_val < 0 or process_val > 10):
            flash(f'Điểm quá trình của sinh viên {rid} không hợp lệ (0-10).', 'err')
            return redirect(url_for('lecturer_learning_records', section_id=section_id))
        if final_val is not None and (final_val < 0 or final_val > 10):
            flash(f'Điểm cuối kỳ của sinh viên {rid} không hợp lệ (0-10).', 'err')
            return redirect(url_for('lecturer_learning_records', section_id=section_id))

        avg_val = None
        if process_val is not None and final_val is not None:
            avg_val = round(process_val * 0.4 + final_val * 0.6, 2)

        exist = execute_query("SELECT GradeID FROM Grade WHERE RegistrationID = %s", (rid,), fetch_one=True)
        if exist:
            execute_query("UPDATE Grade SET ProcessScore=%s, FinalScore=%s, AverageScore=%s, GradeStatus='Draft' WHERE GradeID=%s",
                          (process_val, final_val, avg_val, exist['GradeID']))
        else:
            execute_query("INSERT INTO Grade (RegistrationID, ProcessScore, FinalScore, AverageScore, GradeStatus) VALUES (%s, %s, %s, %s, 'Draft')",
                          (rid, process_val, final_val, avg_val))

    flash('Điểm đã được lưu.', 'ok')
    return redirect(url_for('lecturer_learning_records', section_id=section_id))

# ---------- 7.3 Lecturer Change Password ----------
@app.route('/lecturer/change_password', methods=['GET', 'POST'])
@login_required
@role_required('lecturer')
def lecturer_change_password():
    if request.method == 'GET':
        return render_template('lecturer/change_password_lecturer.html',
                               user_name=session.get('full_name', 'Lecturer'),
                               role_name='Lecturer')

    current = request.form.get('current_password', '').strip()
    new_pass = request.form.get('new_password', '').strip()
    confirm = request.form.get('confirm_password', '').strip()

    if new_pass != confirm:
        flash('Mật khẩu xác nhận không khớp.', 'err')
        return redirect(url_for('lecturer_change_password'))
    if len(new_pass) < 8:
        flash('Mật khẩu mới phải có ít nhất 8 ký tự.', 'err')
        return redirect(url_for('lecturer_change_password'))

    account = execute_query("SELECT PasswordHash FROM Account WHERE AccountID = %s", (session['user_id'],), fetch_one=True)
    if not account:
        flash('Tài khoản không tồn tại.', 'err')
        return redirect(url_for('lecturer_change_password'))

    if account['PasswordHash'].startswith('$2b$'):
        valid = bcrypt.checkpw(current.encode('utf-8'), account['PasswordHash'].encode('utf-8'))
    else:
        valid = (current == account['PasswordHash'])
    if not valid:
        flash('Mật khẩu hiện tại không đúng.', 'err')
        return redirect(url_for('lecturer_change_password'))

    hashed = bcrypt.hashpw(new_pass.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    execute_query("UPDATE Account SET PasswordHash = %s WHERE AccountID = %s", (hashed, session['user_id']))
    flash('Đổi mật khẩu thành công.', 'ok')
    return redirect(url_for('lecturer_profile'))

# ---------- 7.4 Lecturer Logout ----------
@app.route('/lecturer/logout', methods=['GET', 'POST']) 
@login_required
def lecturer_logout():
    if request.method == 'GET':
        session.clear()
        flash('Đã đăng xuất thành công.', 'ok')
        return redirect(url_for('login'))
        
    return render_template('lecturer/logout_lecturer.html', 
                           user_name=session.get('full_name', 'Lecturer'),
                           role_name='Lecturer')

# ============================================================
# 8. STUDENT MODULES
# ============================================================

# ---------- 8.1 Student Dashboard ----------
@app.route('/student/dashboard', methods=['GET'])
@login_required
@role_required('student')
def student_dashboard():
    return redirect(url_for('student_profile'))

# ---------- 8.2 Student Profile ----------
@app.route('/student/profile', methods=['GET', 'POST'])
@login_required
@role_required('student')
def student_profile():
    student_id = session.get('username')
    student = execute_query("SELECT * FROM Student WHERE StudentID = %s", (student_id,), fetch_one=True)
    if not student:
        flash('Không tìm thấy thông tin sinh viên.', 'err')
        return redirect(url_for('logout'))

    if request.method == 'GET':
        faculty = execute_query("SELECT FacultyName FROM Faculty WHERE FacultyID = %s", (student.get('FacultyID'),), fetch_one=True)
        major = execute_query("SELECT MajorName FROM Major WHERE MajorID = %s", (student.get('MajorID'),), fetch_one=True)
        return render_template('student/profile_student.html',
                               student=student,
                               faculty_name=faculty['FacultyName'] if faculty else '',
                               major_name=major['MajorName'] if major else '',
                               user_name=session.get('full_name', 'Student'),
                               role_name='Student')

    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    if not phone or not email:
        flash('Vui lòng nhập đầy đủ số điện thoại và email.', 'err')
        return redirect(url_for('student_profile'))

    execute_query("UPDATE Student SET PhoneNumber = %s, Email = %s WHERE StudentID = %s", (phone, email, student_id))
    execute_query("UPDATE Account SET PhoneNumber = %s WHERE StudentID = %s", (phone, student_id))
    flash('Cập nhật thông tin thành công.', 'ok')
    return redirect(url_for('student_profile'))

# ---------- 8.3 Learning Progress ----------
@app.route('/student/learning_progress', methods=['GET', 'POST'])
@login_required
@role_required('student')
def student_learning_progress():
    student_id = session.get('username')
    registrations = execute_query("""
        SELECT r.RegistrationID, r.CourseSectionID, cs.Semester, cs.AcademicYear,
               s.SubjectID, s.SubjectName, s.Credits,
               g.ProcessScore, g.FinalScore, g.AverageScore, g.GradeStatus,
               g.AcademicRank
        FROM CourseRegistration r
        JOIN CourseSection cs ON r.CourseSectionID = cs.CourseSectionID
        JOIN Subject s ON cs.SubjectID = s.SubjectID
        LEFT JOIN Grade g ON r.RegistrationID = g.RegistrationID
        WHERE r.StudentID = %s AND r.Status = 'enrolled'
        ORDER BY cs.Semester DESC, s.SubjectName
    """, (student_id,), fetch_all=True)

    total_credits = 0
    total_points = 0.0
    for reg in registrations:
        if reg['AverageScore'] is not None:
            total_credits += reg['Credits']
            total_points += float(reg['AverageScore']) * int(reg['Credits'])
    gpa = round(total_points / total_credits, 2) if total_credits > 0 else 0.0

    standing = 'Weak'
    if gpa >= 9.0:
        standing = 'Excellent'
    elif gpa >= 8.0:
        standing = 'Good'
    elif gpa >= 6.5:
        standing = 'Fair'
    elif gpa >= 5.0:
        standing = 'Average'

    earned_credits = 0
    for reg in registrations:
        if reg['AverageScore'] is not None and reg['AverageScore'] >= 5.0:
            earned_credits += reg['Credits']

    attendances = execute_query("""
        SELECT a.AttendanceDate, a.Status, s.SubjectName
        FROM Attendance a
        JOIN CourseRegistration r ON a.RegistrationID = r.RegistrationID
        JOIN CourseSection cs ON r.CourseSectionID = cs.CourseSectionID
        JOIN Subject s ON cs.SubjectID = s.SubjectID
        WHERE r.StudentID = %s
        ORDER BY a.AttendanceDate DESC
        LIMIT 5
    """, (student_id,), fetch_all=True)

    all_attendance = execute_query("SELECT a.Status FROM Attendance a JOIN CourseRegistration r ON a.RegistrationID = r.RegistrationID WHERE r.StudentID = %s",
                                   (student_id,), fetch_all=True)
    total_attended = len(all_attendance)
    total_present = sum(1 for att in all_attendance if att['Status'] == 'Present')
    attendance_rate = round((total_present / total_attended) * 100) if total_attended > 0 else 0

    grades_list = []
    for reg in registrations:
        result = 'Pending'
        if reg['AverageScore'] is not None:
            result = 'Pass' if reg['AverageScore'] >= 5.0 else 'Fail'
        grades_list.append({
            'SubjectName': reg['SubjectName'],
            'SubjectCode': reg['SubjectID'],
            'Credits': reg['Credits'],
            'ProcessScore': reg['ProcessScore'] if reg['ProcessScore'] is not None else '-',
            'FinalScore': reg['FinalScore'] if reg['FinalScore'] is not None else '-',
            'AverageScore': reg['AverageScore'] if reg['AverageScore'] is not None else '-',
            'Result': result
        })

    return render_template('student/learning_progress_student.html',
                           gpa=gpa,
                           standing=standing,
                           earned_credits=earned_credits,
                           attendance_rate=attendance_rate,
                           grades=grades_list,
                           attendances=attendances,
                           user_name=session.get('full_name', 'Student'),
                           role_name='Student')

# ---------- 8.4 Student Change Password ----------
@app.route('/student/change_password', methods=['GET', 'POST'])
@login_required
@role_required('student')
def student_change_password():
    if request.method == 'GET':
        return render_template('student/change_password_student.html',
                               user_name=session.get('full_name', 'Student'),
                               role_name='Student')

    current = request.form.get('current_password', '').strip()
    new_pass = request.form.get('new_password', '').strip()
    confirm = request.form.get('confirm_password', '').strip()

    if new_pass != confirm:
        flash('Mật khẩu xác nhận không khớp.', 'err')
        return redirect(url_for('student_change_password'))
    if len(new_pass) < 8:
        flash('Mật khẩu mới phải có ít nhất 8 ký tự.', 'err')
        return redirect(url_for('student_change_password'))

    account = execute_query("SELECT PasswordHash FROM Account WHERE AccountID = %s", (session['user_id'],), fetch_one=True)
    if not account:
        flash('Tài khoản không tồn tại.', 'err')
        return redirect(url_for('student_change_password'))

    if account['PasswordHash'].startswith('$2b$'):
        valid = bcrypt.checkpw(current.encode('utf-8'), account['PasswordHash'].encode('utf-8'))
    else:
        valid = (current == account['PasswordHash'])
    if not valid:
        flash('Mật khẩu hiện tại không đúng.', 'err')
        return redirect(url_for('student_change_password'))

    hashed = bcrypt.hashpw(new_pass.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    execute_query("UPDATE Account SET PasswordHash = %s WHERE AccountID = %s", (hashed, session['user_id']))
    flash('Đổi mật khẩu thành công.', 'ok')
    return redirect(url_for('student_profile'))

# ---------- 8.5 Student Logout ----------
@app.route('/student/logout', methods=['GET', 'POST']) 
@login_required
def student_logout():
    if request.method == 'GET':
        session.clear()
        flash('Đã đăng xuất thành công.', 'ok')
        return redirect(url_for('login'))
        
    return render_template('student/logout_student.html', 
                           user_name=session.get('full_name', 'Student'),
                           role_name='Student')

# ============================================================
# 9. CHẠY ỨNG DỤNG
# ============================================================
if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=8000)