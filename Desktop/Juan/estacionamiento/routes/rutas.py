from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, make_response
from datetime import datetime
import pdfkit
from database import get_connection
import calendar

main_bp = Blueprint('main', __name__)

from functools import wraps
from flask import session, redirect

def requiere_rol(*roles_permitidos):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):

            if 'rol_id' not in session:
                return redirect('/')

            if session['rol_id'] not in roles_permitidos:
                return redirect('/control')

            return f(*args, **kwargs)
        return wrapper
    return decorator

@main_bp.route('/')
def index():
    return render_template('login.html')


@main_bp.route('/login', methods=['POST'])
def procesar_login():
    usuario = request.form.get('usuario')
    password = request.form.get('password')
    
    conexion = get_connection()
    cursor = conexion.cursor(dictionary=True)
    
    query = "SELECT * FROM usuarios WHERE username = %s AND pass_word = %s"
    cursor.execute(query, (usuario, password))
    
    user = cursor.fetchone()
    
    cursor.close()
    conexion.close()
    
    if user:
        session['usuario_id'] = user['usuario_id']
        session['usuario'] = user['username']
        session['rol_id'] = user['rol_id']

        if user['rol_id'] == 1:  
            return redirect(url_for('main.dashboard'))
        else:  
            return redirect(url_for('main.control'))

    return render_template('login.html', error="Usuario o contraseña incorrectos")
@main_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.index')) 

@main_bp.route('/registro')
def registro():
    return render_template('registro.html')

@main_bp.route('/procesar_registro', methods=['POST'])
def procesar_registro():
    nombre = request.form.get('nombre')
    usuario = request.form.get('usuario')
    password = request.form.get('password')
    rol_id = request.form.get('rol_id')  
    conexion = get_connection()
    cursor = conexion.cursor()

    try:
        cursor.execute("SELECT * FROM usuarios WHERE username = %s", (usuario,))
        if cursor.fetchone():
            return "Error: El usuario ya existe"

        cursor.execute("""
            INSERT INTO usuarios (nombre, username, pass_word, rol_id)
            VALUES (%s, %s, %s, %s)
        """, (nombre, usuario, password, rol_id))

        conexion.commit()
        return redirect(url_for('main.index'))

    except Exception as e:
        conexion.rollback()
        return f"Error: {e}"

    finally:
        cursor.close()
        conexion.close()

@main_bp.route('/clientes')
@requiere_rol(1,2)
def clientes_cobrador():
    conexion = get_connection()
    cursor = conexion.cursor(dictionary=True)

    cursor.execute("""
    SELECT 
        c.cliente_id, c.nombre, c.telefono, c.rfc, c.email,
        GROUP_CONCAT(v.matricula SEPARATOR ', ') AS matriculas
    FROM clientes c
    LEFT JOIN vehiculos v ON c.cliente_id = v.cliente_id
    GROUP BY c.cliente_id
    """)
    clientes = cursor.fetchall()
    
    cursor.close()
    conexion.close()

    # ¡NUEVO!: Atrapamos el error si venimos de un intento fallido de eliminación
    error_msg = request.args.get('error')
    mensaje_error = None
    if error_msg == 'historial':
        mensaje_error = "No se puede eliminar este cliente porque ya tiene historial de estancias o pensiones registradas."

    return render_template('clientes_cobrador.html', clientes=clientes, error_db=mensaje_error)

@main_bp.route('/obtener_vehiculos/<int:id>')
def obtener_vehiculos(id):
    conexion = get_connection()
    cursor = conexion.cursor(dictionary=True)

    cursor.execute("""
        SELECT matricula, modelo, color 
        FROM vehiculos 
        WHERE cliente_id = %s
    """, (id,))

    vehiculos = cursor.fetchall()

    cursor.close()
    conexion.close()

    return jsonify(vehiculos)


@main_bp.route('/procesar_cliente', methods=['POST'])
def procesar_cliente():
    cliente_id = request.form.get('cliente_id')
    nombre = request.form.get('nombre')
    telefono = request.form.get('telefono')
    rfc = request.form.get('rfc')
    email = request.form.get('email')
    
    # EL CAMBIO ESTÁ AQUÍ: Si viene vacío, le asignamos 1 por defecto
    tipo_cliente_id = request.form.get('tipo_cliente_id') or 1

    matriculas = request.form.getlist('matricula[]')
    modelos = request.form.getlist('modelo[]')
    colores = request.form.getlist('color[]')

    conexion = get_connection()
    cursor = conexion.cursor()

    try:
        if cliente_id:
            cursor.execute("""
                SELECT cliente_id FROM clientes 
                WHERE rfc = %s AND cliente_id != %s
            """, (rfc, cliente_id))
        else:
            cursor.execute("SELECT cliente_id FROM clientes WHERE rfc = %s", (rfc,))

        if cursor.fetchone():
            return "Error: El RFC ya esta registrado"

        for mat in matriculas:
            if mat:
                cursor.execute("""
                    SELECT cliente_id 
                    FROM vehiculos 
                    WHERE matricula = %s
                """, (mat,))
                
                resultado = cursor.fetchone()

                if resultado and (not cliente_id or resultado[0] != int(cliente_id)):
                    return f"Error: La matrícula {mat} ya esta registrada"

        if cliente_id:
            cursor.execute("""
                UPDATE clientes 
                SET nombre=%s, telefono=%s, email=%s, rfc=%s, tipo_cliente_id=%s
                WHERE cliente_id=%s
            """, (nombre, telefono, email, rfc, tipo_cliente_id, cliente_id))
        else:
            cursor.execute("""
                INSERT INTO clientes (nombre, telefono, email, rfc, fecha_registro, tipo_cliente_id)
                VALUES (%s, %s, %s, %s, CURDATE(), %s)
            """, (nombre, telefono, email, rfc, tipo_cliente_id))

            cliente_id = cursor.lastrowid

        cursor.execute("SELECT matricula FROM vehiculos WHERE cliente_id = %s", (cliente_id,))
        vehiculos_bd = set([v[0] for v in cursor.fetchall()])
        vehiculos_form = set([m for m in matriculas if m])

        eliminar = vehiculos_bd - vehiculos_form

        for mat in eliminar:
            cursor.execute("SELECT 1 FROM estancias WHERE matricula = %s LIMIT 1", (mat,))
            
            if cursor.fetchone():
                cursor.execute("""
                    UPDATE vehiculos
                    SET cliente_id = NULL
                    WHERE matricula = %s
                """, (mat,))
            else:
                cursor.execute("DELETE FROM vehiculos WHERE matricula = %s", (mat,))

        for i in range(len(matriculas)):
            mat = matriculas[i]

            if mat and mat not in vehiculos_bd:
                cursor.execute("""
                    INSERT INTO vehiculos (matricula, modelo, color, cliente_id)
                    VALUES (%s, %s, %s, %s)
                """, (mat, modelos[i], colores[i], cliente_id))

        conexion.commit()
        return redirect('/clientes')

    except Exception as e:
        conexion.rollback()
        return f"Error: {e}"

    finally:
        cursor.close()
        conexion.close()

@main_bp.route('/eliminar_cliente/<int:id>')
def eliminar_cliente(id):
    conexion = get_connection()
    cursor = conexion.cursor()

    try:
        cursor.execute("DELETE FROM vehiculos WHERE cliente_id = %s", (id,))
        cursor.execute("DELETE FROM clientes WHERE cliente_id = %s", (id,))
        conexion.commit()
    except Exception as e:
        conexion.rollback()
        print("Error al eliminar cliente:", e)
        # ¡EL CAMBIO CLAVE!: En lugar de devolver texto, redirigimos mandando una señal de error
        return redirect(url_for('main.clientes_cobrador', error="historial"))
    finally:
        cursor.close()
        conexion.close()

    return redirect(url_for('main.clientes_cobrador'))

@main_bp.route('/entrada/<matricula>/<int:cajon>')
def entrada(matricula, cajon):

    conexion = get_connection()
    cursor = conexion.cursor()

    try:
        cursor.execute("""
            SELECT * FROM estancias
            WHERE matricula = %s AND fecha_salida IS NULL
        """, (matricula,))

        if cursor.fetchone():
            return "El vehículo ya está dentro"

        cursor.execute("""
            INSERT INTO estancias (
                fecha_entrada,
                matricula,
                cajon_id,
                tipo_servicio_id,
                usuario_id
            )
            VALUES (NOW(), %s, %s, 1, 1)
        """, (matricula, cajon))

        cursor.execute("""
            UPDATE cajones SET estado = 'ocupado'
            WHERE cajon_id = %s
        """, (cajon,))

        conexion.commit()

    except Exception as e:
        conexion.rollback()
        print(e)
        return "Error"

    finally:
        cursor.close()
        conexion.close()

    return redirect(url_for('main.control'))


@main_bp.route('/dashboard')
@requiere_rol(1)
def dashboard():
    conexion = get_connection()
    cursor = conexion.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM estancias
            WHERE DATE(fecha_entrada) = CURDATE()
        """)
        kpi_movimientos = cursor.fetchone()['total']

        cursor.execute("""
            SELECT IFNULL(SUM(monto_total),0) AS total
            FROM pagos
            WHERE DATE(fecha_pago) = CURDATE()
        """)
        kpi_ingresos = float(cursor.fetchone()['total'])
        chart_ingresos = [
            kpi_ingresos,
            kpi_ingresos * 0.6,
            kpi_ingresos * 0.2
        ]

        cursor.execute("""
            SELECT MONTH(fecha_entrada) AS mes, COUNT(*) AS total
            FROM estancias
            GROUP BY mes
            ORDER BY mes
        """)
        data = cursor.fetchall()

        chart_entradas = [int(row['total']) for row in data]

        chart_demanda = chart_entradas

        cursor.execute("""
            SELECT HOUR(fecha_entrada) AS hora, COUNT(*) AS total
            FROM estancias
            GROUP BY hora
            ORDER BY total DESC
            LIMIT 3
        """)
        data = cursor.fetchall()
        chart_horarios = [int(row['total']) for row in data]

        chart_ingresos = [kpi_ingresos, kpi_ingresos * 0.6, kpi_ingresos * 0.2]

        kpi_mes_pico = "N/A"
        kpi_horario_pico = "N/A"

        cursor.execute("SELECT usuario_id AS id, username AS nombre FROM usuarios")
        lista_cobradores = cursor.fetchall()

    except Exception as e:
        print(e)
        return "Error en dashboard"

    finally:
        cursor.close()
        conexion.close()

    return render_template('dashboard.html',
        kpi_movimientos=kpi_movimientos,
        kpi_ingresos=kpi_ingresos,
        kpi_mes_pico=kpi_mes_pico,
        kpi_horario_pico=kpi_horario_pico,
        chart_entradas=chart_entradas,
        chart_demanda=chart_demanda,
        chart_horarios=chart_horarios,
        chart_ingresos=chart_ingresos,
        lista_cobradores=lista_cobradores
    )

@main_bp.route('/api/dashboard')
@requiere_rol(1)
def api_dashboard():
    fecha = request.args.get('fecha')
    usuario = request.args.get('usuario')
    anio = request.args.get('anio')

    conexion = get_connection()
    cursor = conexion.cursor(dictionary=True)

    try:
        filtro = "1=1"
        params = []

        if fecha:
            filtro += " AND DATE(e.fecha_entrada) = %s"
            params.append(fecha)

        if anio:
            filtro += " AND YEAR(e.fecha_entrada) = %s"
            params.append(anio)

        if usuario and usuario != "todos":
            filtro += " AND e.usuario_id = %s"
            params.append(usuario)

        cursor.execute(f"""
            SELECT MONTH(e.fecha_entrada) AS mes, COUNT(*) AS total
            FROM estancias e
            WHERE {filtro}
            GROUP BY mes
            ORDER BY mes
        """, tuple(params))
        data = cursor.fetchall()

        entradas = [row['total'] for row in data]

        cursor.execute(f"""
            SELECT MONTH(p.fecha_pago) AS mes, SUM(p.monto_total) AS total
            FROM pagos p
            JOIN estancias e ON p.estancia_id = e.estancia_id
            WHERE {filtro}
            GROUP BY mes
            ORDER BY mes
        """, tuple(params))
        data_ingresos = cursor.fetchall()

        ingresos = [float(row['total']) for row in data_ingresos]

        cursor.execute(f"""
            SELECT HOUR(e.fecha_entrada) AS hora, COUNT(*) AS total
            FROM estancias e
            WHERE {filtro}
            GROUP BY hora
            ORDER BY total DESC
            LIMIT 1
        """, tuple(params))
        hora_pico = cursor.fetchone()

        kpi_horario_pico = f"{hora_pico['hora']}:00" if hora_pico else "N/A"

        cursor.execute(f"""
            SELECT MONTH(e.fecha_entrada) AS mes, COUNT(*) AS total
            FROM estancias e
            WHERE {filtro}
            GROUP BY mes
            ORDER BY total DESC
            LIMIT 1
        """, tuple(params))
        mes_pico = cursor.fetchone()

        kpi_mes_pico = mes_pico['mes'] if mes_pico else "N/A"

        cursor.execute(f"""
            SELECT COUNT(*) AS total
            FROM estancias e
            WHERE {filtro}
        """, tuple(params))
        kpi_movimientos = cursor.fetchone()['total']

        cursor.execute(f"""
            SELECT IFNULL(SUM(p.monto_total),0) AS total
            FROM pagos p
            JOIN estancias e ON p.estancia_id = e.estancia_id
            WHERE {filtro}
        """, tuple(params))
        kpi_ingresos = float(cursor.fetchone()['total'])

        return jsonify({
            "entradas": entradas,
            "demanda": entradas,
            "horarios": [hora_pico['total']] if hora_pico else [],
            "ingresos": ingresos,

            "kpi_movimientos": kpi_movimientos,
            "kpi_ingresos": kpi_ingresos,
            "kpi_mes_pico": kpi_mes_pico,
            "kpi_horario_pico": kpi_horario_pico
        })

    except Exception as e:
        print(e)
        return jsonify({"error": "Error en API"})

    finally:
        cursor.close()
        conexion.close()

@main_bp.route('/control')
@requiere_rol(1,2)
def control():
    conexion = get_connection()
    cursor = conexion.cursor(dictionary=True)

    cursor.execute("""
        SELECT c.cajon_id, c.numero, c.estado, v.matricula
        FROM cajones c
        LEFT JOIN estancias e ON c.cajon_id = e.cajon_id AND e.fecha_salida IS NULL
        LEFT JOIN vehiculos v ON e.matricula = v.matricula
    """)
    cajones = cursor.fetchall()

    capacidad_total = len(cajones)
    lugares_ocupados = sum(1 for c in cajones if c['estado'] == 'ocupado')
    lugares_libres = capacidad_total - lugares_ocupados

    cursor.close()
    conexion.close()

    return render_template(
        'control.html',
        capacidad_total=capacidad_total,
        lugares_libres=lugares_libres,
        lugares_ocupados=lugares_ocupados,
        lista_cajones=cajones,
        ticket_generado=False
    )

@main_bp.route('/registrar_entrada', methods=['POST'])
def registrar_entrada():
    identificador = request.form.get('identificador')

    conexion = get_connection()
    cursor = conexion.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT v.matricula, c.cliente_id
            FROM vehiculos v
            JOIN clientes c ON v.cliente_id = c.cliente_id
            WHERE v.matricula = %s OR c.nombre LIKE %s
        """, (identificador, f"%{identificador}%"))

        vehiculo = cursor.fetchone()

        if not vehiculo:
            return "Vehículo no encontrado"

        cursor.execute("SELECT * FROM cajones WHERE estado = 'disponible' LIMIT 1")
        cajon = cursor.fetchone()

        if not cajon:
            return "No hay lugares disponibles"

        cursor.execute("""
            INSERT INTO estancias (fecha_entrada, matricula, cajon_id, tipo_servicio_id, usuario_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (datetime.now(), vehiculo['matricula'], cajon['cajon_id'], 1, 1))

        estancia_id = cursor.lastrowid

        cursor.execute("""
            UPDATE cajones SET estado = 'ocupado'
            WHERE cajon_id = %s
        """, (cajon['cajon_id'],))

        conexion.commit()

    except Exception as e:
        conexion.rollback()
        print(e)
        return "Error en entrada"

    finally:
        cursor.close()
        conexion.close()

    conexion = get_connection()
    cursor = conexion.cursor(dictionary=True)

    cursor.execute("""
        SELECT c.cajon_id, c.numero, c.estado, v.matricula
        FROM cajones c
        LEFT JOIN estancias e ON c.cajon_id = e.cajon_id AND e.fecha_salida IS NULL
        LEFT JOIN vehiculos v ON e.matricula = v.matricula
    """)
    cajones = cursor.fetchall()

    capacidad_total = len(cajones)
    lugares_ocupados = sum(1 for c in cajones if c['estado'] == 'ocupado')
    lugares_libres = capacidad_total - lugares_ocupados

    cursor.close()
    conexion.close()

    return render_template(
        'control.html',
        capacidad_total=capacidad_total,
        lugares_libres=lugares_libres,
        lugares_ocupados=lugares_ocupados,
        lista_cajones=cajones,
        ticket_generado=True,
        ticket_cajon=cajon['numero'],
        ticket_folio=estancia_id
    )

@main_bp.route('/registrar_salida', methods=['POST'])
def registrar_salida():
    identificador = request.form.get('identificador')

    conexion = get_connection()
    cursor = conexion.cursor(dictionary=True)

    try:
        # 1. Buscar estancia activa
        cursor.execute("""
            SELECT e.estancia_id, e.fecha_entrada, e.cajon_id, e.matricula
            FROM estancias e
            WHERE e.fecha_salida IS NULL
            AND e.matricula = %s
        """, (identificador,))
        
        estancia = cursor.fetchone()

        if not estancia:
            return "No hay estancia activa"

        # 2. Calcular tiempo
        from datetime import datetime
        import math

        fecha_entrada = estancia['fecha_entrada']
        fecha_salida = datetime.now()

        tiempo = fecha_salida - fecha_entrada
        horas = tiempo.total_seconds() / 3600

        # 🔥 COBRO POR HORA COMPLETA
        horas_totales = max(1, math.ceil(horas))

        # 3. Obtener tipo de cliente
        cursor.execute("""
            SELECT c.tipo_cliente_id
            FROM vehiculos v
            JOIN clientes c ON v.cliente_id = c.cliente_id
            WHERE v.matricula = %s
        """, (estancia['matricula'],))

        cliente = cursor.fetchone()
        tipo_cliente = cliente['tipo_cliente_id'] if cliente else 1

        # 4. Definir tarifas
        if tipo_cliente == 2:  # FRECUENTE
            tarifa_normal = 26
            tarifa_descuento = 22
        else:  # DE PASO
            tarifa_normal = 30
            tarifa_descuento = 25

        # 5. Calcular total con regla de 5 horas
        if horas_totales <= 5:
            total = horas_totales * tarifa_normal
            horas_descuento = 0
        else:
            horas_descuento = horas_totales - 5
            total = (5 * tarifa_normal) + (horas_descuento * tarifa_descuento)

        # 6. Guardar en sesión
        session['pago'] = {
            'estancia_id': estancia['estancia_id'],
            'matricula': estancia['matricula'],
            'cajon_id': estancia['cajon_id'],
            'horas': horas_totales,
            'horas_descuento': horas_descuento,
            'tipo_cliente': tipo_cliente,
            'tarifa_normal': tarifa_normal,
            'tarifa_descuento': tarifa_descuento,
            'total': total,
            'fecha_entrada': str(fecha_entrada),
            'fecha_salida': str(fecha_salida)
        }

    except Exception as e:
        print(e)
        return "Error"

    finally:
        cursor.close()
        conexion.close()

    return redirect(url_for('main.cobro'))

@main_bp.route('/cobro')
def cobro():
    pago = session.get('pago')

    if not pago:
        return redirect(url_for('main.control'))

    return render_template('cobro.html', pago=pago)

@main_bp.route('/procesar_pago', methods=['POST'])
def procesar_pago():
    pago = session.get('pago')
    if not pago:
        return "No hay datos de pago en sesión"

    monto_recibido = float(request.form.get('monto_recibido') or 0)

    total = float(pago['total'])
    horas = float(pago['horas'])
    estancia_id = pago['estancia_id']
    cajon_id = pago['cajon_id']

    if monto_recibido < total:
        return render_template('cobro.html', pago=pago, error="⚠️ El monto recibido no alcanza para cubrir el total.")

    cambio = monto_recibido - total

    conexion = get_connection()
    cursor = conexion.cursor()

    try:
        conexion.start_transaction()

        cursor.execute("""
            UPDATE estancias
            SET fecha_salida = NOW()
            WHERE estancia_id = %s
        """, (estancia_id,))

        cursor.execute("""
            UPDATE cajones
            SET estado = 'disponible'
            WHERE cajon_id = %s
        """, (cajon_id,))

        usuario_id = session.get('usuario_id', 1)
        
        cursor.execute("""
            INSERT INTO pagos (monto_total, horas_totales, fecha_pago, estancia_id, usuario_id)
            VALUES (%s, %s, NOW(), %s, %s)
        """, (
            total,
            horas,
            estancia_id,
            usuario_id
        ))
        
        pago_id = cursor.lastrowid

        conexion.commit()
        
        session['pago_final'] = {
            'matricula': pago['matricula'],
            'horas': horas,
            'total': total,
            'cambio': cambio,
            'fecha': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        session.pop('pago', None)

    except Exception as e:
        conexion.rollback()
        print("Error en pago:", e)
        return "Error al procesar pago"

    finally:
        cursor.close()
        conexion.close()
        
    return redirect(url_for('main.ticket', id=pago_id))


@main_bp.route('/historial')
@requiere_rol(1)
def historial():
    conexion = get_connection()
    cursor = conexion.cursor(dictionary=True)

    cursor.execute("""
        SELECT p.*, e.matricula
        FROM pagos p
        JOIN estancias e ON p.estancia_id = e.estancia_id
        ORDER BY p.fecha_pago DESC
    """)

    pagos = cursor.fetchall()

    cursor.close()
    conexion.close()

    return render_template('historial.html', pagos=pagos)

@main_bp.route('/ticket/<int:id>')
def ticket(id):
    conexion = get_connection()
    cursor = conexion.cursor(dictionary=True)

    cursor.execute("""
        SELECT p.*, e.matricula
        FROM pagos p
        JOIN estancias e ON p.estancia_id = e.estancia_id
        WHERE p.pago_id = %s
    """, (id,))

    pago = cursor.fetchone()

    cursor.close()
    conexion.close()

    if not pago:
        return redirect(url_for('main.control'))

    return render_template('ticket.html', pago=pago)


@main_bp.route('/ticket_pdf/<int:id>')
def ticket_pdf(id):
    conexion = get_connection()
    cursor = conexion.cursor(dictionary=True)

    cursor.execute("""
        SELECT p.*, e.matricula
        FROM pagos p
        JOIN estancias e ON p.estancia_id = e.estancia_id
        WHERE p.pago_id = %s
    """, (id,))

    pago = cursor.fetchone()

    cursor.close()
    conexion.close()

    if not pago:
        return redirect(url_for('main.control'))

    html = render_template('ticket.html', pago=pago)

    config = pdfkit.configuration(
    wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
    )
    
    pdf = pdfkit.from_string(html, False, configuration=config)

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=ticket_{id}.pdf'

    return response

@main_bp.route('/pensiones')
def pensiones():
    conexion = get_connection()
    cursor = conexion.cursor(dictionary=True)

    # Consulta para cargar el historial de pensiones del lado izquierdo
    cursor.execute("""
        SELECT 
            p.matricula, 
            DATE_FORMAT(p.fecha_fin, '%d/%m/%Y') AS fecha_vencimiento,
            c.nombre AS nombre_cliente,
            CASE 
                WHEN p.fecha_fin < CURDATE() THEN 'vencida'
                WHEN DATEDIFF(p.fecha_fin, CURDATE()) <= 7 THEN 'por-vencer'
                ELSE 'vigente'
            END AS estado_clase,
            CASE 
                WHEN p.fecha_fin < CURDATE() THEN 'Vencida'
                WHEN DATEDIFF(p.fecha_fin, CURDATE()) <= 7 THEN 'Por Vencer'
                ELSE 'Vigente'
            END AS estado_texto
        FROM pensiones p
        JOIN vehiculos v ON p.matricula = v.matricula
        JOIN clientes c ON v.cliente_id = c.cliente_id
        ORDER BY p.fecha_fin DESC
    """)
    lista_pensiones = cursor.fetchall()
    
    cursor.close()
    conexion.close()

    return render_template('pensiones.html', lista_pensiones=lista_pensiones)


@main_bp.route('/procesar_pension', methods=['POST'])
def procesar_pension():
    identificador = request.form.get('identificador')
    fecha_inicio_str = request.form.get('fecha_inicio')
    duracion_meses = int(request.form.get('duracion'))

    conexion = get_connection()
    cursor = conexion.cursor(dictionary=True)

    try:
        # 1. Buscar al cliente
        cursor.execute("""
            SELECT v.matricula, c.cliente_id, c.nombre, c.fecha_registro
            FROM vehiculos v
            JOIN clientes c ON v.cliente_id = c.cliente_id
            WHERE v.matricula = %s OR c.rfc = %s
            LIMIT 1
        """, (identificador, identificador))

        vehiculo = cursor.fetchone()

        if not vehiculo:
            return "Error: No se encontró el vehículo o el RFC. Registre al cliente primero."

        # 1.5 ¡NUEVO! Buscar un cajón disponible
        cursor.execute("SELECT * FROM cajones WHERE estado = 'disponible' LIMIT 1")
        cajon_disponible = cursor.fetchone()
        
        if not cajon_disponible:
            return "Error: El estacionamiento está lleno, no hay cajones para asignar a la pensión."

        # 2. Calcular la fecha de finalización
        from datetime import datetime, date
        fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        
        mes_total = fecha_inicio.month - 1 + duracion_meses
        anio_fin = fecha_inicio.year + mes_total // 12
        mes_fin = mes_total % 12 + 1
        
        try:
            fecha_fin = date(anio_fin, mes_fin, fecha_inicio.day)
        except ValueError:
            dia_max = calendar.monthrange(anio_fin, mes_fin)[1]
            fecha_fin = date(anio_fin, mes_fin, dia_max)

        # 3. Validar si el cliente tiene más de 2 años
        dias_antiguedad = (fecha_inicio - vehiculo['fecha_registro']).days
        aplica_descuento = dias_antiguedad >= 730

        # 4. Calcular dinero
        precio_mensual = 1000 
        subtotal = precio_mensual * duracion_meses
        monto_descuento = (subtotal * 0.20) if aplica_descuento else 0
        total = subtotal - monto_descuento

        # 5. Guardar la pensión
        usuario_id = session.get('usuario_id', 1)
        cursor.execute("""
            INSERT INTO pensiones (fecha_inicio, fecha_fin, descuento, usuario_id, matricula)
            VALUES (%s, %s, %s, %s, %s)
        """, (fecha_inicio, fecha_fin, monto_descuento, usuario_id, vehiculo['matricula']))
        
        # 5.5 Asignar la estancia física al cajón como "Pensionado" (tipo 2)
        cursor.execute("""
            INSERT INTO estancias (fecha_entrada, matricula, cajon_id, tipo_servicio_id, usuario_id)
            VALUES (NOW(), %s, %s, 2, %s)
        """, (vehiculo['matricula'], cajon_disponible['cajon_id'], usuario_id))

        # 5.6 Marcar el cajón como ocupado
        cursor.execute("""
            UPDATE cajones SET estado = 'ocupado'
            WHERE cajon_id = %s
        """, (cajon_disponible['cajon_id'],))

        conexion.commit()

        # 6. Crear el recibo enviando el número de cajón a tu HTML
        recibo = {
            "subtotal": f"{subtotal:,.2f}",
            "aplica_descuento": aplica_descuento,
            "monto_descuento": f"{monto_descuento:,.2f}",
            "total": f"{total:,.2f}",
            "nueva_fecha_vencimiento": fecha_fin.strftime('%d/%m/%Y'),
            "cajon_asignado": cajon_disponible['numero'] # <-- Pasamos el cajón al front
        }

        # Volvemos a cargar la lista
        cursor.execute("""
            SELECT p.matricula, DATE_FORMAT(p.fecha_fin, '%d/%m/%Y') AS fecha_vencimiento, c.nombre AS nombre_cliente,
                CASE WHEN p.fecha_fin < CURDATE() THEN 'vencida' WHEN DATEDIFF(p.fecha_fin, CURDATE()) <= 7 THEN 'por-vencer' ELSE 'vigente' END AS estado_clase,
                CASE WHEN p.fecha_fin < CURDATE() THEN 'Vencida' WHEN DATEDIFF(p.fecha_fin, CURDATE()) <= 7 THEN 'Por Vencer' ELSE 'Vigente' END AS estado_texto
            FROM pensiones p JOIN vehiculos v ON p.matricula = v.matricula JOIN clientes c ON v.cliente_id = c.cliente_id ORDER BY p.fecha_fin DESC
        """)
        lista_pensiones = cursor.fetchall()

        return render_template('pensiones.html', recibo=recibo, lista_pensiones=lista_pensiones)

    except Exception as e:
        conexion.rollback()
        print("Error al procesar pensión:", e)
        return "Hubo un error interno en el servidor."
    finally:
        cursor.close()
        conexion.close()
        
@main_bp.route('/cancelar_pension/<matricula>', methods=['POST'])
def cancelar_pension(matricula):
    conexion = get_connection()
    cursor = conexion.cursor(dictionary=True)

    try:
        # 1. Encontrar en qué cajón está guardado este coche actualmente (tipo 2 = pensión)
        cursor.execute("""
            SELECT estancia_id, cajon_id 
            FROM estancias 
            WHERE matricula = %s AND fecha_salida IS NULL AND tipo_servicio_id = 2
        """, (matricula,))
        estancia = cursor.fetchone()

        if estancia:
            # 2. Liberar el cajón físicamente
            cursor.execute("""
                UPDATE cajones SET estado = 'disponible' WHERE cajon_id = %s
            """, (estancia['cajon_id'],))
            
            # 3. Marcar la salida del vehículo cerrando su estancia
            cursor.execute("""
                UPDATE estancias SET fecha_salida = NOW() WHERE estancia_id = %s
            """, (estancia['estancia_id'],))

        # 4. Caducar la pensión inmediatamente (le restamos 1 día a hoy para que ya no sea válida)
        cursor.execute("""
            UPDATE pensiones 
            SET fecha_fin = CURDATE() - INTERVAL 1 DAY 
            WHERE matricula = %s AND fecha_fin >= CURDATE()
        """, (matricula,))

        conexion.commit()

    except Exception as e:
        conexion.rollback()
        print("Error al cancelar pensión:", e)
    
    finally:
        cursor.close()
        conexion.close()

    # Redirigir de vuelta a la pantalla para ver los cambios
    return redirect(url_for('main.pensiones'))