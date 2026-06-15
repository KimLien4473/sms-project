import os

class Config:
    # Chuỗi bí mật để bảo mật session (đăng nhập)
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'ma-bao-mat-chu-tich-nhom-sms'
    
    # Cấu hình kết nối MySQL (Mn chủ động sửa lại dòng MYSQL_PASSWORD và MYSQL_USER cho đúng với cấu hình máy của mình để chạy thử dưới máy cá nhân nhé)
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'root'
    MYSQL_PASSWORD = 'your_password'
    MYSQL_DB = 'sms_database'
