CREATE DATABASE IF NOT EXISTS estacionamiento;
USE estacionamiento;

CREATE TABLE roles(
	rol_id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(30) NOT NULL
);

CREATE TABLE usuarios(
	usuario_id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL,
    email VARCHAR(50),
    username VARCHAR(30) NOT NULL UNIQUE,
    pass_word VARCHAR(50) NOT NULL,
    rol_id INT NOT NULL,
    CONSTRAINT fk_us_rol FOREIGN KEY (rol_id) REFERENCES roles(rol_id)
);

CREATE TABLE tiposclientes(
	tipo_cliente_id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(45) NOT NULL
);

CREATE TABLE clientes(
	cliente_id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL,
    telefono VARCHAR(15) NOT NULL,
    email VARCHAR(45),
    rfc VARCHAR(15) NOT NULL UNIQUE,
    fecha_registro DATE NOT NULL,
    tipo_cliente_id INT NOT NULL,
    CONSTRAINT fk_cli_tip FOREIGN KEY (tipo_cliente_id) REFERENCES tiposclientes(tipo_cliente_id)
);

CREATE TABLE vehiculos(
	matricula VARCHAR(10) PRIMARY KEY,
    modelo VARCHAR(50) NOT NULL,
    color VARCHAR(30),
    cliente_id INT NOT NULL,
    CONSTRAINT fk_ve_cli FOREIGN KEY (cliente_id) REFERENCES clientes(cliente_id)
);

CREATE TABLE pensiones(
	pension_id INT AUTO_INCREMENT PRIMARY KEY,
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE,
    descuento DECIMAL(10,2),
    usuario_id INT NOT NULL,
    matricula VARCHAR(10) NOT NULL,
    CONSTRAINT fk_pen_us FOREIGN KEY (usuario_id) REFERENCES usuarios(usuario_id),
    CONSTRAINT fk_pen_ve FOREIGN KEY (matricula) REFERENCES vehiculos(matricula)
);

CREATE TABLE tarifas(
	tarifa_id INT AUTO_INCREMENT PRIMARY KEY,
    precio_hora DECIMAL(10,2) NOT NULL,
    precio_hora_descuento DECIMAL(10,2) NOT NULL,
    horas_descuento INT NOT NULL,
    tipo_cliente_id INT NOT NULL,
    CONSTRAINT fk_tar_tip FOREIGN KEY (tipo_cliente_id) REFERENCES tiposclientes(tipo_cliente_id)
);

CREATE TABLE cajones(
	cajon_id INT AUTO_INCREMENT PRIMARY KEY,
    numero INT NOT NULL UNIQUE,
    estado ENUM('disponible', 'ocupado') NOT NULL
);

CREATE TABLE tiposservicio(
	tipo_servicio_id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(40) NOT NULL
);

CREATE TABLE estancias(
	estancia_id INT AUTO_INCREMENT PRIMARY KEY,
    fecha_entrada DATETIME NOT NULL,
    fecha_salida DATETIME,
    matricula VARCHAR(10) NOT NULL,
    cajon_id INT NOT NULL,
    tipo_servicio_id INT NOT NULL,
    usuario_id INT NOT NULL,
    CONSTRAINT fk_est_ve FOREIGN KEY (matricula) REFERENCES vehiculos(matricula),
    CONSTRAINT fk_est_caj FOREIGN KEY (cajon_id) REFERENCES cajones(cajon_id),
    CONSTRAINT fk_est_tip FOREIGN KEY (tipo_servicio_id) REFERENCES tiposservicio(tipo_servicio_id),
    CONSTRAINT fk_est_us FOREIGN KEY (usuario_id) REFERENCES usuarios(usuario_id)
);


CREATE TABLE pagos(
	pago_id INT AUTO_INCREMENT PRIMARY KEY,
    monto_total DECIMAL(10,2) NOT NULL,
    horas_totales DECIMAL(10,2) NOT NULL,
    fecha_pago DATETIME NOT NULL,
    estancia_id INT NOT NULL,
    usuario_id INT NOT NULL,
    CONSTRAINT fk_pag_est FOREIGN KEY (estancia_id) REFERENCES estancias(estancia_id),
    CONSTRAINT fk_pag_use FOREIGN KEY (usuario_id) REFERENCES usuarios(usuario_id)
);

SHOW TABLES;

INSERT INTO roles(nombre) VALUES ('admin');

INSERT INTO usuarios(nombre, email, username, pass_word, rol_id)
VALUES ('Admin', 'admin@test.com', 'admin', '1234', 1);

INSERT INTO tiposclientes (nombre) VALUES ('Normal');

USE estacionamiento;

SELECT * FROM CLIENTES;
SELECT * FROM VEHICULOS;
SELECT * FROM USUARIOS;

INSERT INTO cajones (numero, estado) VALUES (1, 'disponible');
INSERT INTO cajones (numero, estado) VALUES (2, 'disponible');
INSERT INTO cajones (numero, estado) VALUES (3, 'disponible');
INSERT INTO cajones (numero, estado) VALUES (4, 'disponible');
INSERT INTO cajones (numero, estado) VALUES (5, 'disponible');

INSERT INTO tiposservicio (nombre) VALUES ('General');
INSERT INTO tiposservicio (nombre) VALUES ('Pensionado');