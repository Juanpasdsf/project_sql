from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, make_response
from datetime import datetime
import pdfkit
from database import get_connection

main_bp = Blueprint('main', __name__)

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
        return redirect(url_for('main.dashboard'))
    else:
        return render_template('login.html', error="Usuario o contraseña incorrectos")


@main_bp.route('/registro')
def registro():
    return render_template('registro.html')

@main_bp.route('/clientes')
def clientes_cobrador():
    conexion = get_connection()
    cursor = conexion.cursor(dictionary=True)

    cursor.execute("""
    SELECT 
        c.cliente_id,
        c.nombre,
        c.telefono,
        c.rfc,
        c.email,
        GROUP_CONCAT(v.matricula SEPARATOR ', ') AS matriculas
    FROM clientes c
    LEFT JOIN vehiculos v ON c.cliente_id = v.cliente_id
    GROUP BY c.cliente_id
    """)

    clientes = cursor.fetchall()

    cursor.close()
    conexion.close()

    return render_template('clientes_cobrador.html', clientes=clientes)

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
                cursor.execute("SELECT cliente_id FROM vehiculos WHERE matricula = %s", (mat,))
                resultado = cursor.fetchone()

                if resultado and (not cliente_id or resultado[0] != int(cliente_id)):
                    return f"Error: La matrícula {mat} ya esta registrada"

        if cliente_id:
            cursor.execute("""
                UPDATE clientes 
                SET nombre=%s, telefono=%s, email=%s, rfc=%s
                WHERE cliente_id=%s
            """, (nombre, telefono, email, rfc, cliente_id))
            
            cursor.execute("DELETE FROM vehiculos WHERE cliente_id = %s", (cliente_id,))
        else:
            cursor.execute("""
                INSERT INTO clientes (nombre, telefono, email, rfc, fecha_registro, tipo_cliente_id)
                VALUES (%s, %s, %s, %s, CURDATE(), 1)
            """, (nombre, telefono, email, rfc))
            cliente_id = cursor.lastrowid

        for i in range(len(matriculas)):
            if matriculas[i]:  
                cursor.execute("""
                    INSERT INTO vehiculos (matricula, modelo, color, cliente_id)
                    VALUES (%s, %s, %s, %s)
                """, (matriculas[i], modelos[i], colores[i], cliente_id))

        conexion.commit()

    except Exception as e:
        conexion.rollback()
        print("Error:", e)
        return "Error en el servidor"

    finally:
        cursor.close()
        conexion.close()

    return redirect(url_for('main.clientes_cobrador'))



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
        print("Error:", e)
        return "Error al eliminar"

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
        cursor.execute("""
            SELECT e.estancia_id, e.fecha_entrada, e.cajon_id, e.matricula
            FROM estancias e
            WHERE e.fecha_salida IS NULL
            AND e.matricula = %s
        """, (identificador,))
        
        estancia = cursor.fetchone()

        if not estancia:
            return "No hay estancia activa"

        from datetime import datetime

        fecha_entrada = estancia['fecha_entrada']
        fecha_salida = datetime.now()

        tiempo = fecha_salida - fecha_entrada
        horas = tiempo.total_seconds() / 3600

        horas_totales = max(1, round(horas, 2))

        precio_hora = 20
        total = horas_totales * precio_hora

        session['pago'] = {
            'estancia_id': estancia['estancia_id'],
            'matricula': estancia['matricula'],
            'cajon_id': estancia['cajon_id'],
            'horas': horas_totales,
            'total': total,
            'fecha_entrada': str(estancia['fecha_entrada']), 
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
        return "Monto insuficiente"

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
    return render_template('pensiones.html')