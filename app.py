import re
import bcrypt
from datetime import datetime
from functools import wraps

import pymysql
from flask import Flask, flash, redirect, render_template, request, session, url_for
from pymysql.cursors import DictCursor

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


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Vui lòng đăng nhập để tiếp tục.', 'warn')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'role' not in session or session['role'] != role:
                flash('Bạn không có quyền truy cập trang này.', 'err')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated
    return decorator


@app.route('/')
def index():
    if session.get('role') == 'lecturer':
        return redirect(url_for('lecturer_profile'))
    if session.get('role') == 'admin':
        return redirect(url_for('admin_lecturers'))
    return 'Lecturer Module Backend'

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
if __name__ == '__main__':
    app.run(debug=True)
