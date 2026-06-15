import os

class Config:
    # Chuỗi bí mật để bảo mật session (đăng nhập)
    SECRET_KEY = "sms_project_cong_nghe_phan_mem_group11"
    
    # Cấu hình kết nối MySQL (Mn chủ động sửa lại dòng MYSQL_PASSWORD và MYSQL_USER cho đúng với cấu hình máy của mình để chạy thử dưới máy cá nhân nhé)
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'root'
    MYSQL_PASSWORD = '123456'
    MYSQL_DB = 'sms_database'
