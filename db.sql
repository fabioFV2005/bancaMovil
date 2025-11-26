CREATE DATABASE IF NOT EXISTS sistema_cobros_simple 
CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE sistema_cobros_simple;

CREATE TABLE IF NOT EXISTS tarjeteros (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    ubicacion VARCHAR(200),
    saldo DECIMAL(10,2) DEFAULT 0.00,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activo BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ci VARCHAR(50) UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(100),
    telefono VARCHAR(20),
    saldo DECIMAL(10,2) DEFAULT 0.00,
    password_hash VARCHAR(255),
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activo BOOLEAN DEFAULT TRUE,
    INDEX idx_ci (ci)
);

CREATE TABLE IF NOT EXISTS tarjetas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    uid VARCHAR(50) UNIQUE,
    pin VARCHAR(4) NOT NULL,
    id_usuario INT NOT NULL,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    activa BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id) ON DELETE CASCADE,
    INDEX idx_uid (uid),
    INDEX idx_usuario (id_usuario),
    COMMENT 'UID puede ser NULL para usuarios sin tarjeta RFID (solo web)'
);

CREATE TABLE IF NOT EXISTS transacciones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    id_tarjetero INT NOT NULL,
    id_usuario INT NOT NULL,
    monto DECIMAL(10,2) NOT NULL,
    tipo ENUM('cobro', 'recarga') DEFAULT 'cobro',
    estado ENUM('aprobada', 'rechazada', 'pendiente') DEFAULT 'aprobada',
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    descripcion TEXT,
    FOREIGN KEY (id_tarjetero) REFERENCES tarjeteros(id),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id),
    INDEX idx_fecha (fecha),
    INDEX idx_tarjetero (id_tarjetero),
    INDEX idx_usuario (id_usuario)
);

INSERT INTO tarjeteros (nombre, ubicacion, saldo) VALUES
('Tarjetero #1', 'Entrada Principal', 0);

-- Usuarios de prueba (password: 1234 para todos)
INSERT INTO usuarios (ci, nombre, email, telefono, saldo, password_hash) VALUES
('1234567', 'Juan Perez', 'juan@gmail.com', '77777777', 150.00, '$2b$12$MPN8yv7FBX8xUazSoLKABuRPGiRd5djboXcq5Er2RklSsCTp7nPHa'),
('7654321', 'Maria Lopez', 'maria@gmail.com', '71234567', 200.00, '$2b$12$MPN8yv7FBX8xUazSoLKABuRPGiRd5djboXcq5Er2RklSsCTp7nPHa'),
('1111111', 'Carlos Ruiz', 'carlos@gmail.com', '79999999', 75.50, '$2b$12$MPN8yv7FBX8xUazSoLKABuRPGiRd5djboXcq5Er2RklSsCTp7nPHa'),
('9876543', 'Ana Garcia', 'ana@gmail.com', '72345678', 300.00, '$2b$12$MPN8yv7FBX8xUazSoLKABuRPGiRd5djboXcq5Er2RklSsCTp7nPHa'),
('5555555', 'Pedro Martinez', 'pedro@gmail.com', '78888888', 125.75, '$2b$12$MPN8yv7FBX8xUazSoLKABuRPGiRd5djboXcq5Er2RklSsCTp7nPHa'),
('3333333', 'Sofia Torres', 'sofia@gmail.com', '76543210', 450.00, '$2b$12$MPN8yv7FBX8xUazSoLKABuRPGiRd5djboXcq5Er2RklSsCTp7nPHa'),
('2222222', 'Luis Gomez', 'luis@gmail.com', '73456789', 89.25, '$2b$12$MPN8yv7FBX8xUazSoLKABuRPGiRd5djboXcq5Er2RklSsCTp7nPHa'),
('8888888', 'Laura Silva', 'laura@gmail.com', '79876543', 175.50, '$2b$12$MPN8yv7FBX8xUazSoLKABuRPGiRd5djboXcq5Er2RklSsCTp7nPHa');

INSERT INTO tarjetas (uid, pin, id_usuario) VALUES
('A1B2C3D4', '1234', 1),
('E5F6G7H8', '1234', 2),
('I9J0K1L2', '1234', 3),
('M3N4O5P6', '1234', 4),
('Q7R8S9T0', '1234', 5),
('U1V2W3X4', '1234', 6),
('Y5Z6A7B8', '1234', 7),
('C9D0E1F2', '1234', 8);

CREATE TABLE IF NOT EXISTS tarjetas_recarga (
    id INT AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(20) UNIQUE NOT NULL,
    monto DECIMAL(10,2) NOT NULL,
    usado BOOLEAN DEFAULT FALSE,
    id_usuario_uso INT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_uso TIMESTAMP NULL,
    FOREIGN KEY (id_usuario_uso) REFERENCES usuarios(id),
    INDEX idx_codigo (codigo),
    INDEX idx_usado (usado)
);

-- Tarjetas de recarga de 10, 50 y 100 Bs
INSERT INTO tarjetas_recarga (codigo, monto) VALUES
-- Tarjetas de 10 Bs
('REC10-A1B2C3', 10.00),
('REC10-D4E5F6', 10.00),
('REC10-G7H8I9', 10.00),
('REC10-J0K1L2', 10.00),
('REC10-M3N4O5', 10.00),
-- Tarjetas de 50 Bs
('REC50-P6Q7R8', 50.00),
('REC50-S9T0U1', 50.00),
('REC50-V2W3X4', 50.00),
('REC50-Y5Z6A7', 50.00),
('REC50-B8C9D0', 50.00),
-- Tarjetas de 100 Bs
('REC100-E1F2G3', 100.00),
('REC100-H4I5J6', 100.00),
('REC100-K7L8M9', 100.00),
('REC100-N0O1P2', 100.00),
('REC100-Q3R4S5', 100.00);

CREATE TABLE IF NOT EXISTS transferencias (
    id INT AUTO_INCREMENT PRIMARY KEY,
    id_origen INT NOT NULL,
    id_destino INT NOT NULL,
    monto DECIMAL(10,2) NOT NULL,
    descripcion TEXT,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_origen) REFERENCES usuarios(id),
    FOREIGN KEY (id_destino) REFERENCES usuarios(id),
    INDEX idx_fecha (fecha),
    INDEX idx_origen (id_origen),
    INDEX idx_destino (id_destino)
);

INSERT INTO transacciones (id_tarjetero, id_usuario, monto, tipo, estado, descripcion) VALUES
(1, 1, 10.00, 'cobro', 'aprobada', 'Compra en cafetería'),
(1, 2, 15.50, 'cobro', 'aprobada', 'Pago de transporte'),
(1, 3, 5.00, 'cobro', 'aprobada', 'Compra en tienda'),
(1, 1, 50.00, 'recarga', 'aprobada', 'Recarga efectivo'),
(1, 4, 25.00, 'cobro', 'aprobada', 'Pago de almuerzo'),
(1, 2, 100.00, 'recarga', 'aprobada', 'Recarga banco');