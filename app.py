import bcrypt
import re
import os
from datetime import datetime
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for, session, flash, jsonify)
import pymysql
from pymysql.cursors import DictCursor

# ============================================================
# 1. CẤU HÌNH FLASK VÀ DATABASE
# ============================================================
app = Flask(__name__)
app.secret_key = 'your-secret-key-here'          # Thay đổi trong production
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024
app.config.setdefault('UPLOAD_FOLDER', os.path.join(app.root_path, 'static'))
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'avatars'), exist_ok=True)

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', '123456'),
    'database': os.getenv('DB_NAME', 'sms_db'),
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
    if account['RoleName'] == 'student' and account.get('StudentID'):
        return execute_query("SELECT * FROM Student WHERE StudentID = %s",
                             (account['StudentID'],), fetch_one=True)
    elif account['RoleName'] == 'lecturer' and account.get('LecturerID'):
        return execute_query("SELECT * FROM Lecturer WHERE LecturerID = %s",
                             (account['LecturerID'],), fetch_one=True)
    return None

def get_user_display_name(account):
    if account['RoleName'] == 'student' and account.get('StudentID'):
        user = get_user_info(account)
        return user['FullName'] if user else account['Username']
    elif account['RoleName'] == 'lecturer' and account.get('LecturerID'):
        user = get_user_info(account)
        return user['FullName'] if user else account['Username']
    return account['Username']

def redirect_by_role(role):
    if role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif role == 'lecturer':
        return redirect(url_for('lecturer_profile'))
    elif role == 'student':
        return redirect(url_for('student_profile'))
    flash('Vai trò không xác định.', 'err')
    return redirect(url_for('logout'))

# ---------- Hàm dùng cho Student ----------
def get_student_profile(student_id):
    sql = """
        SELECT s.*, f.FacultyName, m.MajorName, c.ClassName
        FROM Student s
        LEFT JOIN Faculty f ON s.FacultyID = f.FacultyID
        LEFT JOIN Major m ON s.MajorID = m.MajorID
        LEFT JOIN ClassGroup c ON s.ClassID = c.ClassID
        WHERE s.StudentID = %s
    """
    return execute_query(sql, (student_id,), fetch_one=True)

PHONE_REGEX = re.compile(r'^0\d{9,10}$')
EMAIL_REGEX = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

def validate_contact_data(phone, email):
    if not phone or not email:
        return False, 'Vui lòng nhập đầy đủ Phone Number và Email.'
    if not PHONE_REGEX.match(phone):
        return False, 'Phone Number không đúng định dạng (ví dụ: 0912345678).'
    if not EMAIL_REGEX.match(email):
        return False, 'Email không đúng định dạng (ví dụ: ten@domain.com).'
    return True, None

def check_class_capacity(class_id, exclude_student_id=None):
    if not class_id:
        return True, None
    class_info = execute_query(
        "SELECT ClassID, ClassName, MaximumCapacity FROM ClassGroup WHERE ClassID = %s",
        (class_id,), fetch_one=True
    )
    if not class_info:
        return False, 'Lớp học không tồn tại trên hệ thống.'
    max_capacity = class_info.get('MaximumCapacity')
    if max_capacity is None:
        return True, None
    count_sql = "SELECT COUNT(*) AS cnt FROM Student WHERE ClassID = %s"
    params = [class_id]
    if exclude_student_id:
        count_sql += " AND StudentID != %s"
        params.append(exclude_student_id)
    result = execute_query(count_sql, tuple(params), fetch_one=True)
    current_count = result['cnt'] if result else 0
    if current_count >= max_capacity:
        return False, (f"Lớp {class_info['ClassName']} đã đạt sỉ số tối đa "
                       f"({max_capacity}/{max_capacity}). Không thể thêm sinh viên.")
    return True, None

# ---------- Hàm dùng cho Lecturer ----------
EMAIL_DOMAIN = '@gmail.com'
PHONE_REGEX_LECTURER = r'^\d{10}$'

def generate_next_lecturer_id():
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
    local_part = (local_part or '').strip()
    if '@' in local_part:
        local_part = local_part.split('@')[0]
    return f"{local_part}{EMAIL_DOMAIN}" if local_part else ''

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

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'role' not in session or session['role'] not in roles:
                flash('Bạn không có quyền truy cập trang này.', 'err')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator

# ============================================================
# 5. XÁC THỰC (LOGIN, LOGOUT, RESET PASSWORD)
# ============================================================
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect_by_role(session.get('role'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        if 'user_id' in session:
            return redirect_by_role(session.get('role'))
        return render_template('login.html')

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'admin')

    if not username or not password:
        flash('Vui lòng nhập đầy đủ thông tin.', 'err')
        return redirect(url_for('login'))

    account = get_account_by_username(username)
    if not account:
        flash('Sai username hoặc password.', 'err')
        return redirect(url_for('login'))

    # Kiểm tra mật khẩu (hỗ trợ plaintext và bcrypt)
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

    execute_query("UPDATE Account SET LastLogin = NOW() WHERE AccountID = %s",
                  (account['AccountID'],))
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
    execute_query("UPDATE Account SET PasswordHash = %s WHERE AccountID = %s",
                  (hashed, account['AccountID']))
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
    flash('Vai trò không xác định.', 'err')
    return redirect(url_for('logout'))

# ============================================================
# 6. ADMIN MODULE
# ============================================================

# ---------- 6.1 Dashboard ----------
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
                               chart_data=chart_data,
                               activities=activities,
                               user_name=session.get('full_name', 'Admin'),
                               role_name='System Administrator')
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash('Không thể tải dữ liệu thống kê. Vui lòng thử lại sau.', 'err')
        return render_template('admin/admin_dashboard.html',
                               total_students=0,
                               total_lecturers=0,
                               total_faculties=0,
                               total_majors=0,
                               chart_data=[],
                               faculty_stats=[],
                               top_faculties=[],
                               activities=[{'activity': 'Lỗi tải dữ liệu', 'actor': 'System', 'time': ''}],
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
    role_name = request.form.get('role', '').strip()
    phone = request.form.get('phone', '').strip()

    if role_name not in ['admin', 'lecturer', 'student']:
        flash('Vai trò không hợp lệ.', 'err')
        return redirect(url_for('admin_accounts'))

    role = execute_query("SELECT RoleID FROM Role WHERE RoleName = %s", (role_name,), fetch_one=True)
    if not role:
        flash('Vai trò không tồn tại trong hệ thống.', 'err')
        return redirect(url_for('admin_accounts'))

    student_id = None
    lecturer_id = None
    username = None

    if role_name == 'admin':
        username = request.form.get('username', '').strip()
        if not username:
            flash('Vui lòng nhập tên đăng nhập cho Admin.', 'err')
            return redirect(url_for('admin_accounts'))
        exist = execute_query("SELECT AccountID FROM Account WHERE Username = %s", (username,), fetch_one=True)
        if exist:
            flash('Tên đăng nhập đã tồn tại.', 'err')
            return redirect(url_for('admin_accounts'))

    elif role_name == 'student':
        student_id = request.form.get('student_id', '').strip()
        if not student_id:
            flash('Vui lòng nhập Student ID.', 'err')
            return redirect(url_for('admin_accounts'))
        if not student_id.startswith('SV'):
            flash('Student ID phải bắt đầu bằng "SV". (Ví dụ: SV001)', 'err')
            return redirect(url_for('admin_accounts'))
        student = execute_query("SELECT StudentID FROM Student WHERE StudentID = %s", (student_id,), fetch_one=True)
        if not student:
            flash('Student ID không tồn tại trong hệ thống.', 'err')
            return redirect(url_for('admin_accounts'))
        exist_account = execute_query("SELECT AccountID FROM Account WHERE StudentID = %s", (student_id,), fetch_one=True)
        if exist_account:
            flash('Student ID đã có tài khoản.', 'err')
            return redirect(url_for('admin_accounts'))
        username = student_id

    elif role_name == 'lecturer':
        lecturer_id = request.form.get('lecturer_id', '').strip()
        if not lecturer_id:
            flash('Vui lòng nhập Lecturer ID.', 'err')
            return redirect(url_for('admin_accounts'))
        if not lecturer_id.startswith('GV'):
            flash('Lecturer ID phải bắt đầu bằng "GV". (Ví dụ: GV001)', 'err')
            return redirect(url_for('admin_accounts'))
        lecturer = execute_query("SELECT LecturerID FROM Lecturer WHERE LecturerID = %s", (lecturer_id,), fetch_one=True)
        if not lecturer:
            flash('Lecturer ID không tồn tại trong hệ thống.', 'err')
            return redirect(url_for('admin_accounts'))
        exist_account = execute_query("SELECT AccountID FROM Account WHERE LecturerID = %s", (lecturer_id,), fetch_one=True)
        if exist_account:
            flash('Lecturer ID đã có tài khoản.', 'err')
            return redirect(url_for('admin_accounts'))
        username = lecturer_id

    if phone and not phone.replace('+', '').isdigit():
        flash('Số điện thoại chỉ được chứa số và dấu +.', 'err')
        return redirect(url_for('admin_accounts'))
    if len(phone) > 20:
        flash('Số điện thoại không được vượt quá 20 ký tự.', 'err')
        return redirect(url_for('admin_accounts'))

    password = '123'
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    sql = """
        INSERT INTO Account
        (Username, PasswordHash, PhoneNumber, IsFirstLogin, Status, RoleID, StudentID, LecturerID)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    execute_query(sql, (username, hashed, phone, True, 'Active', role['RoleID'], student_id, lecturer_id))

    flash(f'Tạo tài khoản {role_name} thành công. Mật khẩu mặc định: 123', 'ok')
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

@app.route('/admin/account_management/update', methods=['POST'])
@login_required
@role_required('admin')
def admin_accounts_update():
    account_id = request.form.get('account_id')
    username = request.form.get('username', '').strip()
    role_name = request.form.get('role', '').strip()
    phone = request.form.get('phone', '').strip()
    student_id = request.form.get('student_id', '').strip() or None
    lecturer_id = request.form.get('lecturer_id', '').strip() or None

    if not account_id:
        flash('Thiếu thông tin tài khoản.', 'err')
        return redirect(url_for('admin_accounts'))

    account = execute_query("SELECT * FROM Account WHERE AccountID = %s", (account_id,), fetch_one=True)
    if not account:
        flash('Tài khoản không tồn tại.', 'err')
        return redirect(url_for('admin_accounts'))

    if role_name not in ['admin', 'lecturer', 'student']:
        flash('Vai trò không hợp lệ.', 'err')
        return redirect(url_for('admin_accounts'))

    role = execute_query("SELECT RoleID FROM Role WHERE RoleName = %s", (role_name,), fetch_one=True)
    if not role:
        flash('Vai trò không tồn tại.', 'err')
        return redirect(url_for('admin_accounts'))

    if role_name == 'admin':
        if username != account['Username']:
            exist = execute_query("SELECT AccountID FROM Account WHERE Username = %s AND AccountID != %s",
                                  (username, account_id), fetch_one=True)
            if exist:
                flash('Tên đăng nhập đã tồn tại.', 'err')
                return redirect(url_for('admin_accounts'))
        student_id = None
        lecturer_id = None
    elif role_name == 'student':
        if not student_id:
            flash('Vui lòng nhập Student ID.', 'err')
            return redirect(url_for('admin_accounts'))
        if not student_id.startswith('SV'):
            flash('Student ID phải bắt đầu bằng "SV".', 'err')
            return redirect(url_for('admin_accounts'))
        student = execute_query("SELECT StudentID FROM Student WHERE StudentID = %s", (student_id,), fetch_one=True)
        if not student:
            flash('Student ID không tồn tại trong hệ thống.', 'err')
            return redirect(url_for('admin_accounts'))
        exist_account = execute_query("SELECT AccountID FROM Account WHERE StudentID = %s AND AccountID != %s",
                                      (student_id, account_id), fetch_one=True)
        if exist_account:
            flash('Student ID đã được gán cho tài khoản khác.', 'err')
            return redirect(url_for('admin_accounts'))
        username = student_id
        lecturer_id = None
    elif role_name == 'lecturer':
        if not lecturer_id:
            flash('Vui lòng nhập Lecturer ID.', 'err')
            return redirect(url_for('admin_accounts'))
        if not lecturer_id.startswith('GV'):
            flash('Lecturer ID phải bắt đầu bằng "GV".', 'err')
            return redirect(url_for('admin_accounts'))
        lecturer = execute_query("SELECT LecturerID FROM Lecturer WHERE LecturerID = %s", (lecturer_id,), fetch_one=True)
        if not lecturer:
            flash('Lecturer ID không tồn tại trong hệ thống.', 'err')
            return redirect(url_for('admin_accounts'))
        exist_account = execute_query("SELECT AccountID FROM Account WHERE LecturerID = %s AND AccountID != %s",
                                      (lecturer_id, account_id), fetch_one=True)
        if exist_account:
            flash('Lecturer ID đã được gán cho tài khoản khác.', 'err')
            return redirect(url_for('admin_accounts'))
        username = lecturer_id
        student_id = None

    sql = """
        UPDATE Account
        SET Username = %s, PhoneNumber = %s, RoleID = %s, StudentID = %s, LecturerID = %s
        WHERE AccountID = %s
    """
    execute_query(sql, (username, phone, role['RoleID'], student_id, lecturer_id, account_id))
    flash('Cập nhật tài khoản thành công.', 'ok')
    return redirect(url_for('admin_accounts'))
# ---------- 6.3 Student Management (FIXED) ----------
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
    classes = execute_query("SELECT ClassID, ClassName FROM ClassGroup", fetch_all=True)
    return render_template('admin/student_management.html',
                           students=students,
                           faculties=faculties,
                           majors=majors,
                           classes=classes,
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
    # FIX: form field is name="full_name" (đã sửa trong HTML), giữ tương thích
    full_name = request.form.get('name', '').strip()
    gender = request.form.get('gender', '')
    dob = request.form.get('dob', '')
    faculty_id = request.form.get('faculty', '')
    major_id = request.form.get('major', '')
    class_id = request.form.get('class_id', '')
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    cccd = request.form.get('cccd', '').strip()
    status = request.form.get('status', 'Studying').strip()

    if not student_id or not full_name:
        flash('Vui lòng nhập đầy đủ thông tin bắt buộc (Mã SV và Họ tên).', 'err')
        return redirect(url_for('admin_students'))

    if execute_query("SELECT StudentID FROM Student WHERE StudentID = %s", (student_id,), fetch_one=True):
        flash('Lỗi nghiệp vụ: Mã sinh viên này đã tồn tại trên hệ thống.', 'err')
        return redirect(url_for('admin_students'))

    if cccd and execute_query("SELECT StudentID FROM Student WHERE CCCD = %s", (cccd,), fetch_one=True):
        flash('Lỗi nghiệp vụ: Số CCCD / National ID này đã được đăng ký.', 'err')
        return redirect(url_for('admin_students'))

    if class_id:
        is_class_ok, class_err = check_class_capacity(class_id)
        if not is_class_ok:
            flash(class_err, 'err')
            return redirect(url_for('admin_students'))

    enrollment_year = dob[:4] if dob else datetime.now().year

    try:
        sql = """
            INSERT INTO Student
                (StudentID, FullName, DateOfBirth, CCCD, PhoneNumber, Email, FacultyID, MajorID, ClassID, Gender, EnrollmentYear, Status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        execute_query(sql, (student_id, full_name, dob or None, cccd or None, phone or None, email or None,
                            faculty_id or None, major_id or None, class_id or None, gender or None, enrollment_year,
                            status or 'Studying'))

        hashed = bcrypt.hashpw('123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        role = execute_query("SELECT RoleID FROM Role WHERE RoleName = 'student'", fetch_one=True)
        if role:
            execute_query("""
                INSERT INTO Account (Username, PasswordHash, PhoneNumber, IsFirstLogin, Status, RoleID, StudentID)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (student_id, hashed, phone or None, True, 'Active', role['RoleID'], student_id))

        flash('Khởi tạo hồ sơ sinh viên thành công.', 'ok')
    except Exception as e:
        flash(f'Lỗi hệ thống khi tạo mới: {str(e)}', 'err')

    return redirect(url_for('admin_students'))


@app.route('/admin/students/edit', methods=['POST'])
@login_required
@role_required('admin')
def admin_edit_student():
    try:
        # Đồng bộ 100% thuộc tính name="..." từ file HTML sang request.form.get
        student_id = request.form.get('student_id')
        full_name  = request.form.get('name')      # đổi từ 'student_name'
        gender     = request.form.get('gender')    # đổi từ 'student_gender'
        dob        = request.form.get('dob')       # đổi từ 'student_dob'
        faculty_id = request.form.get('faculty')   # đổi từ 'student_faculty'
        major_id   = request.form.get('major')     # đổi từ 'student_major'
        email      = request.form.get('email')     # đổi từ 'student_email'
        phone      = request.form.get('phone')     # đổi từ 'student_phone'
        status     = request.form.get('status')    # đổi từ 'student_status'  # Trong HTML đặt name="student_status"

        if not student_id:
            flash('Không tìm thấy mã sinh viên cần chỉnh sửa.', 'err')
            return redirect(url_for('admin_students'))

        # Cập nhật thông tin sinh viên vào Database
        execute_query("""
            UPDATE Student 
            SET FullName = %s, Gender = %s, DateOfBirth = %s, FacultyID = %s, MajorID = %s, 
                Email = %s, PhoneNumber = %s, Status = %s
            WHERE StudentID = %s
        """, (full_name, gender, dob, faculty_id, major_id, email, phone, status, student_id))

        # Ghi nhật ký hệ thống (Để cập nhật lên Dashboard)
        execute_query("INSERT INTO ActivityLog (AccountID, action, target, target_id) VALUES (%s, 'UPDATE', 'Student', %s)",
                      (session['user_id'], student_id))

        flash('Cập nhật thông tin sinh viên thành công!', 'ok')
    except Exception as e:
        print("Lỗi Edit Student:", e)
        flash('Đã xảy ra lỗi khi chỉnh sửa thông tin sinh viên.', 'err')

    # BẮT BUỘC DÙNG REDIRECT ĐỂ LÀM MỚI BẢNG GIAO DIỆN
    return redirect(url_for('admin_students'))

@app.route('/admin/students/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_students_delete():
    student_id = request.form.get('student_id', '').strip()
    if not student_id:
        flash('Thiếu thông tin.', 'err')
        return redirect(url_for('admin_students'))

    try:
        # FIX: CourseRegistration.StudentID -> Student.StudentID KHÔNG có ON DELETE CASCADE,
        # và Grade / Attendance lại phụ thuộc vào CourseRegistration.
        # Phải xóa theo đúng thứ tự phụ thuộc (con trước, cha sau),
        # nếu không MySQL sẽ ném lỗi "foreign key constraint fails" khi xóa Student.
        registrations = execute_query(
            "SELECT RegistrationID FROM CourseRegistration WHERE StudentID = %s",
            (student_id,), fetch_all=True
        ) or []
        reg_ids = [r['RegistrationID'] for r in registrations]

        if reg_ids:
            placeholders = ','.join(['%s'] * len(reg_ids))
            execute_query(
                f"DELETE FROM Attendance WHERE RegistrationID IN ({placeholders})",
                tuple(reg_ids)
            )
            execute_query(
                f"DELETE FROM Grade WHERE RegistrationID IN ({placeholders})",
                tuple(reg_ids)
            )

        execute_query("DELETE FROM CourseRegistration WHERE StudentID = %s", (student_id,))
        execute_query("DELETE FROM Account WHERE StudentID = %s", (student_id,))
        execute_query("DELETE FROM Student WHERE StudentID = %s", (student_id,))

        flash('Xóa sinh viên thành công.', 'ok')
    except Exception as e:
        flash(f'Lỗi hệ thống khi xóa sinh viên: {str(e)}', 'err')

    return redirect(url_for('admin_students'))

# ---------- 6.4 Lecturer Management ----------
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
    lecturer_id = generate_next_lecturer_id()
    full_name = request.form.get('name', '').strip()
    faculty_id = request.form.get('faculty', '')
    email = normalize_gmail(request.form.get('email_local', ''))
    phone = request.form.get('phone', '').strip()

    if not full_name:
        flash('Vui lòng nhập đầy đủ thông tin bắt buộc.', 'err')
        return redirect(url_for('admin_lecturers'))

    if not re.match(PHONE_REGEX_LECTURER, phone):
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
        execute_query("""
            INSERT INTO Account (Username, PasswordHash, PhoneNumber, IsFirstLogin, Status, RoleID, LecturerID)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (lecturer_id, hashed, phone, True, 'Active', role['RoleID'], lecturer_id))

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

    if not re.match(PHONE_REGEX_LECTURER, phone):
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

    execute_query("INSERT INTO Faculty (FacultyID, FacultyName, Description) VALUES (%s, %s, %s)",
                  (code, name, description))
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

    execute_query("UPDATE Faculty SET FacultyName=%s, Description=%s WHERE FacultyID=%s",
                  (name, description, code))
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

    execute_query("INSERT INTO Major (MajorID, MajorName, FacultyID) VALUES (%s, %s, %s)",
                  (code, name, faculty_id))
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

    execute_query("UPDATE Major SET MajorName=%s, FacultyID=%s WHERE MajorID=%s",
                  (name, faculty_id, code))
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

    execute_query("INSERT INTO Subject (SubjectID, SubjectName, Credits, FacultyID) VALUES (%s, %s, %s, %s)",
                  (code, name, credits, faculty_id))
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

    execute_query("UPDATE Subject SET SubjectName=%s, Credits=%s, FacultyID=%s WHERE SubjectID=%s",
                  (name, credits, faculty_id, code))
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

# ---------- 6.8 Academic Structure Management (Homeroom & Course Section) ----------
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

@app.route('/admin/academic_structure/homeroom/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_homeroom_create():
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    advisor = request.form.get('advisor', '').strip() or None
    capacity = request.form.get('capacity', '').strip()
    academic_year = request.form.get('academic_year', '').strip() or None
    semester = request.form.get('semester', '').strip() or None

    if not code or not name:
        flash('Vui lòng nhập đầy đủ thông tin bắt buộc (Mã lớp và Tên lớp).', 'err')
        return redirect(url_for('admin_academic_structure'))

    exist_class = execute_query("SELECT ClassID FROM ClassGroup WHERE ClassID = %s", (code,), fetch_one=True)
    if exist_class:
        flash(f'Mã lớp "{code}" đã tồn tại trong hệ thống.', 'err')
        return redirect(url_for('admin_academic_structure'))

    if advisor:
        lecturer = execute_query("SELECT LecturerID FROM Lecturer WHERE LecturerID = %s", (advisor,), fetch_one=True)
        if not lecturer:
            flash(f'Mã giảng viên cố vấn "{advisor}" không tồn tại trong hệ thống.', 'err')
            return redirect(url_for('admin_academic_structure'))

    try:
        capacity_val = int(capacity) if capacity else None
        if capacity_val is not None and capacity_val < 0:
            flash('Sức chứa lớp (Capacity) không được là số âm.', 'err')
            return redirect(url_for('admin_academic_structure'))

        sql = """
            INSERT INTO ClassGroup (ClassID, ClassName, MaxSize, HomeroomLecturerID, AcademicYear, Semester)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        execute_query(sql, (code, name, capacity_val, advisor, academic_year, semester))
        flash('Thêm lớp homeroom mới thành công!', 'ok')
    except Exception as e:
        print(f"Lỗi hệ thống khi thêm lớp Homeroom: {e}")
        flash('Lỗi cơ sở dữ liệu: Không thể lưu dữ liệu.', 'err')

    return redirect(url_for('admin_academic_structure'))

@app.route('/admin/academic_structure/homeroom/edit', methods=['POST'])
@login_required
@role_required('admin')
def admin_homeroom_edit():
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    advisor = request.form.get('advisor', '').strip() or None
    capacity = request.form.get('capacity', '').strip()
    academic_year = request.form.get('academic_year', '').strip() or None
    semester = request.form.get('semester', '').strip() or None

    if not code or not name:
        flash('Vui lòng nhập đầy đủ thông tin bắt buộc.', 'err')
        return redirect(url_for('admin_academic_structure'))

    try:
        capacity_val = int(capacity) if capacity else None
        if capacity_val is not None and capacity_val < 0:
            flash('Sức chứa lớp không được là số âm.', 'err')
            return redirect(url_for('admin_academic_structure'))

        sql = """
            UPDATE ClassGroup
            SET ClassName=%s, MaxSize=%s, HomeroomLecturerID=%s, AcademicYear=%s, Semester=%s
            WHERE ClassID=%s
        """
        execute_query(sql, (name, capacity_val, advisor, academic_year, semester, code))
        flash('Cập nhật lớp Homeroom thành công!', 'ok')
    except Exception as e:
        print(f"Lỗi khi sửa lớp Homeroom: {e}")
        flash('Lỗi cơ sở dữ liệu: Không thể cập nhật dữ liệu.', 'err')

    return redirect(url_for('admin_academic_structure'))

@app.route('/admin/academic_structure/homeroom/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_homeroom_delete():
    code = request.form.get('code', '').strip()
    if not code:
        flash('Thiếu mã lớp học cần xóa.', 'err')
        return redirect(url_for('admin_academic_structure'))
    try:
        execute_query("DELETE FROM ClassGroup WHERE ClassID = %s", (code,))
        flash('Xóa lớp Homeroom thành công.', 'ok')
    except Exception as e:
        print(f"Lỗi khi xóa lớp Homeroom: {e}")
        flash('Không thể xóa lớp học này vì đang có dữ liệu liên quan.', 'err')
    return redirect(url_for('admin_academic_structure'))

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
    try:
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
    except Exception as e:
        flash('Không thể tải dữ liệu thống kê. Vui lòng thử lại sau.', 'err')
        return render_template('admin/statistics.html',
                               total_students=0,
                               total_lecturers=0,
                               total_faculties=0,
                               total_majors=0,
                               total_subjects=0,
                               total_sections=0,
                               total_accounts=0,
                               chart_data=[],
                               enrollment_chart_data=[],
                               faculty_distribution=[],
                               year_filter='all',
                               semester_filter='all',
                               enrollment_years=[],
                               user_name=session.get('full_name', 'Admin'),
                               role_name='System Administrator')

@app.route('/admin/statistics/enrollment_data', methods=['GET'])
@login_required
@role_required('admin')
def enrollment_data():
    year = request.args.get('year', type=int)
    try:
        if year:
            data = execute_query("""
                SELECT EnrollmentYear AS year, COUNT(*) AS count
                FROM Student
                WHERE EnrollmentYear = %s
                GROUP BY EnrollmentYear
            """, (year,), fetch_all=True)
        else:
            data = execute_query("""
                SELECT EnrollmentYear AS year, COUNT(*) AS count
                FROM Student
                WHERE EnrollmentYear IS NOT NULL
                GROUP BY EnrollmentYear
                ORDER BY EnrollmentYear ASC
            """, fetch_all=True)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': 'Không thể tải dữ liệu'}), 500

# ---------- 6.10 Admin Profile ----------
@app.route('/admin/profile', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_profile():
    username = session.get('username')
    if not username:
        return redirect(url_for('login'))

    if request.method == 'POST':
        account = get_account_by_username(username)
        if not account:
            return jsonify({'success': False, 'message': 'Không tìm thấy tài khoản.'})

        account_id = account['AccountID']
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        dob = request.form.get('dob', '').strip()
        gender = request.form.get('gender', '').strip()
        address = request.form.get('address', '').strip()

        errors = []
        if not full_name:
            errors.append('Họ và tên không được để trống.')
        if phone and not re.match(r'^\d{10}$', phone):
            errors.append('Số điện thoại phải có đúng 10 chữ số.')
        if email and not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            errors.append('Email không hợp lệ.')
        if dob:
            try:
                datetime.strptime(dob, '%Y-%m-%d')
            except ValueError:
                errors.append('Ngày sinh không hợp lệ (định dạng YYYY-MM-DD).')
        if gender and gender not in ['Male', 'Female', 'Other']:
            errors.append('Giới tính không hợp lệ.')
        if errors:
            return jsonify({'success': False, 'message': '; '.join(errors)})

        existing = execute_query(
            "SELECT AccountID FROM AdminProfile WHERE AccountID = %s",
            (account_id,), fetch_one=True
        )

        try:
            if existing:
                query = """
                    UPDATE AdminProfile
                    SET FullName = %s, Email = %s, PhoneNumber = %s,
                        DateOfBirth = %s, Gender = %s, Address = %s
                    WHERE AccountID = %s
                """
                params = (full_name, email if email else None, phone if phone else None,
                          dob if dob else None, gender if gender else None,
                          address if address else None, account_id)
            else:
                query = """
                    INSERT INTO AdminProfile
                    (AccountID, FullName, Email, PhoneNumber, DateOfBirth, Gender, Address)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                params = (account_id, full_name, email if email else None, phone if phone else None,
                          dob if dob else None, gender if gender else None,
                          address if address else None)

            execute_query(query, params)
            session['full_name'] = full_name
            return jsonify({'success': True, 'message': 'Cập nhật thông tin thành công!'})
        except Exception as e:
            app.logger.error(f"Lỗi cập nhật AdminProfile: {str(e)}")
            return jsonify({'success': False, 'message': f'Lỗi cơ sở dữ liệu: {str(e)}'})

    query = """
        SELECT
            a.Username,
            a.Status,
            r.RoleName,
            p.FullName,
            p.Email,
            p.PhoneNumber,
            p.DateOfBirth,
            p.Gender,
            p.Address
        FROM Account a
        LEFT JOIN Role r ON a.RoleID = r.RoleID
        LEFT JOIN AdminProfile p ON a.AccountID = p.AccountID
        WHERE a.Username = %s
    """
    account = execute_query(query, (username,), fetch_one=True)

    if not account:
        account = {
            'Username': username,
            'Status': 'Active',
            'RoleName': 'System Administrator',
            'FullName': username,
            'Email': '',
            'PhoneNumber': '',
            'DateOfBirth': None,
            'Gender': None,
            'Address': ''
        }
    else:
        if not account.get('FullName'):
            account['FullName'] = account.get('Username', 'Admin')

    if account.get('DateOfBirth'):
        if isinstance(account['DateOfBirth'], datetime):
            account['DateOfBirth'] = account['DateOfBirth'].strftime('%Y-%m-%d')
        elif not isinstance(account['DateOfBirth'], str):
            account['DateOfBirth'] = ''
    else:
        account['DateOfBirth'] = ''

    return render_template('admin/personal_profile.html',
                           account=account,
                           user_name=account.get('FullName', username),
                           role_name=account.get('RoleName', 'System Administrator'))

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

    if not current or not new_pass or not confirm:
        flash('Vui lòng điền đầy đủ các trường.', 'err')
        return redirect(url_for('admin_change_password'))

    if new_pass != confirm:
        flash('Mật khẩu xác nhận không khớp.', 'err')
        return redirect(url_for('admin_change_password'))

    account = execute_query("SELECT PasswordHash FROM Account WHERE AccountID = %s",
                            (session['user_id'],), fetch_one=True)
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
    execute_query("UPDATE Account SET PasswordHash = %s WHERE AccountID = %s",
                  (hashed, session['user_id']))

    flash('Đổi mật khẩu thành công.', 'ok')
    return redirect(url_for('admin_profile'))

# ---------- 6.12 Admin Logout ----------
@app.route('/admin/logout', methods=['GET', 'POST'])
@login_required
def admin_logout():
    if request.method == 'GET':
        return render_template('admin/logout.html',
                               user_name=session.get('full_name', 'Admin'),
                               role_name='System Administrator')
    session.clear()
    flash('Đã đăng xuất thành công.', 'ok')
    return redirect(url_for('login'))

# ============================================================
# 7. LECTURER MODULE
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

    execute_query("UPDATE Lecturer SET PhoneNumber = %s, Email = %s WHERE LecturerID = %s",
                  (phone, email, lecturer_id))
    execute_query("UPDATE Account SET PhoneNumber = %s WHERE LecturerID = %s",
                  (phone, lecturer_id))
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

# ---------- 7.3 Attendance ----------
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
                execute_query("UPDATE Attendance SET Status = %s WHERE AttendanceID = %s",
                              (status, exist['AttendanceID']))
            else:
                execute_query("INSERT INTO Attendance (RegistrationID, AttendanceDate, Status) VALUES (%s, %s, %s)",
                              (reg['RegistrationID'], att_date, status))

    flash('Điểm danh đã được lưu.', 'ok')
    return redirect(url_for('lecturer_learning_records', section_id=section_id))

# ---------- 7.4 Grades ----------
@app.route('/lecturer/grades/save', methods=['POST'])
@login_required
@role_required('lecturer')
def lecturer_grades_save():
    # 1. Lấy thông tin lớp học phần gửi lên
    section_id = request.form.get('course_section_id', '').strip()
    
    # 2. KIỂM TRA TRẠNG THÁI: Nếu đã Finalized thì chặn ngay lập tức
    # (Bạn check trạng thái g.GradeStatus của bất kỳ sinh viên nào trong lớp này)
    current_status = execute_query("""
        SELECT g.GradeStatus 
        FROM Grade g
        JOIN CourseRegistration r ON g.RegistrationID = r.RegistrationID
        WHERE r.CourseSectionID = %s LIMIT 1
    """, (section_id,), fetch_one=True)
    
    if current_status and current_status['GradeStatus'] == 'Finalized':
        flash('Không thể lưu! Bảng điểm lớp học phần này đã được chốt và khóa vĩnh viễn.', 'err')
        return redirect(url_for('lecturer_learning_records', section_id=section_id))
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

## fixx
@app.route('/lecturer/grades/finalize', methods=['POST'])
@login_required
@role_required('lecturer')
def lecturer_grades_finalize():
    section_id = request.form.get('course_section_id', '').strip()
    if not section_id:
        flash('Thiếu thông tin lớp học phần.', 'err')
        return redirect(url_for('lecturer_learning_records'))

    lecturer_id = session.get('username')
    check = execute_query("SELECT CourseSectionID FROM CourseSection WHERE CourseSectionID = %s AND LecturerID = %s",
                          (section_id, lecturer_id), fetch_one=True)
    if not check:
        flash('Bạn không có quyền chốt điểm cho lớp học phần này.', 'err')
        return redirect(url_for('lecturer_learning_records'))

    grades = execute_query("""
        SELECT g.GradeID, g.RegistrationID, g.ProcessScore, g.FinalScore, g.AverageScore, s.FullName
        FROM Grade g
        JOIN CourseRegistration r ON g.RegistrationID = r.RegistrationID
        JOIN Student s ON r.StudentID = s.StudentID
        WHERE r.CourseSectionID = %s AND r.Status = 'enrolled'
    """, (section_id,), fetch_all=True)

    registrations = execute_query(
        "SELECT RegistrationID FROM CourseRegistration WHERE CourseSectionID = %s AND Status = 'enrolled'",
        (section_id,), fetch_all=True)

    graded_reg_ids = {g['RegistrationID'] for g in grades if g['AverageScore'] is not None}
    all_reg_ids = {r['RegistrationID'] for r in registrations}
    missing = all_reg_ids - graded_reg_ids

    if missing:
        flash(f'Không thể chốt điểm: còn {len(missing)} sinh viên chưa có đủ điểm quá trình và cuối kỳ. Vui lòng nhập đầy đủ trước khi chốt.', 'err')
        return redirect(url_for('lecturer_learning_records', section_id=section_id))

    try:
        execute_query("""
            UPDATE Grade g
            JOIN CourseRegistration r ON g.RegistrationID = r.RegistrationID
            SET g.GradeStatus = 'Finalized'
            WHERE r.CourseSectionID = %s AND r.Status = 'enrolled'
        """, (section_id,))
        flash('Đã chốt điểm thành công. Sinh viên có thể xem điểm ngay bây giờ.', 'ok')
    except Exception as e:
        flash(f'Lỗi hệ thống khi chốt điểm: {str(e)}', 'err')

    return redirect(url_for('lecturer_learning_records', section_id=section_id))
# ---------- 7.5 Lecturer Change Password ----------
@app.route('/lecturer/change_password', methods=['GET', 'POST'])
@login_required
@role_required('lecturer')
def lecturer_change_password():
    """Cho phép lecturer đổi mật khẩu của chính mình"""
    if request.method == 'GET':
        return render_template('lecturer/change_password_lecturer.html',
                               user_name=session.get('full_name', 'Lecturer'),
                               role_name='Lecturer')

    current = request.form.get('current_password', '').strip()
    new_pass = request.form.get('new_password', '').strip()
    confirm = request.form.get('confirm_password', '').strip()

    if not current or not new_pass or not confirm:
        flash('Vui lòng điền đầy đủ các trường.', 'err')
        return redirect(url_for('lecturer_change_password'))

    if new_pass != confirm:
        flash('Mật khẩu xác nhận không khớp.', 'err')
        return redirect(url_for('lecturer_change_password'))

    account = execute_query("SELECT PasswordHash FROM Account WHERE AccountID = %s", (session['user_id'],), fetch_one=True)
    if not account:
        flash('Tài khoản không tồn tại.', 'err')
        return redirect(url_for('lecturer_change_password'))

    # Xác thực mật khẩu hiện tại
    if account['PasswordHash'].startswith('$2b$'):
        valid = bcrypt.checkpw(current.encode('utf-8'), account['PasswordHash'].encode('utf-8'))
    else:
        valid = (current == account['PasswordHash'])

    if not valid:
        flash('Mật khẩu hiện tại không đúng.', 'err')
        return redirect(url_for('lecturer_change_password'))

    # Mã hóa và lưu mật khẩu mới
    hashed = bcrypt.hashpw(new_pass.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    execute_query("UPDATE Account SET PasswordHash = %s WHERE AccountID = %s", (hashed, session['user_id']))

    flash('Đổi mật khẩu thành công.', 'ok')
    return redirect(url_for('lecturer_profile'))   

# ---------- 7.6 Lecturer Logout ----------
@app.route('/lecturer/logout', methods=['GET', 'POST'])
@login_required
def lecturer_logout():
    if request.method == 'GET':
        return render_template('lecturer/logout_lecturer.html',
                               user_name=session.get('full_name', 'Lecturer'),
                               role_name='Lecturer')
    session.clear()
    flash('Đã đăng xuất thành công.', 'ok')
    return redirect(url_for('login'))

# ============================================================
# 8. STUDENT MODULE
# ============================================================

# ---------- 8.1 Student Profile ----------
@app.route('/student/profile', methods=['GET'])
@login_required
@role_required('student')
def student_profile():
    student_id = session.get('username')
    profile = get_student_profile(student_id)
    if not profile:
        flash('Không tìm thấy dữ liệu hồ sơ sinh viên.', 'err')
        return redirect(url_for('login'))

    return render_template('student/profile_student.html',
                           student=profile,
                           user_name=session.get('full_name', 'Student'),
                           role_name='Student')

@app.route('/student/profile/update', methods=['POST'])
@login_required
@role_required('student')
def student_profile_update():
    student_id_session = session.get('username')

    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()

    current_profile = execute_query("SELECT * FROM Student WHERE StudentID = %s",
                                    (student_id_session,), fetch_one=True)
    if not current_profile:
        flash('Không tìm thấy dữ liệu hồ sơ sinh viên.', 'err')
        return redirect(url_for('student_profile'))

    if phone == (current_profile['PhoneNumber'] or '') and email == (current_profile['Email'] or ''):
        flash('Không có thay đổi nào được lưu.', 'warn')
        return redirect(url_for('student_profile'))

    is_valid, error_message = validate_contact_data(phone, email)
    if not is_valid:
        flash(error_message, 'err')
        return redirect(url_for('student_profile'))

    try:
        execute_query("UPDATE Student SET PhoneNumber = %s, Email = %s WHERE StudentID = %s",
                      (phone, email, student_id_session))
        flash('Cập nhật thông tin liên lạc thành công.', 'ok')
    except Exception as e:
        flash(f'Lỗi hệ thống: {str(e)}', 'err')

    return redirect(url_for('student_profile'))

# ---------- 8.2 Learning Progress ----------
@app.route('/student/learning_progress', methods=['GET'])
@login_required
@role_required('student')
def student_learning_progress():
    student_id = session.get('username')

    registrations = execute_query("""
        SELECT r.RegistrationID, r.CourseSectionID, cs.Semester, cs.AcademicYear,
               s.SubjectID, s.SubjectName, s.Credits,
               g.ProcessScore, g.FinalScore, g.AverageScore, g.GradeStatus
        FROM CourseRegistration r
        JOIN CourseSection cs ON r.CourseSectionID = cs.CourseSectionID
        JOIN Subject s ON cs.SubjectID = s.SubjectID
        LEFT JOIN Grade g ON r.RegistrationID = g.RegistrationID
        WHERE r.StudentID = %s AND r.Status = 'enrolled'
        ORDER BY cs.Semester DESC, s.SubjectName
    """, (student_id,), fetch_all=True)

    total_credits = 0
    total_points = 0.0
    earned_credits = 0
    grades_list = []

    for reg in registrations:
        is_finalized = reg['GradeStatus'] == 'Finalized' and reg['AverageScore'] is not None
        if is_finalized:
            avg = float(reg['AverageScore'])
            total_credits += reg['Credits']
            total_points += avg * int(reg['Credits'])
            if avg >= 5.0:
                earned_credits += reg['Credits']
            result = 'Pass' if avg >= 5.0 else 'Fail'
            grades_list.append({
                'SubjectName': reg['SubjectName'],
                'SubjectCode': reg['SubjectID'],
                'Credits': reg['Credits'],
                'ProcessScore': reg['ProcessScore'] if reg['ProcessScore'] is not None else '-',
                'FinalScore': reg['FinalScore'] if reg['FinalScore'] is not None else '-',
                'AverageScore': reg['AverageScore'],
                'Result': result
            })
        else:
            grades_list.append({
                'SubjectName': reg['SubjectName'],
                'SubjectCode': reg['SubjectID'],
                'Credits': reg['Credits'],
                'ProcessScore': '-',
                'FinalScore': '-',
                'AverageScore': '-',
                'Result': 'Pending'
            })

    gpa = round(total_points / total_credits, 2) if total_credits > 0 else 0.0

    standing = 'Weak'
    if gpa >= 9.0:
        standing = 'Excellent'
    elif gpa >= 8.0:
        standing = 'Very Good'
    elif gpa >= 6.5:
        standing = 'Good'
    elif gpa >= 5.0:
        standing = 'Average'

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

    all_attendance = execute_query("""
        SELECT a.Status FROM Attendance a
        JOIN CourseRegistration r ON a.RegistrationID = r.RegistrationID
        WHERE r.StudentID = %s
    """, (student_id,), fetch_all=True)
    total_attended = len(all_attendance)
    total_present = sum(1 for att in all_attendance if att['Status'] == 'Present')
    attendance_rate = round((total_present / total_attended) * 100) if total_attended > 0 else 0

    return render_template('student/learning_progress_student.html',
                           gpa=gpa,
                           standing=standing,
                           earned_credits=earned_credits,
                           attendance_rate=attendance_rate,
                           grades=grades_list,
                           attendances=attendances,
                           user_name=session.get('full_name', 'Student'),
                           role_name='Student')

# ---------- 8.3 Student Change Password ----------
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

    if not current or not new_pass or not confirm:
        flash('Vui lòng điền đầy đủ các trường.', 'err')
        return redirect(url_for('student_change_password'))

    if new_pass != confirm:
        flash('Mật khẩu xác nhận không khớp.', 'err')
        return redirect(url_for('student_change_password'))

    account = execute_query("SELECT PasswordHash FROM Account WHERE AccountID = %s",
                            (session['user_id'],), fetch_one=True)
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
    execute_query("UPDATE Account SET PasswordHash = %s, IsFirstLogin = FALSE WHERE AccountID = %s",
                  (hashed, session['user_id']))
    flash('Đổi mật khẩu thành công.', 'ok')
    return redirect(url_for('student_profile'))   

# ---------- 8.4 Student Logout ----------
@app.route('/student/logout', methods=['GET', 'POST'])
@login_required
def student_logout():
    if request.method == 'GET':
        return render_template('student/logout_student.html',
                               user_name=session.get('full_name', 'Student'),
                               role_name='Student')
    session.clear()
    flash('Đã đăng xuất thành công.', 'ok')
    return redirect(url_for('login'))

# ============================================================
# 9. CHẠY ỨNG DỤNG
# ============================================================
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=9999)