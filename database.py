import mysql.connector
from config import Config


def get_db_connection():

    try:

        connection = mysql.connector.connect(
            host=Config.MYSQL_HOST,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DB
        )

        return connection

    except mysql.connector.Error as err:

        print("Lỗi kết nối MySQL:", err)

        return None
