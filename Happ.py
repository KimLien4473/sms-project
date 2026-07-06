import bcrypt
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import pymysql
import re
import os
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

def init_upload_folder(app):
    app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024
    app.config.setdefault('UPLOAD_FOLDER', os.path.join(app.root_path, 'static'))
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'avatars'), exist_ok=True)


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
    """Lấy thông tin tài khoản theo username."""
    sql = """
        SELECT a.*, r.RoleName
        FROM Account a
        JOIN Role r ON a.RoleID = r.RoleID
        WHERE a.Username = %s
    """
    return execute_query(sql, (username,), fetch_one=True)

def get_user_display_name(account):
    """Lấy tên hiển thị của người dùng."""
    if account['RoleName'] == 'student' and account['StudentID']:
        user = execute_query("SELECT FullName FROM Student WHERE StudentID = %s", (account['StudentID'],), fetch_one=True)
        return user['FullName'] if user else account['Username']
    elif account['RoleName'] == 'lecturer' and account['LecturerID']:
        user = execute_query("SELECT FullName FROM Lecturer WHERE LecturerID = %s", (account['LecturerID'],), fetch_one=True)
        return user['FullName'] if user else account['Username']
    return account['Username']

def redirect_by_role(role):
    """Chuyển hướng người dùng đến trang tương ứng sau đăng nhập."""
    if role == 'admin':
        return redirect(url_for('admin_faculties'))
    elif role == 'lecturer':
        return redirect(url_for('admin_faculties'))  # Chuyển đến trang mặc định
    elif role == 'student':
        return redirect(url_for('admin_faculties'))  # Chuyển đến trang mặc định
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
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ============================================================
# 5. LOGIN - LOGOUT
# ============================================================
@app.route('/')
def index():
    """Trang chủ - chuyển đến login hoặc dashboard."""
    if 'user_id' in session:
        return redirect_by_role(session.get('role'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Trang đăng nhập."""
    if request.method == 'GET':
        if 'user_id' in session:
            return redirect_by_role(session.get('role'))
        return render_template('login.html')

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'admin')  # Mặc định là admin

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

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    """Đăng xuất."""
    session.clear()
    flash('Đã đăng xuất.', 'ok')
    return redirect(url_for('login'))


# ============================================================
# 6. ADMIN ACADEMIC MODULES
# ============================================================

# ---------- 6.1 Faculty Management ----------
@app.route('/admin/faculties', methods=['GET'])
@login_required
@role_required('admin')
def admin_faculties():
    """Hiển thị danh sách khoa với tìm kiếm."""
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
    """Tạo khoa mới."""
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
    """Cập nhật thông tin khoa."""
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
    """Xóa khoa."""
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


# ---------- 6.2 Major Management ----------
@app.route('/admin/majors', methods=['GET'])
@login_required
@role_required('admin')
def admin_majors():
    """Hiển thị danh sách ngành học với tìm kiếm."""
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
    """Tạo ngành học mới."""
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
    """Cập nhật thông tin ngành học."""
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
    """Xóa ngành học."""
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


# ---------- 6.3 Course Management ----------
@app.route('/admin/courses', methods=['GET'])
@login_required
@role_required('admin')
def admin_courses():
    """Hiển thị danh sách môn học với tìm kiếm."""
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
    """Tạo môn học mới."""
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
    """Cập nhật thông tin môn học."""
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
    """Xóa môn học."""
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


# ---------- 6.4 Academic Structure Management ----------
@app.route('/admin/academic_structure', methods=['GET'])
@login_required
@role_required('admin')
def admin_academic_structure():
    """Hiển thị trang quản lý cấu trúc học vụ (lớp homeroom và lớp học phần)."""
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


# ==================== HOMEROOM CRUD ====================
@app.route('/admin/academic_structure/homeroom/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_homeroom_create():
    """Tạo lớp homeroom mới."""
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
    """Cập nhật thông tin lớp homeroom."""
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
    """Xóa lớp homeroom."""
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


# ==================== COURSE SECTION CRUD ====================
@app.route('/admin/academic_structure/course_section/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_course_section_create():
    """Tạo lớp học phần mới."""
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
    """Cập nhật thông tin lớp học phần."""
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
    """Xóa lớp học phần."""
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


# ============================================================
# 7. CHẠY ỨNG DỤNG
# ============================================================
if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=9000)