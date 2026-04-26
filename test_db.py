from database import get_connection

try:
    conexion = get_connection();
    print("Conexion exitosa a la base de datos")
    conexion.close()
except Exception as e:
    print("Error", e)