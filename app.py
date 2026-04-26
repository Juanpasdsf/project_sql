from flask import Flask
from routes.rutas import main_bp

app = Flask(__name__)

# Configuración básica para JWT y sesiones
app.config['SECRET_KEY'] = 'mi_clave_secreta_para_jwt'

# Conectamos nuestras rutas modulares
app.register_blueprint(main_bp)

if __name__ == '__main__':
    app.run(debug=True, port=5000)