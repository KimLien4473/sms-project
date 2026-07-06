import bcrypt
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import pymysql
import re
from pymysql.cursors import DictCursor
from functools import wraps

# ============================================================
# 1. CẤU HÌNH FLASK VÀ KẾT NỐI CƠ SỞ DỮ LIỆU
# ============================================================
app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Khóa bí mật cho session

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'sms_db',
    'charset': 'utf8mb4',
    'autocommit': True
}

# ============================================================
# 2. HÀM KẾT NỐI VÀ THỰC THI CÂU LỆNH SQL
# ============================================================
def get_db_connection():
    """Tạo kết nối đến MySQL"""
    return pymysql.connect(**DB_CONFIG)

def execute_query(sql, params=None, fetch_one=False, fetch_all=False):
    """
    Thực thi câu lệnh SQL và trả về kết quả theo yêu cầu.
    - fetch_one: lấy một bản ghi
    - fetch_all: lấy tất cả bản ghi
    - Mặc định: commit và trả về lastrowid
    """
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
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
# 3. HÀM TIỆN ÍCH (XỬ LÝ THÔNG TIN TÀI KHOẢN, ĐIỀU HƯỚNG)
# ============================================================
def get_account_by_username(username):
    """Lấy thông tin tài khoản (kèm role) theo username"""
    sql = """
        SELECT 
            a.AccountID,
            a.Username,
            a.PasswordHash,
            a.Status,
            a.RoleID,
            a.StudentID,
            a.LecturerID,
            a.LastLogin,
            r.RoleName
        FROM Account a
        JOIN Role r ON a.RoleID = r.RoleID
        WHERE a.Username = %s
    """
    return execute_query(sql, (username,), fetch_one=True)

def get_user_info(account):
    """Lấy thông tin chi tiết của người dùng (sinh viên/giảng viên) dựa trên role"""
    if account['RoleName'] == 'student' and account['StudentID']:
        return execute_query("SELECT * FROM Student WHERE StudentID = %s", (account['StudentID'],), fetch_one=True)
    elif account['RoleName'] == 'lecturer' and account['LecturerID']:
        return execute_query("SELECT * FROM Lecturer WHERE LecturerID = %s", (account['LecturerID'],), fetch_one=True)
    return None

def get_user_display_name(account):
    """Lấy tên hiển thị (FullName) của người dùng, nếu không có thì dùng Username"""
    if account['RoleName'] == 'student' and account['StudentID']:
        user = get_user_info(account)
        return user['FullName'] if user else account['Username']
    elif account['RoleName'] == 'lecturer' and account['LecturerID']:
        user = get_user_info(account)
        return user['FullName'] if user else account['Username']
    return account['Username']

def redirect_by_role(role):
    """Chuyển hướng đến đúng dashboard theo vai trò (hiện chỉ hỗ trợ admin)"""
    if role == 'admin':
        return redirect(url_for('admin_dashboard'))
    else:
        flash('Vai trò không được hỗ trợ.', 'err')
        return redirect(url_for('logout'))

# ============================================================
# 4. DECORATOR (XÁC THỰC & PHÂN QUYỀN)
# ============================================================
def login_required(f):
    """Yêu cầu người dùng đã đăng nhập"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Vui lòng đăng nhập để tiếp tục.', 'warn')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def role_required(role):
    """Yêu cầu người dùng có vai trò nhất định (admin/lecturer/student)"""
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
# 5. CÁC ROUTE XÁC THỰC: LOGIN, LOGOUT, RESET PASSWORD
# ============================================================
@app.route('/')
def index():
    """Trang chủ: nếu đã đăng nhập thì vào dashboard, nếu chưa thì chuyển đến login"""
    if 'user_id' in session:
        return redirect_by_role(session.get('role'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Đăng nhập: kiểm tra username/password, role, trạng thái tài khoản"""
    if request.method == 'GET':
        if 'user_id' in session:
            return redirect_by_role(session.get('role'))
        return render_template('login.html')

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'admin')  # mặc định admin

    if not username or not password:
        flash('Vui lòng nhập đầy đủ thông tin.', 'err')
        return redirect(url_for('login'))

    account = get_account_by_username(username)
    if not account:
        flash('Sai username hoặc password.', 'err')
        return redirect(url_for('login'))

    # Xác thực mật khẩu (hỗ trợ plaintext và bcrypt)
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

    # Lưu thông tin vào session
    session['user_id'] = account['AccountID']
    session['username'] = account['Username']
    session['role'] = account['RoleName']
    session['full_name'] = get_user_display_name(account)

    # Cập nhật thời gian đăng nhập cuối
    execute_query("UPDATE Account SET LastLogin = NOW() WHERE AccountID = %s", (account['AccountID'],))
    flash('Đăng nhập thành công!', 'ok')
    return redirect_by_role(account['RoleName'])

@app.route('/logout', methods=['POST'])
def logout():
    """Đăng xuất (xóa session)"""
    session.clear()
    flash('Đã đăng xuất.', 'ok')
    return redirect(url_for('login'))

@app.route('/resetpassword', methods=['GET', 'POST'])
def reset_password():
    """Quên mật khẩu: tìm tài khoản qua số điện thoại và đặt lại mật khẩu"""
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

    # Tìm AccountID qua số điện thoại (trong Account, Student, Lecturer)
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
    """Trang chính sau đăng nhập (chuyển hướng đến đúng module)"""
    role = session.get('role')
    if role == 'admin':
        return redirect(url_for('admin_dashboard'))
    else:
        flash('Vai trò không được hỗ trợ.', 'err')
        return redirect(url_for('logout'))

# ============================================================
# 6. CÁC ROUTE DÀNH CHO ADMIN
#    (Dashboard, Quản lý tài khoản, Thống kê, Hồ sơ, Đổi mật khẩu, Đăng xuất)
# ============================================================

# ---------- 6.1 Admin Dashboard (bỏ Recent Activities) ----------
@app.route('/admin/dashboard', methods=['GET'])
@login_required
@role_required('admin')
def admin_dashboard():
    """Trang tổng quan admin: hiển thị số liệu thống kê cơ bản và phân bố sinh viên theo khoa"""
    try:
        total_students = execute_query("SELECT COUNT(*) AS total FROM Student", fetch_one=True)['total']
        total_lecturers = execute_query("SELECT COUNT(*) AS total FROM Lecturer", fetch_one=True)['total']
        total_faculties = execute_query("SELECT COUNT(*) AS total FROM Faculty", fetch_one=True)['total']
        total_majors = execute_query("SELECT COUNT(*) AS total FROM Major", fetch_one=True)['total']

        # Dữ liệu để vẽ biểu đồ phân bố sinh viên theo khoa (dạng thanh ngang)
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

        # Top 4 khoa có nhiều sinh viên nhất
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

        # Đã xóa phần query và truyền biến activities vì không còn "Recent System Activities"

        return render_template('admin/admin_dashboard.html',
                               total_students=total_students,
                               total_lecturers=total_lecturers,
                               total_faculties=total_faculties,
                               total_majors=total_majors,
                               faculty_stats=faculty_stats,
                               top_faculties=top_faculties,
                               chart_data=chart_data,
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
                               user_name=session.get('full_name', 'Admin'),
                               role_name='System Administrator')

# ---------- 6.2 Quản lý tài khoản ----------
@app.route('/admin/account_management', methods=['GET'])
@login_required
@role_required('admin')
def admin_accounts():
    """Hiển thị danh sách tài khoản với tìm kiếm và lọc theo role"""
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
    """Tạo tài khoản mới (admin/student/lecturer) với mật khẩu mặc định '123'"""
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

    # Xử lý theo từng role
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

    # Kiểm tra số điện thoại
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
    """Khóa / mở khóa tài khoản"""
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
    """Đặt lại mật khẩu về '123' cho một tài khoản"""
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
    """Cập nhật thông tin tài khoản (username, role, phone, student/lecturer ID)"""
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

    # Xử lý tùy theo role mới
    if role_name == 'admin':
        if username != account['Username']:
            exist = execute_query("SELECT AccountID FROM Account WHERE Username = %s AND AccountID != %s", (username, account_id), fetch_one=True)
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
        exist_account = execute_query("SELECT AccountID FROM Account WHERE StudentID = %s AND AccountID != %s", (student_id, account_id), fetch_one=True)
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
        exist_account = execute_query("SELECT AccountID FROM Account WHERE LecturerID = %s AND AccountID != %s", (lecturer_id, account_id), fetch_one=True)
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

# ---------- 6.3 Thống kê ----------
@app.route('/admin/statistics', methods=['GET'])
@login_required
@role_required('admin')
def admin_statistics():
    """Trang thống kê toàn diện với nhiều chỉ số và biểu đồ"""
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
    """API trả về dữ liệu tuyển sinh theo năm (dùng cho biểu đồ)"""
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

# ---------- 6.4 Hồ sơ cá nhân (Admin) ----------
@app.route('/admin/profile', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_profile():
    """Xem và cập nhật hồ sơ cá nhân của admin"""
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

        # Validate dữ liệu
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

        # Kiểm tra đã có profile chưa
        existing = execute_query(
            "SELECT AccountID FROM AdminProfile WHERE AccountID = %s",
            (account_id,),
            fetch_one=True
        )

        try:
            if existing:
                query = """
                    UPDATE AdminProfile 
                    SET FullName = %s, Email = %s, PhoneNumber = %s,
                        DateOfBirth = %s, Gender = %s, Address = %s
                    WHERE AccountID = %s
                """
                params = (
                    full_name,
                    email if email else None,
                    phone if phone else None,
                    dob if dob else None,
                    gender if gender else None,
                    address if address else None,
                    account_id
                )
            else:
                query = """
                    INSERT INTO AdminProfile 
                    (AccountID, FullName, Email, PhoneNumber, DateOfBirth, Gender, Address)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                params = (
                    account_id,
                    full_name,
                    email if email else None,
                    phone if phone else None,
                    dob if dob else None,
                    gender if gender else None,
                    address if address else None
                )

            execute_query(query, params)
            session['full_name'] = full_name  # cập nhật tên hiển thị trên topbar

            return jsonify({'success': True, 'message': 'Cập nhật thông tin thành công!'})

        except Exception as e:
            app.logger.error(f"Lỗi cập nhật AdminProfile: {str(e)}")
            return jsonify({'success': False, 'message': f'Lỗi cơ sở dữ liệu: {str(e)}'})

    # GET: hiển thị form
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

    # Định dạng ngày sinh cho input type="date"
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

# ---------- 6.5 Đổi mật khẩu (Admin) ----------
@app.route('/admin/change_password', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_change_password():
    """Cho phép admin đổi mật khẩu của chính mình"""
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

    account = execute_query("SELECT PasswordHash FROM Account WHERE AccountID = %s", (session['user_id'],), fetch_one=True)
    if not account:
        flash('Tài khoản không tồn tại.', 'err')
        return redirect(url_for('admin_change_password'))

    # Xác thực mật khẩu hiện tại
    if account['PasswordHash'].startswith('$2b$'):
        valid = bcrypt.checkpw(current.encode('utf-8'), account['PasswordHash'].encode('utf-8'))
    else:
        valid = (current == account['PasswordHash'])

    if not valid:
        flash('Mật khẩu hiện tại không đúng.', 'err')
        return redirect(url_for('admin_change_password'))

    # Mã hóa và lưu mật khẩu mới
    hashed = bcrypt.hashpw(new_pass.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    execute_query("UPDATE Account SET PasswordHash = %s WHERE AccountID = %s", (hashed, session['user_id']))

    flash('Đổi mật khẩu thành công.', 'ok')
    return redirect(url_for('admin_profile'))

# ---------- 6.6 Đăng xuất (Admin) ----------
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
# 7. KHỞI CHẠY ỨNG DỤNG
# ============================================================
if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=1111)