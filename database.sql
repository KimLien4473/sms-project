
DROP DATABASE IF EXISTS sms_db;

-- Tạo database mới
CREATE DATABASE sms_db
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

-- Sử dụng database
USE sms_db;

-- ============================================================
-- 1. BẢNG FACULTY (Khoa)
-- ============================================================
CREATE TABLE Faculty (
    FacultyID VARCHAR(20) PRIMARY KEY,
    FacultyName VARCHAR(100) NOT NULL,
    Description TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 2. BẢNG MAJOR (Ngành)
-- ============================================================
CREATE TABLE Major (
    MajorID VARCHAR(20) PRIMARY KEY,
    MajorName VARCHAR(100) NOT NULL,
    FacultyID VARCHAR(20) NOT NULL,
    CONSTRAINT fk_major_faculty FOREIGN KEY (FacultyID) REFERENCES Faculty(FacultyID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 3. BẢNG LECTURER (Giảng viên)
-- ============================================================
CREATE TABLE Lecturer (
    LecturerID VARCHAR(20) PRIMARY KEY,
    FullName VARCHAR(100) NOT NULL,
    DateOfBirth DATE NULL,
    CCCD VARCHAR(20) NULL,
    PhoneNumber VARCHAR(20) NULL,
    Email VARCHAR(100) NULL,
    FacultyID VARCHAR(20) NULL,
    Title VARCHAR(100) NULL,
    CONSTRAINT fk_lecturer_faculty FOREIGN KEY (FacultyID) REFERENCES Faculty(FacultyID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 4. BẢNG CLASSGROUP (Lớp homeroom)
-- ============================================================
CREATE TABLE ClassGroup (
    ClassID VARCHAR(20) PRIMARY KEY,
    ClassName VARCHAR(100) NOT NULL,
    MaxSize INT NULL,
    HomeroomLecturerID VARCHAR(20) NULL,
    AcademicYear VARCHAR(10) NULL,
    Semester VARCHAR(20) NULL,
    CONSTRAINT fk_classgroup_lecturer FOREIGN KEY (HomeroomLecturerID) REFERENCES Lecturer(LecturerID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 5. BẢNG SUBJECT (Môn học)
-- ============================================================
CREATE TABLE Subject (
    SubjectID VARCHAR(20) PRIMARY KEY,
    SubjectName VARCHAR(100) NOT NULL,
    Credits INT NOT NULL,
    FacultyID VARCHAR(20) NULL,
    CONSTRAINT fk_subject_faculty FOREIGN KEY (FacultyID) REFERENCES Faculty(FacultyID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 6. BẢNG STUDENT (Sinh viên)
-- ============================================================
CREATE TABLE Student (
    StudentID VARCHAR(20) PRIMARY KEY,
    FullName VARCHAR(100) NOT NULL,
    DateOfBirth DATE NULL,
    CCCD VARCHAR(20) NULL,
    PhoneNumber VARCHAR(20) NULL,
    Email VARCHAR(100) NULL,
    FacultyID VARCHAR(20) NULL,
    MajorID VARCHAR(20) NULL,
    ClassID VARCHAR(20) NULL,
    Gender ENUM('Male','Female','Other') NULL,
    EnrollmentYear YEAR NULL,
    CONSTRAINT fk_student_faculty FOREIGN KEY (FacultyID) REFERENCES Faculty(FacultyID),
    CONSTRAINT fk_student_major FOREIGN KEY (MajorID) REFERENCES Major(MajorID),
    CONSTRAINT fk_student_class FOREIGN KEY (ClassID) REFERENCES ClassGroup(ClassID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 7. BẢNG ROLE (Vai trò)
-- ============================================================
CREATE TABLE Role (
    RoleID INT PRIMARY KEY,
    RoleName ENUM('admin','lecturer','student') NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 8. BẢNG ACCOUNT (Tài khoản đăng nhập)
-- ============================================================
CREATE TABLE Account (
    AccountID INT PRIMARY KEY AUTO_INCREMENT,
    Username VARCHAR(50) UNIQUE NOT NULL,
    PasswordHash VARCHAR(255) NOT NULL,
    PhoneNumber VARCHAR(20) NULL,
    IsFirstLogin BOOLEAN DEFAULT TRUE,
    Status ENUM('Active','Inactive') DEFAULT 'Active',
    RoleID INT NOT NULL,
    StudentID VARCHAR(20) NULL,
    LecturerID VARCHAR(20) NULL,
    LastLogin DATETIME NULL,
    Avatar VARCHAR(255),
    CONSTRAINT fk_account_role FOREIGN KEY (RoleID) REFERENCES Role(RoleID),
    CONSTRAINT fk_account_student FOREIGN KEY (StudentID) REFERENCES Student(StudentID),
    CONSTRAINT fk_account_lecturer FOREIGN KEY (LecturerID) REFERENCES Lecturer(LecturerID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 9. BẢNG COURSESECTION (Lớp học phần)
-- ============================================================
CREATE TABLE CourseSection (
    CourseSectionID VARCHAR(20) PRIMARY KEY,
    SubjectID VARCHAR(20) NOT NULL,
    LecturerID VARCHAR(20) NOT NULL,
    Semester VARCHAR(20) NOT NULL,
    AcademicYear VARCHAR(10) NULL,
    MaxSize INT NULL,
    CONSTRAINT fk_coursesection_subject FOREIGN KEY (SubjectID) REFERENCES Subject(SubjectID),
    CONSTRAINT fk_coursesection_lecturer FOREIGN KEY (LecturerID) REFERENCES Lecturer(LecturerID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 10. BẢNG COURSEREGISTRATION (Đăng ký học phần)
-- ============================================================
CREATE TABLE CourseRegistration (
    RegistrationID INT PRIMARY KEY AUTO_INCREMENT,
    StudentID VARCHAR(20) NOT NULL,
    CourseSectionID VARCHAR(20) NOT NULL,
    RegistrationDate DATE DEFAULT (CURRENT_DATE),
    Status ENUM('enrolled','dropped','completed') DEFAULT 'enrolled',
    CONSTRAINT fk_registration_student FOREIGN KEY (StudentID) REFERENCES Student(StudentID),
    CONSTRAINT fk_registration_section FOREIGN KEY (CourseSectionID) REFERENCES CourseSection(CourseSectionID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 11. BẢNG GRADE (Điểm số)
-- ============================================================
CREATE TABLE Grade (
    GradeID INT PRIMARY KEY AUTO_INCREMENT,
    RegistrationID INT NOT NULL,
    ProcessScore DECIMAL(5,2) NULL,
    FinalScore DECIMAL(5,2) NULL,
    AverageScore DECIMAL(5,2) NULL,
    GradeStatus ENUM('Draft','Finalized') DEFAULT 'Draft',
    AcademicRank ENUM('Excellent','Good','Fair','Average','Weak') NULL,
    CONSTRAINT fk_grade_registration FOREIGN KEY (RegistrationID) REFERENCES CourseRegistration(RegistrationID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 12. BẢNG ATTENDANCE (Điểm danh)
-- ============================================================
CREATE TABLE Attendance (
    AttendanceID INT PRIMARY KEY AUTO_INCREMENT,
    RegistrationID INT NOT NULL,
    AttendanceDate DATE NOT NULL,
    Status ENUM('Present','Absent') NOT NULL,
    CONSTRAINT fk_attendance_registration FOREIGN KEY (RegistrationID) REFERENCES CourseRegistration(RegistrationID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 13. BẢNG ACTIVITYLOG (Nhật ký hoạt động)
-- ============================================================
CREATE TABLE ActivityLog (
    id INT PRIMARY KEY AUTO_INCREMENT,
    AccountID INT NOT NULL,
    action VARCHAR(50) NOT NULL,
    target VARCHAR(100) NOT NULL,
    target_id VARCHAR(50),
    details TEXT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_activity_user FOREIGN KEY (AccountID) REFERENCES Account(AccountID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bảng AdminProfile dùng để lưu thông tin chi tiết của tài khoản admin
CREATE TABLE AdminProfile (
    AccountID INT PRIMARY KEY,                     
    FullName VARCHAR(100) NOT NULL,          
    Email VARCHAR(100) NULL,            
    PhoneNumber VARCHAR(20) NULL,        
    DateOfBirth DATE NULL,                   
    Gender ENUM('Male', 'Female', 'Other') NULL,  
    Address TEXT NULL,          
    UpdatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
        ON UPDATE CURRENT_TIMESTAMP,           
    CONSTRAINT fk_admin_profile_account 
        FOREIGN KEY (AccountID) REFERENCES Account(AccountID) 
        ON DELETE CASCADE                     
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- CHÈN DỮ LIỆU MẪU
-- ============================================================

-- ------------------------------
-- Faculty
-- ------------------------------
INSERT INTO Faculty (FacultyID, FacultyName, Description) VALUES
('KHMT', 'Khoa học Máy tính', 'Đào tạo và nghiên cứu về khoa học máy tính'),
('KTMT', 'Kỹ thuật Máy tính', 'Đào tạo về phần cứng và nhúng'),
('KHDL', 'Khoa học Dữ liệu', 'Đào tạo về phân tích dữ liệu lớn'),
('ATTT', 'An toàn Thông tin', 'Đào tạo về bảo mật và an toàn thông tin'),
('MMT', 'Mạng máy tính và Truyền thông', 'Đào tạo về mạng và truyền thông');

-- ------------------------------
-- Major
-- ------------------------------
INSERT INTO Major (MajorID, MajorName, FacultyID) VALUES
('KHMT_AI', 'Trí tuệ nhân tạo', 'KHMT'),
('KHMT_CS', 'Khoa học máy tính', 'KHMT'),
('KTMT_KT', 'Kỹ thuật máy tính', 'KTMT'),
('KTMT_NH', 'Kỹ thuật nhúng', 'KTMT'),
('KHDL_DS', 'Khoa học dữ liệu', 'KHDL'),
('KHDL_AI', 'AI và Dữ liệu', 'KHDL'),
('ATTT_BM', 'Bảo mật hệ thống', 'ATTT'),
('ATTT_AT', 'An toàn thông tin', 'ATTT'),
('MMT_M', 'Mạng máy tính', 'MMT'),
('MMT_VT', 'Truyền thông và Viễn thông', 'MMT');

-- ------------------------------
-- Lecturer
-- ------------------------------
INSERT INTO Lecturer (LecturerID, FullName, DateOfBirth, CCCD, PhoneNumber, Email, FacultyID, Title) VALUES
('GV001', 'PGS. Nguyễn Văn Bình', '1975-06-10', '00119750610123', '0912345678', 'binhnv@university.edu', 'KHMT', 'Assoc. Prof.'),
('GV002', 'TS. Trần Thị Cúc', '1980-12-05', '00119801205456', '0923456789', 'cuctt@university.edu', 'KTMT', 'Dr.'),
('GV003', 'ThS. Lê Văn Dũng', '1985-08-20', '00119850820789', '0934567890', 'dunglv@university.edu', 'KHDL', 'Lecturer'),
('GV004', 'TS. Phạm Thị Em', '1978-03-15', '00119780315123', '0945678901', 'empt@university.edu', 'ATTT', 'Dr.'),
('GV005', 'PGS. Hoàng Văn Phúc', '1972-09-30', '00119720930456', '0956789012', 'phuchv@university.edu', 'MMT', 'Assoc. Prof.'),
('GV006', 'TS. Ngô Thị Hạnh', '1982-07-25', '00119820725789', '0967890123', 'hanhnt@university.edu', 'KHMT', 'Dr.'),
('GV007', 'ThS. Đỗ Văn Hùng', '1988-11-11', '00119881111234', '0978901234', 'hungdv@university.edu', 'KTMT', 'Lecturer'),
('GV008', 'TS. Bùi Thị Lan', '1979-04-18', '00119790418567', '0989012345', 'lanbt@university.edu', 'KHDL', 'Dr.'),
('GV009', 'PGS. Vũ Văn Minh', '1976-02-28', '00119760228890', '0990123456', 'minhvv@university.edu', 'ATTT', 'Assoc. Prof.'),
('GV010', 'ThS. Lý Thị Nga', '1986-10-10', '00119861010123', '0901234567', 'ngalt@university.edu', 'MMT', 'Lecturer'),
('GV011', 'TS. Trịnh Văn Oanh', '1983-05-05', '00119830505456', '0912345678', 'oanhtv@university.edu', 'KHMT', 'Dr.'),
('GV012', 'PGS. Đặng Thị Phương', '1977-12-12', '00119771212789', '0923456789', 'phuongdt@university.edu', 'KTMT', 'Assoc. Prof.'),
('GV013', 'ThS. Nguyễn Văn Quân', '1989-09-09', '00119890909123', '0934567890', 'quannv@university.edu', 'KHDL', 'Lecturer'),
('GV014', 'TS. Lê Thị Hoa', '1981-03-20', '00119810320456', '0945678901', 'hoalt@university.edu', 'ATTT', 'Dr.'),
('GV015', 'PGS. Trần Văn Sơn', '1974-06-15', '00119740615789', '0956789012', 'sontv@university.edu', 'MMT', 'Assoc. Prof.');

-- ------------------------------
-- ClassGroup
-- ------------------------------
INSERT INTO ClassGroup (ClassID, ClassName, MaxSize, HomeroomLecturerID, AcademicYear, Semester) VALUES
('KHMT-K45', 'Khoa học Máy tính K45', 40, 'GV004', '2024-2025', 'Fall 2024'),
('KTMT-K45', 'Kỹ thuật Máy tính K45', 35, 'GV005', '2024-2025', 'Fall 2024'),
('KHDL-K45', 'Khoa học Dữ liệu K45', 30, 'GV006', '2024-2025', 'Fall 2024'),
('ATTT-K45', 'An toàn Thông tin K45', 35, 'GV007', '2024-2025', 'Fall 2024'),
('MMT-K45', 'Mạng máy tính K45', 40, 'GV008', '2024-2025', 'Fall 2024'),
('KHMT-K46', 'Khoa học Máy tính K46', 40, 'GV009', '2025-2026', 'Spring 2025'),
('KTMT-K46', 'Kỹ thuật Máy tính K46', 35, 'GV010', '2025-2026', 'Spring 2025'),
('KHDL-K46', 'Khoa học Dữ liệu K46', 30, 'GV011', '2025-2026', 'Spring 2025'),
('ATTT-K46', 'An toàn Thông tin K46', 35, 'GV012', '2025-2026', 'Spring 2025'),
('MMT-K46', 'Mạng máy tính K46', 40, 'GV013', '2025-2026', 'Spring 2025');

-- ------------------------------
-- Subject
-- ------------------------------
INSERT INTO Subject (SubjectID, SubjectName, Credits, FacultyID) VALUES
('KHMT101', 'Nhập môn Khoa học Máy tính', 3, 'KHMT'),
('KHMT201', 'Cấu trúc dữ liệu và Giải thuật', 4, 'KHMT'),
('KHMT301', 'Hệ điều hành', 3, 'KHMT'),
('KTMT101', 'Kỹ thuật số', 3, 'KTMT'),
('KTMT201', 'Vi xử lý và Vi điều khiển', 4, 'KTMT'),
('KHDL101', 'Nhập môn Khoa học Dữ liệu', 3, 'KHDL'),
('KHDL201', 'Phân tích dữ liệu', 4, 'KHDL'),
('ATTT101', 'An toàn thông tin cơ bản', 3, 'ATTT'),
('ATTT201', 'Mật mã học', 4, 'ATTT'),
('MMT101', 'Mạng máy tính', 3, 'MMT'),
('MMT201', 'Truyền thông dữ liệu', 4, 'MMT'),
('KHMT401', 'Trí tuệ nhân tạo', 3, 'KHMT'),
('KTMT301', 'Hệ thống nhúng', 4, 'KTMT'),
('KHDL301', 'Học máy', 3, 'KHDL'),
('ATTT301', 'An ninh mạng', 4, 'ATTT');


-- ------------------------------
-- Student
-- ------------------------------
INSERT INTO Student (StudentID, FullName, DateOfBirth, CCCD, PhoneNumber, Email, FacultyID, MajorID, ClassID, Gender, EnrollmentYear) VALUES
('SV001', 'Nguyễn Minh Anh', '2005-01-01', '00120050101123', '0900000001', 'anh.nm@student.edu', 'KHMT', 'KHMT_AI', 'KHMT-K45', 'Female', 2024),
('SV002', 'Trần Văn Bảo', '2005-02-02', '00120050202123', '0900000002', 'bao.tv@student.edu', 'KHMT', 'KHMT_CS', 'KHMT-K45', 'Male', 2024),
('SV003', 'Lê Thị Cát', '2005-03-03', '00120050303123', '0900000003', 'cat.lt@student.edu', 'KTMT', 'KTMT_KT', 'KTMT-K45', 'Female', 2024),
('SV004', 'Phạm Văn Đức', '2005-04-04', '00120050404123', '0900000004', 'duc.pv@student.edu', 'KTMT', 'KTMT_NH', 'KTMT-K45', 'Male', 2024),
('SV005', 'Hoàng Thị Em', '2005-05-05', '00120050505123', '0900000005', 'em.ht@student.edu', 'KHDL', 'KHDL_DS', 'KHDL-K45', 'Female', 2024),
('SV006', 'Ngô Văn Giang', '2005-06-06', '00120050606123', '0900000006', 'giang.nv@student.edu', 'KHDL', 'KHDL_AI', 'KHDL-K45', 'Male', 2024),
('SV007', 'Đỗ Thị Hà', '2005-07-07', '00120050707123', '0900000007', 'ha.dt@student.edu', 'ATTT', 'ATTT_BM', 'ATTT-K45', 'Female', 2024),
('SV008', 'Bùi Văn Hùng', '2005-08-08', '00120050808123', '0900000008', 'hung.bv@student.edu', 'ATTT', 'ATTT_AT', 'ATTT-K45', 'Male', 2024),
('SV009', 'Vũ Thị Lan', '2005-09-09', '00120050909123', '0900000009', 'lan.vt@student.edu', 'MMT', 'MMT_M', 'MMT-K45', 'Female', 2024),
('SV010', 'Lý Văn Minh', '2005-10-10', '00120051010123', '0900000010', 'minh.lv@student.edu', 'MMT', 'MMT_VT', 'MMT-K45', 'Male', 2024),
('SV011', 'Trịnh Thị Nga', '2005-11-11', '00120051111123', '0900000011', 'nga.tt@student.edu', 'KHMT', 'KHMT_AI', 'KHMT-K46', 'Female', 2025),
('SV012', 'Đặng Văn Oanh', '2005-12-12', '00120051212123', '0900000012', 'oanh.dv@student.edu', 'KHMT', 'KHMT_CS', 'KHMT-K46', 'Male', 2025),
('SV013', 'Nguyễn Thị Phương', '2006-01-01', '00120060101123', '0900000013', 'phuong.nt@student.edu', 'KTMT', 'KTMT_KT', 'KTMT-K46', 'Female', 2025),
('SV014', 'Trần Văn Quân', '2006-02-02', '00120060202123', '0900000014', 'quan.tv@student.edu', 'KTMT', 'KTMT_NH', 'KTMT-K46', 'Male', 2025),
('SV015', 'Lê Thị Hoa', '2006-03-03', '00120060303123', '0900000015', 'hoa.lt@student.edu', 'KHDL', 'KHDL_DS', 'KHDL-K46', 'Female', 2025),
('SV016', 'Phạm Văn Sơn', '2006-04-04', '00120060404123', '0900000016', 'son.pv@student.edu', 'KHDL', 'KHDL_AI', 'KHDL-K46', 'Male', 2025),
('SV017', 'Hoàng Thị Thu', '2006-05-05', '00120060505123', '0900000017', 'thu.ht@student.edu', 'ATTT', 'ATTT_BM', 'ATTT-K46', 'Female', 2025),
('SV018', 'Ngô Văn Toàn', '2006-06-06', '00120060606123', '0900000018', 'toan.nv@student.edu', 'ATTT', 'ATTT_AT', 'ATTT-K46', 'Male', 2025),
('SV019', 'Đỗ Thị Uyên', '2006-07-07', '00120060707123', '0900000019', 'uyen.dt@student.edu', 'MMT', 'MMT_M', 'MMT-K46', 'Female', 2025),
('SV020', 'Bùi Văn Vũ', '2006-08-08', '00120060808123', '0900000020', 'vu.bv@student.edu', 'MMT', 'MMT_VT', 'MMT-K46', 'Male', 2025),
('SV021', 'Vũ Thị Xuân', '2006-09-09', '00120060909123', '0900000021', 'xuan.vt@student.edu', 'KHMT', 'KHMT_AI', 'KHMT-K45', 'Female', 2024),
('SV022', 'Lý Văn Yên', '2006-10-10', '00120061010123', '0900000022', 'yen.lv@student.edu', 'KHMT', 'KHMT_CS', 'KHMT-K45', 'Male', 2024),
('SV023', 'Trịnh Thị Ánh', '2006-11-11', '00120061111123', '0900000023', 'anh.tt@student.edu', 'KTMT', 'KTMT_KT', 'KTMT-K45', 'Female', 2024),
('SV024', 'Đặng Văn Bình', '2006-12-12', '00120061212123', '0900000024', 'binh.dv@student.edu', 'KTMT', 'KTMT_NH', 'KTMT-K45', 'Male', 2024),
('SV025', 'Nguyễn Thị Chi', '2007-01-01', '00120070101123', '0900000025', 'chi.nt@student.edu', 'KHDL', 'KHDL_DS', 'KHDL-K45', 'Female', 2024),
('SV026', 'Trần Văn Dũng', '2007-02-02', '00120070202123', '0900000026', 'dung.tv@student.edu', 'KHDL', 'KHDL_AI', 'KHDL-K45', 'Male', 2024),
('SV027', 'Lê Thị Hà', '2007-03-03', '00120070303123', '0900000027', 'ha.lt@student.edu', 'ATTT', 'ATTT_BM', 'ATTT-K45', 'Female', 2024),
('SV028', 'Phạm Văn Hòa', '2007-04-04', '00120070404123', '0900000028', 'hoa.pv@student.edu', 'ATTT', 'ATTT_AT', 'ATTT-K45', 'Male', 2024),
('SV029', 'Hoàng Thị Liên', '2007-05-05', '00120070505123', '0900000029', 'lien.ht@student.edu', 'MMT', 'MMT_M', 'MMT-K45', 'Female', 2024),
('SV030', 'Ngô Văn Nam', '2007-06-06', '00120070606123', '0900000030', 'nam.nv@student.edu', 'MMT', 'MMT_VT', 'MMT-K45', 'Male', 2024);
-- ------------------------------
-- Role
-- ------------------------------
INSERT INTO Role (RoleID, RoleName) VALUES
(1, 'admin'),
(2, 'lecturer'),
(3, 'student');

-- ------------------------------
-- Account 
-- ------------------------------
INSERT INTO Account (Username, PasswordHash, PhoneNumber, IsFirstLogin, Status, RoleID, StudentID, LecturerID, LastLogin) VALUES
('admin', 'admin', '1234567890', TRUE, 'Active', 1, NULL, NULL, NOW()),
('GV001', '123', '0912345678', TRUE, 'Active', 2, NULL, 'GV001', NOW()),
('GV002', '123', '0923456789', TRUE, 'Active', 2, NULL, 'GV002', NOW()),
('GV003', '123', '0934567890', TRUE, 'Active', 2, NULL, 'GV003', NOW()),
('GV004', '123', '0945678901', TRUE, 'Active', 2, NULL, 'GV004', NOW()),
('GV005', '123', '0956789012', TRUE, 'Active', 2, NULL, 'GV005', NOW()),
('GV006', '123', '0967890123', TRUE, 'Active', 2, NULL, 'GV006', NOW()),
('GV007', '123', '0978901234', TRUE, 'Active', 2, NULL, 'GV007', NOW()),
('GV008', '123', '0989012345', TRUE, 'Active', 2, NULL, 'GV008', NOW()),
('GV009', '123', '0990123456', TRUE, 'Active', 2, NULL, 'GV009', NOW()),
('GV010', '123', '0901234567', TRUE, 'Active', 2, NULL, 'GV010', NOW()),
('GV011', '123', '0912345678', TRUE, 'Active', 2, NULL, 'GV011', NOW()),
('GV012', '123', '0923456789', TRUE, 'Active', 2, NULL, 'GV012', NOW()),
('GV013', '123', '0934567890', TRUE, 'Active', 2, NULL, 'GV013', NOW()),
('GV014', '123', '0945678901', TRUE, 'Active', 2, NULL, 'GV014', NOW()),
('GV015', '123', '0956789012', TRUE, 'Active', 2, NULL, 'GV015', NOW()),
('SV001', '123', '0900000001', TRUE, 'Active', 3, 'SV001', NULL, NOW()),
('SV002', '123', '0900000002', TRUE, 'Active', 3, 'SV002', NULL, NOW()),
('SV003', '123', '0900000003', TRUE, 'Active', 3, 'SV003', NULL, NOW()),
('SV004', '123', '0900000004', TRUE, 'Active', 3, 'SV004', NULL, NOW()),
('SV005', '123', '0900000005', TRUE, 'Active', 3, 'SV005', NULL, NOW()),
('SV006', '123', '0900000006', TRUE, 'Active', 3, 'SV006', NULL, NOW()),
('SV007', '123', '0900000007', TRUE, 'Active', 3, 'SV007', NULL, NOW()),
('SV008', '123', '0900000008', TRUE, 'Active', 3, 'SV008', NULL, NOW()),
('SV009', '123', '0900000009', TRUE, 'Active', 3, 'SV009', NULL, NOW()),
('SV010', '123', '0900000010', TRUE, 'Active', 3, 'SV010', NULL, NOW()),
('SV011', '123', '0900000011', TRUE, 'Active', 3, 'SV011', NULL, NOW()),
('SV012', '123', '0900000012', TRUE, 'Active', 3, 'SV012', NULL, NOW()),
('SV013', '123', '0900000013', TRUE, 'Active', 3, 'SV013', NULL, NOW()),
('SV014', '123', '0900000014', TRUE, 'Active', 3, 'SV014', NULL, NOW()),
('SV015', '123', '0900000015', TRUE, 'Active', 3, 'SV015', NULL, NOW()),
('SV016', '123', '0900000016', TRUE, 'Active', 3, 'SV016', NULL, NOW()),
('SV017', '123', '0900000017', TRUE, 'Active', 3, 'SV017', NULL, NOW()),
('SV018', '123', '0900000018', TRUE, 'Active', 3, 'SV018', NULL, NOW()),
('SV019', '123', '0900000019', TRUE, 'Active', 3, 'SV019', NULL, NOW()),
('SV020', '123', '0900000020', TRUE, 'Active', 3, 'SV020', NULL, NOW()),
('SV021', '123', '0900000021', TRUE, 'Active', 3, 'SV021', NULL, NOW()),
('SV022', '123', '0900000022', TRUE, 'Active', 3, 'SV022', NULL, NOW()),
('SV023', '123', '0900000023', TRUE, 'Active', 3, 'SV023', NULL, NOW()),
('SV024', '123', '0900000024', TRUE, 'Active', 3, 'SV024', NULL, NOW()),
('SV025', '123', '0900000025', TRUE, 'Active', 3, 'SV025', NULL, NOW()),
('SV026', '123', '0900000026', TRUE, 'Active', 3, 'SV026', NULL, NOW()),
('SV027', '123', '0900000027', TRUE, 'Active', 3, 'SV027', NULL, NOW()),
('SV028', '123', '0900000028', TRUE, 'Active', 3, 'SV028', NULL, NOW()),
('SV029', '123', '0900000029', TRUE, 'Active', 3, 'SV029', NULL, NOW()),
('SV030', '123', '0900000030', TRUE, 'Active', 3, 'SV030', NULL, NOW());
-- ------------------------------
-- CourseSection
-- ------------------------------
INSERT INTO CourseSection (CourseSectionID, SubjectID, LecturerID, Semester, AcademicYear, MaxSize) VALUES
('KHMT101-A', 'KHMT101', 'GV004', 'Fall 2024', '2024-2025', 40),
('KHMT201-A', 'KHMT201', 'GV009', 'Fall 2024', '2024-2025', 35),
('KHMT301-A', 'KHMT301', 'GV014', 'Fall 2024', '2024-2025', 30),
('KTMT101-A', 'KTMT101', 'GV005', 'Fall 2024', '2024-2025', 35),
('KTMT201-A', 'KTMT201', 'GV010', 'Fall 2024', '2024-2025', 30),
('KHDL101-A', 'KHDL101', 'GV006', 'Fall 2024', '2024-2025', 30),
('KHDL201-A', 'KHDL201', 'GV011', 'Fall 2024', '2024-2025', 30),
('ATTT101-A', 'ATTT101', 'GV007', 'Fall 2024', '2024-2025', 35),
('ATTT201-A', 'ATTT201', 'GV012', 'Fall 2024', '2024-2025', 30),
('MMT101-A', 'MMT101', 'GV008', 'Fall 2024', '2024-2025', 40),
('MMT201-A', 'MMT201', 'GV013', 'Fall 2024', '2024-2025', 35),
('KHMT401-A', 'KHMT401', 'GV004', 'Spring 2025', '2024-2025', 30),
('KTMT301-A', 'KTMT301', 'GV005', 'Spring 2025', '2024-2025', 30),
('KHDL301-A', 'KHDL301', 'GV006', 'Spring 2025', '2024-2025', 30),
('ATTT301-A', 'ATTT301', 'GV007', 'Spring 2025', '2024-2025', 30);

-- ------------------------------
-- CourseRegistration
-- ------------------------------
INSERT INTO CourseRegistration (StudentID, CourseSectionID, RegistrationDate, Status) VALUES
-- Sinh viên KHMT-K45 (SV001, SV002, SV021, SV022)
('SV001', 'KHMT101-A', '2024-09-01', 'enrolled'),
('SV001', 'KHMT201-A', '2024-09-02', 'enrolled'),
('SV001', 'KHMT301-A', '2024-09-03', 'enrolled'),
('SV001', 'KHMT401-A', '2024-09-04', 'enrolled'),
('SV002', 'KHMT101-A', '2024-09-01', 'enrolled'),
('SV002', 'KHMT201-A', '2024-09-02', 'enrolled'),
('SV002', 'KHMT401-A', '2024-09-03', 'enrolled'),
('SV021', 'KHMT101-A', '2024-09-01', 'enrolled'),
('SV021', 'KHMT301-A', '2024-09-02', 'enrolled'),
('SV021', 'KHMT401-A', '2024-09-03', 'enrolled'),
('SV022', 'KHMT101-A', '2024-09-01', 'enrolled'),
('SV022', 'KHMT201-A', '2024-09-02', 'enrolled'),
-- Sinh viên KTMT-K45 (SV003, SV004, SV023, SV024)
('SV003', 'KTMT101-A', '2024-09-01', 'enrolled'),
('SV003', 'KTMT201-A', '2024-09-02', 'enrolled'),
('SV003', 'KTMT301-A', '2024-09-03', 'enrolled'),
('SV004', 'KTMT101-A', '2024-09-01', 'enrolled'),
('SV004', 'KTMT201-A', '2024-09-02', 'enrolled'),
('SV023', 'KTMT101-A', '2024-09-01', 'enrolled'),
('SV023', 'KTMT301-A', '2024-09-02', 'enrolled'),
('SV024', 'KTMT201-A', '2024-09-01', 'enrolled'),
('SV024', 'KTMT301-A', '2024-09-02', 'enrolled'),
-- Sinh viên KHDL-K45 (SV005, SV006, SV025, SV026)
('SV005', 'KHDL101-A', '2024-09-01', 'enrolled'),
('SV005', 'KHDL201-A', '2024-09-02', 'enrolled'),
('SV005', 'KHDL301-A', '2024-09-03', 'enrolled'),
('SV006', 'KHDL101-A', '2024-09-01', 'enrolled'),
('SV006', 'KHDL201-A', '2024-09-02', 'enrolled'),
('SV025', 'KHDL101-A', '2024-09-01', 'enrolled'),
('SV025', 'KHDL301-A', '2024-09-02', 'enrolled'),
('SV026', 'KHDL201-A', '2024-09-01', 'enrolled'),
('SV026', 'KHDL301-A', '2024-09-02', 'enrolled'),
-- Sinh viên ATTT-K45 (SV007, SV008, SV027, SV028)
('SV007', 'ATTT101-A', '2024-09-01', 'enrolled'),
('SV007', 'ATTT201-A', '2024-09-02', 'enrolled'),
('SV007', 'ATTT301-A', '2024-09-03', 'enrolled'),
('SV008', 'ATTT101-A', '2024-09-01', 'enrolled'),
('SV008', 'ATTT201-A', '2024-09-02', 'enrolled'),
('SV027', 'ATTT101-A', '2024-09-01', 'enrolled'),
('SV027', 'ATTT301-A', '2024-09-02', 'enrolled'),
('SV028', 'ATTT201-A', '2024-09-01', 'enrolled'),
('SV028', 'ATTT301-A', '2024-09-02', 'enrolled'),
-- Sinh viên MMT-K45 (SV009, SV010, SV029, SV030)
('SV009', 'MMT101-A', '2024-09-01', 'enrolled'),
('SV009', 'MMT201-A', '2024-09-02', 'enrolled'),
('SV010', 'MMT101-A', '2024-09-01', 'enrolled'),
('SV010', 'MMT201-A', '2024-09-02', 'enrolled'),
('SV029', 'MMT101-A', '2024-09-01', 'enrolled'),
('SV029', 'MMT201-A', '2024-09-02', 'enrolled'),
('SV030', 'MMT101-A', '2024-09-01', 'enrolled'),
('SV030', 'MMT201-A', '2024-09-02', 'enrolled'),
-- Sinh viên KHMT-K46 (SV011, SV012)
('SV011', 'KHMT101-A', '2025-01-10', 'enrolled'),
('SV011', 'KHMT201-A', '2025-01-11', 'enrolled'),
('SV011', 'KHMT401-A', '2025-01-12', 'enrolled'),
('SV012', 'KHMT101-A', '2025-01-10', 'enrolled'),
('SV012', 'KHMT301-A', '2025-01-11', 'enrolled'),
-- Sinh viên KTMT-K46 (SV013, SV014)
('SV013', 'KTMT101-A', '2025-01-10', 'enrolled'),
('SV013', 'KTMT201-A', '2025-01-11', 'enrolled'),
('SV014', 'KTMT101-A', '2025-01-10', 'enrolled'),
('SV014', 'KTMT301-A', '2025-01-11', 'enrolled'),
-- Sinh viên KHDL-K46 (SV015, SV016)
('SV015', 'KHDL101-A', '2025-01-10', 'enrolled'),
('SV015', 'KHDL201-A', '2025-01-11', 'enrolled'),
('SV015', 'KHDL301-A', '2025-01-12', 'enrolled'),
('SV016', 'KHDL101-A', '2025-01-10', 'enrolled'),
('SV016', 'KHDL301-A', '2025-01-11', 'enrolled'),
-- Sinh viên ATTT-K46 (SV017, SV018)
('SV017', 'ATTT101-A', '2025-01-10', 'enrolled'),
('SV017', 'ATTT201-A', '2025-01-11', 'enrolled'),
('SV018', 'ATTT101-A', '2025-01-10', 'enrolled'),
('SV018', 'ATTT301-A', '2025-01-11', 'enrolled'),
-- Sinh viên MMT-K46 (SV019, SV020)
('SV019', 'MMT101-A', '2025-01-10', 'enrolled'),
('SV019', 'MMT201-A', '2025-01-11', 'enrolled'),
('SV020', 'MMT101-A', '2025-01-10', 'enrolled'),
('SV020', 'MMT201-A', '2025-01-11', 'enrolled');

-- ------------------------------
-- Grade
-- ------------------------------
INSERT INTO Grade (RegistrationID, ProcessScore, FinalScore, AverageScore, GradeStatus, AcademicRank) VALUES
(1, 8.5, 9.0, 8.8, 'Finalized', 'Good'),
(2, 7.0, 6.5, 6.7, 'Finalized', 'Average'),
(3, 9.0, 9.5, 9.3, 'Finalized', 'Excellent'),
(4, 7.5, 7.0, 7.2, 'Finalized', 'Average'),
(5, 6.0, 5.5, 5.7, 'Finalized', 'Weak'),
(6, 8.0, 8.5, 8.3, 'Finalized', 'Good'),
(7, 9.5, 9.0, 9.2, 'Finalized', 'Excellent'),
(8, 7.0, 7.5, 7.3, 'Finalized', 'Average'),
(9, 8.0, 8.0, 8.0, 'Finalized', 'Good'),
(10, 6.5, 6.0, 6.2, 'Finalized', 'Average'),
(11, 9.0, 9.5, 9.3, 'Finalized', 'Excellent'),
-- Dữ liệu hoàn thành (Finalized) với nhiều mức xếp loại khác nhau
(12, 8.5, 8.0, 8.15, 'Finalized', 'Good'),
(13, 7.5, 7.8, 7.71, 'Finalized', 'Fair'),
(14, 5.0, 5.5, 5.35, 'Finalized', 'Average'),
(15, 9.5, 9.5, 9.50, 'Finalized', 'Excellent'),
(16, 4.0, 4.5, 4.35, 'Finalized', 'Weak'),
(17, 8.0, 7.5, 7.65, 'Finalized', 'Fair'),
(18, 7.0, 8.5, 8.05, 'Finalized', 'Good'),
(19, 9.0, 8.8, 8.86, 'Finalized', 'Good'),
(20, 6.0, 6.5, 6.35, 'Finalized', 'Average'),
(21, 8.5, 9.2, 8.99, 'Finalized', 'Good'),
(22, 5.5, 5.0, 5.15, 'Finalized', 'Average'),
(23, 9.8, 9.5, 9.59, 'Finalized', 'Excellent'),
(24, 7.2, 7.4, 7.34, 'Finalized', 'Fair'),
(25, 3.5, 4.0, 3.85, 'Finalized', 'Weak'),
-- Dữ liệu dạng bản nháp (Draft) - Điểm thành phần chưa đầy đủ hoặc chưa chốt xếp loại
(26, 8.0, NULL, NULL, 'Draft', NULL),
(27, 6.5, 7.0, 6.85, 'Draft', 'Fair'),
(28, NULL, 5.0, NULL, 'Draft', NULL),
(29, 9.0, 9.0, 9.00, 'Draft', 'Excellent'),
(30, 5.0, NULL, NULL, 'Draft', NULL),
(31, 7.8, 8.2, 8.08, 'Draft', 'Good');

-- ------------------------------
-- Attendance
-- ------------------------------
INSERT INTO Attendance (RegistrationID, AttendanceDate, Status) VALUES
(1, '2024-10-24', 'Present'),
(1, '2024-10-17', 'Present'),
(2, '2024-10-23', 'Present'),
(3, '2024-10-21', 'Absent'),
(4, '2024-10-24', 'Present'),
(5, '2024-10-23', 'Present'),
(6, '2024-10-24', 'Absent'),
(7, '2024-10-22', 'Present'),
(8, '2024-10-21', 'Present'),
(9, '2024-10-24', 'Present'),
(10, '2024-10-20', 'Present'),
(11, '2024-10-21', 'Present'),
-- Thêm các buổi học tiếp theo cho các sinh viên đã có sẵn (để có lịch sử điểm danh nhiều buổi)
(1, '2024-10-31', 'Present'),
(1, '2024-11-07', 'Absent'),
(2, '2024-10-30', 'Present'),
(2, '2024-11-06', 'Present'),
(3, '2024-10-28', 'Present'),
(4, '2024-10-31', 'Present'),
(5, '2024-10-30', 'Absent'),

-- Thêm dữ liệu điểm danh cho các mã đăng ký mới (từ RegistrationID 12 đến 25)
(12, '2024-10-20', 'Present'),
(12, '2024-10-27', 'Present'),
(13, '2024-10-21', 'Present'),
(14, '2024-10-22', 'Absent'),
(14, '2024-10-29', 'Present'),
(15, '2024-10-24', 'Present'),
(16, '2024-10-25', 'Present'),
(17, '2024-10-21', 'Present'),
(18, '2024-10-22', 'Present'),
(19, '2024-10-23', 'Absent'),
(19, '2024-10-30', 'Present'),
(20, '2024-10-24', 'Present'),
(21, '2024-10-25', 'Present'),
(22, '2024-10-21', 'Present'),
(23, '2024-10-22', 'Present'),
(24, '2024-10-23', 'Present'),
(25, '2024-10-24', 'Absent'),
(25, '2024-10-31', 'Present');

SHOW DATABASES;
USE sms_db;
SHOW TABLES;
SELECT * FROM account;
DESCRIBE Account;
ALTER TABLE Student
ADD COLUMN Status VARCHAR(20) NOT NULL DEFAULT 'Studying'
AFTER EnrollmentYear;
SHOW COLUMNS FROM Student;