
CREATE DATABASE sms_database;
USE sms_database;

CREATE TABLE account (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    password VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL
);
INSERT INTO account(username,password,role)
VALUES
('admin','123456','admin'),
('mytien','123456','lecturer'),
('kimlien','051306014473','student');