import os

class Config:
    # Chuỗi bí mật để bảo mật session (đăng nhập)
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'ma-bao-mat-chu-tich-nhom-sms'
    
    # Cấu hình kết nối MySQL (Thay đổi user, password, db_name theo thực tế của nhóm)
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'root'
    MYSQL_PASSWORD = 'your_password'
    MYSQL_DB = 'sms_database'
