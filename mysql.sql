CREATE DATABASE platedb;
USE platedb;

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(100) UNIQUE,
    password VARCHAR(255),
    role ENUM('user', 'admin') DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE vehicle_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    plate_number VARCHAR(20),
    image_path VARCHAR(255),
    entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    exit_time TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

INSERT INTO users (name, email, password, role) 
VALUES ('Admin', 'admin@plate.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQyCgK0nP9z5R0RGE2KlWQm.6', 'admin');