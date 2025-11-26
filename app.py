from flask import Flask, request, jsonify, render_template, session, redirect, url_for, Response, stream_with_context
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta
from functools import wraps
import bcrypt
import secrets
import requests
import json

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Configuración simple para desarrollo
app.config['SECRET_KEY'] = 'dev-secret-key-bancamovil-2024'

# Sesiones de usuario activas (en memoria para desarrollo)
active_sessions = {}

def generar_token():
    return secrets.token_urlsafe(32)

def auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Token no proporcionado'}), 401
        
        token = auth_header.replace('Bearer ', '')
        user_id = active_sessions.get(token)
        
        if not user_id:
            return jsonify({'error': 'Token inválido o expirado'}), 401
        
        # Agregar user_id al contexto
        request.user_id = user_id
        return f(*args, **kwargs)
    return decorated_function

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',
    'database': 'sistema_cobros_simple'
}

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def validar_pin(pin):
    if not (pin.isdigit() and len(pin) == 4):
        return False, 'PIN debe tener 4 digitos numericos'
    return True, None

def validar_monto(monto):
    try:
        monto_float = float(monto)
        if monto_float <= 0:
            return False, 'Monto debe ser mayor que 0'
        return True, None
    except (ValueError, TypeError):
        return False, 'Monto inválido'

@app.route('/buscar_usuario_por_ci', methods=['POST'])
def buscar_usuario_por_ci():
    data = request.get_json()
    ci = data.get('ci')
    
    if not ci:
        return jsonify({'error': 'Falta CI'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT id, nombre, saldo, activo FROM usuarios WHERE ci = %s", (ci,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        return jsonify({
            'id': user['id'],
            'nombre': user['nombre'],
            'saldo': float(user['saldo']),
            'activo': bool(user['activo'])
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/registrar_tarjeta', methods=['POST'])
def registrar_tarjeta():
    data = request.get_json()
    uid = data.get('uid')
    pin = data.get('pin')
    id_usuario = data.get('id_usuario')
    ci = data.get('ci')
    
    # Validar PIN
    valido, error = validar_pin(pin)
    if not valido:
        return jsonify({'error': error}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Buscar usuario por CI o ID
        usuario_id = None
        if id_usuario:
            cursor.execute("SELECT id, activo FROM usuarios WHERE id = %s", (id_usuario,))
            u = cursor.fetchone()
            if not u:
                return jsonify({'error': 'El usuario no existe'}), 400
            if not u.get('activo', True):
                return jsonify({'error': 'Usuario inactivo'}), 400
            usuario_id = id_usuario
        elif ci:
            cursor.execute("SELECT id, activo FROM usuarios WHERE ci = %s", (ci,))
            u = cursor.fetchone()
            if not u:
                return jsonify({'error': 'El usuario no existe (CI no encontrado)'}), 400
            if not u.get('activo', True):
                return jsonify({'error': 'Usuario inactivo'}), 400
            usuario_id = u['id']
        else:
            return jsonify({'error': 'Proveer id_usuario o ci'}), 400
        
        # Validar que UID no esté registrada
        cursor.execute("SELECT id FROM tarjetas WHERE uid = %s", (uid,))
        if cursor.fetchone():
            return jsonify({'error': 'La tarjeta ya está registrada'}), 400
        
        # Registrar tarjeta
        cursor.execute("""
            INSERT INTO tarjetas (uid, pin, id_usuario, fecha_registro)
            VALUES (%s, %s, %s, %s)
        """, (uid, pin, usuario_id, datetime.now()))
        
        conn.commit()
        
        return jsonify({
            'mensaje': 'Tarjeta registrada exitosamente',
            'id_usuario': usuario_id
        }), 201
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/transaccion', methods=['POST'])
def realizar_transaccion():
    data = request.get_json()
    id_tarjetero = data.get('id_tarjetero')
    uid_tarjeta = data.get('uid_tarjeta')
    pin = data.get('pin')
    monto = data.get('monto')
    
    # Validaciones
    valido, error = validar_pin(pin)
    if not valido:
        return jsonify({'error': error}), 400
    
    valido, error = validar_monto(monto)
    if not valido:
        return jsonify({'error': error}), 400
    
    monto = float(monto)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        conn.start_transaction()
        
        # Verificar tarjeta y PIN
        cursor.execute("""
            SELECT t.id, t.uid, t.pin, t.id_usuario, t.activa
            FROM tarjetas t
            WHERE t.uid = %s
            FOR UPDATE
        """, (uid_tarjeta,))
        tarjeta = cursor.fetchone()
        
        if not tarjeta:
            conn.rollback()
            return jsonify({
                'error': 'Tarjeta no encontrada',
                'estado': 'rechazado',
                'detail': 'Tarjeta no registrada'
            }), 404
        if not tarjeta.get('activa', True):
            conn.rollback()
            return jsonify({
                'error': 'Tarjeta inactiva',
                'estado': 'rechazado',
                'detail': 'Tarjeta bloqueada'
            }), 400
        if tarjeta['pin'] != pin:
            conn.rollback()
            return jsonify({
                'error': 'PIN incorrecto',
                'estado': 'rechazado',
                'detail': 'PIN invalido'
            }), 401
        
        id_usuario = tarjeta['id_usuario']
        
        # Bloquear fila usuario
        cursor.execute("SELECT id, saldo, activo FROM usuarios WHERE id = %s FOR UPDATE", (id_usuario,))
        usuario = cursor.fetchone()
        
        if not usuario:
            conn.rollback()
            return jsonify({
                'error': 'Usuario no encontrado',
                'estado': 'rechazado',
                'detail': 'Usuario no existe'
            }), 404
        if not usuario.get('activo', True):
            conn.rollback()
            return jsonify({
                'error': 'Usuario inactivo',
                'estado': 'rechazado',
                'detail': 'Usuario suspendido'
            }), 400
        
        # VALIDACIÓN CRÍTICA: Verificar saldo suficiente
        saldo_usuario = float(usuario['saldo'])
        if saldo_usuario < monto:
            conn.rollback()
            faltante = monto - saldo_usuario
            return jsonify({
                'error': 'Saldo insuficiente',
                'estado': 'rechazado',
                'detail': f'Saldo insuficiente',
                'mensaje': f'Saldo: ${saldo_usuario:.2f} Necesita: ${monto:.2f}',
                'saldo_actual': saldo_usuario,
                'monto_requerido': monto,
                'faltante': faltante
            }), 400
        
        # Bloquear fila tarjetero
        cursor.execute("SELECT id, saldo, activo FROM tarjeteros WHERE id = %s FOR UPDATE", (id_tarjetero,))
        tarjetero = cursor.fetchone()
        
        if not tarjetero:
            conn.rollback()
            return jsonify({'error': 'Tarjetero no encontrado'}), 400
        if not tarjetero.get('activo', True):
            conn.rollback()
            return jsonify({'error': 'Tarjetero inactivo'}), 400
        
        # Actualizar saldos
        nuevo_saldo_usuario = round(saldo_usuario - monto, 2)
        nuevo_saldo_tarjetero = round(float(tarjetero['saldo']) + monto, 2)
        
        cursor.execute("UPDATE usuarios SET saldo = %s WHERE id = %s", (nuevo_saldo_usuario, id_usuario))
        cursor.execute("UPDATE tarjeteros SET saldo = %s WHERE id = %s", (nuevo_saldo_tarjetero, id_tarjetero))
        
        # Registrar transacción
        cursor.execute("""
            INSERT INTO transacciones (id_tarjetero, id_usuario, monto, tipo, estado, fecha)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (id_tarjetero, id_usuario, monto, 'cobro', 'aprobada', datetime.now()))
        
        conn.commit()
        
        # Obtener nombre usuario
        cursor.execute("SELECT nombre FROM usuarios WHERE id = %s", (id_usuario,))
        nombre_usuario = cursor.fetchone()['nombre']
        
        return jsonify({
            'estado': 'aprobado',
            'mensaje': 'Transacción exitosa',
            'nuevo_saldo_usuario': nuevo_saldo_usuario,
            'nombre_usuario': nombre_usuario
        }), 200
        
    except Error as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/tarjetero/<int:id_tarjetero>', methods=['GET'])
def obtener_info_tarjetero(id_tarjetero):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT * FROM tarjeteros WHERE id = %s", (id_tarjetero,))
        tarjetero = cursor.fetchone()
        
        if not tarjetero:
            return jsonify({'error': 'Tarjetero no encontrado'}), 404
        
        cursor.execute("""
            SELECT t.monto, t.fecha, u.nombre as usuario
            FROM transacciones t
            JOIN usuarios u ON t.id_usuario = u.id
            WHERE t.id_tarjetero = %s
            ORDER BY t.fecha DESC
            LIMIT 5
        """, (id_tarjetero,))
        transacciones = cursor.fetchall()
        
        # Convertir fechas a string para serialización JSON
        for trans in transacciones:
            if trans['fecha']:
                trans['fecha'] = trans['fecha'].isoformat()
        
        return jsonify({
            'tarjetero': tarjetero,
            'ultimas_transacciones': transacciones
        }), 200
        
    finally:
        cursor.close()
        conn.close()

@app.route('/consultar_saldo', methods=['POST'])
def consultar_saldo():
    data = request.get_json()
    uid_tarjeta = data.get('uid_tarjeta')
    
    if not uid_tarjeta:
        return jsonify({'error': 'Falta uid_tarjeta'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT u.saldo, u.nombre
            FROM tarjetas t
            JOIN usuarios u ON t.id_usuario = u.id
            WHERE t.uid = %s
        """, (uid_tarjeta,))
        resultado = cursor.fetchone()
        
        if not resultado:
            return jsonify({'error': 'Tarjeta no encontrada'}), 404
        
        return jsonify({
            'saldo': float(resultado['saldo']),
            'nombre': resultado['nombre']
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# ============= RUTAS WEB =============
@app.route('/')
def index():
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/admin')
def admin_panel():
    return render_template('admin.html')

# ============= AUTENTICACIÓN =============
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return jsonify({'error': 'Usuario y contraseña requeridos'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Buscar usuario por CI, email o nombre
        cursor.execute("""
            SELECT id, ci, nombre, email, password_hash, saldo, activo
            FROM usuarios 
            WHERE (ci = %s OR email = %s OR nombre = %s)
        """, (username, username, username))
        
        user = cursor.fetchone()
        
        if not user:
            print(f" Usuario no encontrado: {username}")
            return jsonify({'error': 'Usuario no encontrado. Verifica tu CI o email.'}), 401
        
        if not user.get('activo', True):
            print(f" Usuario inactivo: {username}")
            return jsonify({'error': 'Usuario inactivo. Contacta al administrador.'}), 401
        
        # Verificar contraseña
        password_valida = False
        
        if user.get('password_hash'):
            try:
                password_valida = bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8'))
                if not password_valida:
                    print(f" Contraseña incorrecta para: {user['nombre']} (CI: {user['ci']})")
                else:
                    print(f"Login exitoso: {user['nombre']} (CI: {user['ci']})")
            except Exception as e:
                print(f" Error verificando hash: {e}")
                return jsonify({'error': 'Error al verificar contraseña'}), 500
        else:
            # Si no tiene password_hash, usar el PIN de la tarjeta
            cursor.execute("SELECT pin FROM tarjetas WHERE id_usuario = %s LIMIT 1", (user['id'],))
            tarjeta = cursor.fetchone()
            if tarjeta and tarjeta['pin'] == password:
                password_valida = True
                print(f"✅ Login con PIN de tarjeta: {user['nombre']}")
            else:
                print(f"❌ PIN incorrecto para: {user['nombre']}")
        
        if not password_valida:
            return jsonify({'error': 'Contraseña incorrecta. Intenta nuevamente.'}), 401
        
        # Crear token simple
        access_token = generar_token()
        active_sessions[access_token] = user['id']
        
        print(f"Token generado para {user['nombre']}")
        
        return jsonify({
            'access_token': access_token,
            'user': {
                'id': user['id'],
                'nombre': user['nombre'],
                'email': user['email'],
                'ci': user['ci'],
                'saldo': float(user['saldo'])
            }
        }), 200
        
    except Exception as e:
        print(f"Error en login: {e}")
        return jsonify({'error': f'Error del servidor: {str(e)}'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/cambiar_password', methods=['POST'])
@auth_required
def cambiar_password():
    user_id = request.user_id
    data = request.get_json()
    password_actual = data.get('password_actual')
    password_nueva = data.get('password_nueva')
    
    if not password_actual or not password_nueva:
        return jsonify({'error': 'Contraseñas requeridas'}), 400
    
    if len(password_nueva) < 6:
        return jsonify({'error': 'Contraseña debe tener al menos 6 caracteres'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT password_hash FROM usuarios WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        # Verificar contraseña actual
        if user.get('password_hash'):
            if not bcrypt.checkpw(password_actual.encode('utf-8'), user['password_hash'].encode('utf-8')):
                return jsonify({'error': 'Contraseña actual incorrecta'}), 401
        
        # Hash nueva contraseña
        password_hash = bcrypt.hashpw(password_nueva.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        cursor.execute("UPDATE usuarios SET password_hash = %s WHERE id = %s", (password_hash, user_id))
        conn.commit()
        
        return jsonify({'mensaje': 'Contraseña actualizada exitosamente'}), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# ============= PERFIL DE USUARIO =============
@app.route('/api/perfil', methods=['GET'])
@auth_required
def obtener_perfil():
    user_id = request.user_id
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT id, ci, nombre, email, telefono, saldo, fecha_registro, activo
            FROM usuarios WHERE id = %s
        """, (user_id,))
        
        user = cursor.fetchone()
        
        if not user:
            print(f" Usuario no encontrado con ID: {user_id}")
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        print(f"Perfil cargado: {user['nombre']} (ID: {user_id})")
        
        # Obtener tarjetas del usuario
        cursor.execute("""
            SELECT id, uid, activa, fecha_registro
            FROM tarjetas WHERE id_usuario = %s
        """, (user_id,))
        tarjetas = cursor.fetchall()
        
        return jsonify({
            'usuario': {
                'id': user['id'],
                'ci': user['ci'],
                'nombre': user['nombre'],
                'email': user['email'],
                'telefono': user['telefono'],
                'saldo': float(user['saldo']),
                'fecha_registro': user['fecha_registro'].isoformat() if user['fecha_registro'] else None,
                'activo': bool(user['activo'])
            },
            'tarjetas': [{
                'id': t['id'],
                'uid': t['uid'],
                'activa': bool(t['activa']),
                'fecha_registro': t['fecha_registro'].isoformat() if t['fecha_registro'] else None
            } for t in tarjetas]
        }), 200
        
    finally:
        cursor.close()
        conn.close()

@app.route('/api/historial_transacciones', methods=['GET'])
@auth_required
def historial_transacciones():
    user_id = request.user_id
    limite = request.args.get('limite', 50, type=int)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Obtener transacciones normales (recargas y pagos RFID)
        cursor.execute("""
            SELECT t.id, t.monto, t.tipo, t.estado, t.fecha, t.descripcion,
                   tar.nombre as tarjetero_nombre
            FROM transacciones t
            LEFT JOIN tarjeteros tar ON t.id_tarjetero = tar.id
            WHERE t.id_usuario = %s
            ORDER BY t.fecha DESC
        """, (user_id,))
        
        transacciones = cursor.fetchall()
        
        # Obtener transferencias enviadas
        cursor.execute("""
            SELECT tf.id, tf.monto, tf.fecha, tf.descripcion,
                   u.nombre as destinatario_nombre, u.ci as destinatario_ci
            FROM transferencias tf
            INNER JOIN usuarios u ON tf.id_destino = u.id
            WHERE tf.id_origen = %s
            ORDER BY tf.fecha DESC
        """, (user_id,))
        
        transferencias_enviadas = cursor.fetchall()
        
        # Obtener transferencias recibidas
        cursor.execute("""
            SELECT tf.id, tf.monto, tf.fecha, tf.descripcion,
                   u.nombre as remitente_nombre, u.ci as remitente_ci
            FROM transferencias tf
            INNER JOIN usuarios u ON tf.id_origen = u.id
            WHERE tf.id_destino = %s
            ORDER BY tf.fecha DESC
        """, (user_id,))
        
        transferencias_recibidas = cursor.fetchall()
        
        # Combinar todas las transacciones
        historial = []
        
        # Agregar transacciones normales
        for tr in transacciones:
            historial.append({
                'id': tr['id'],
                'monto': float(tr['monto']),
                'tipo': tr['tipo'],
                'estado': tr['estado'],
                'fecha': tr['fecha'].isoformat() if tr['fecha'] else None,
                'descripcion': tr['descripcion'],
                'tarjetero': tr['tarjetero_nombre'],
                'categoria': 'transaccion'
            })
        
        # Agregar transferencias enviadas
        for tf in transferencias_enviadas:
            historial.append({
                'id': tf['id'],
                'monto': float(tf['monto']),
                'tipo': 'transferencia_enviada',
                'estado': 'completada',
                'fecha': tf['fecha'].isoformat() if tf['fecha'] else None,
                'descripcion': tf['descripcion'],
                'destinatario': f"{tf['destinatario_nombre']} (CI: {tf['destinatario_ci']})",
                'categoria': 'transferencia'
            })
        
        # Agregar transferencias recibidas
        for tf in transferencias_recibidas:
            historial.append({
                'id': tf['id'],
                'monto': float(tf['monto']),
                'tipo': 'transferencia_recibida',
                'estado': 'completada',
                'fecha': tf['fecha'].isoformat() if tf['fecha'] else None,
                'descripcion': tf['descripcion'],
                'remitente': f"{tf['remitente_nombre']} (CI: {tf['remitente_ci']})",
                'categoria': 'transferencia'
            })
        
        # Ordenar por fecha descendente y limitar
        historial.sort(key=lambda x: x['fecha'] if x['fecha'] else '', reverse=True)
        historial = historial[:limite]
        
        return jsonify({
            'transacciones': historial
        }), 200
        
    finally:
        cursor.close()
        conn.close()

# ============= TRANSFERENCIAS ENTRE USUARIOS =============
@app.route('/api/transferir', methods=['POST'])
@auth_required
def transferir():
    user_id = request.user_id
    data = request.get_json()
    
    ci_destino = data.get('ci_destino')
    monto = data.get('monto')
    descripcion = data.get('descripcion', '')
    
    # Validaciones
    valido, error = validar_monto(monto)
    if not valido:
        return jsonify({'error': error}), 400
    
    monto = float(monto)
    
    if not ci_destino:
        return jsonify({'error': 'CI de destino requerido'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        conn.start_transaction()
        
        # Bloquear usuario origen
        cursor.execute("""
            SELECT id, ci, nombre, saldo, activo 
            FROM usuarios WHERE id = %s FOR UPDATE
        """, (user_id,))
        origen = cursor.fetchone()
        
        if not origen or not origen['activo']:
            conn.rollback()
            return jsonify({'error': 'Usuario origen inactivo'}), 400
        
        # Bloquear usuario destino
        cursor.execute("""
            SELECT id, nombre, saldo, activo 
            FROM usuarios WHERE ci = %s FOR UPDATE
        """, (ci_destino,))
        destino = cursor.fetchone()
        
        if not destino:
            conn.rollback()
            return jsonify({'error': 'Usuario destino no encontrado'}), 404
        
        if not destino['activo']:
            conn.rollback()
            return jsonify({'error': 'Usuario destino inactivo'}), 400
        
        if origen['id'] == destino['id']:
            conn.rollback()
            return jsonify({'error': 'No puedes transferir a ti mismo'}), 400
        
        # Verificar saldo
        saldo_origen = float(origen['saldo'])
        if saldo_origen < monto:
            conn.rollback()
            return jsonify({'error': 'Saldo insuficiente'}), 400
        
        # Actualizar saldos
        nuevo_saldo_origen = round(saldo_origen - monto, 2)
        nuevo_saldo_destino = round(float(destino['saldo']) + monto, 2)
        
        cursor.execute("UPDATE usuarios SET saldo = %s WHERE id = %s", (nuevo_saldo_origen, origen['id']))
        cursor.execute("UPDATE usuarios SET saldo = %s WHERE id = %s", (nuevo_saldo_destino, destino['id']))
        
        # Registrar transferencia (como transacción especial)
        cursor.execute("""
            INSERT INTO transferencias (id_origen, id_destino, monto, descripcion, fecha)
            VALUES (%s, %s, %s, %s, %s)
        """, (origen['id'], destino['id'], monto, descripcion, datetime.now()))
        
        conn.commit()
        
        return jsonify({
            'mensaje': 'Transferencia exitosa',
            'nuevo_saldo': nuevo_saldo_origen,
            'destinatario': destino['nombre'],
            'monto': monto
        }), 200
        
    except Error as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/recargar_saldo', methods=['POST'])
@auth_required
def recargar_saldo():
    user_id = request.user_id
    data = request.get_json()
    
    monto = data.get('monto')
    metodo_pago = data.get('metodo_pago', 'efectivo')
    
    valido, error = validar_monto(monto)
    if not valido:
        return jsonify({'error': error}), 400
    
    monto = float(monto)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        conn.start_transaction()
        
        cursor.execute("SELECT saldo FROM usuarios WHERE id = %s FOR UPDATE", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            conn.rollback()
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        nuevo_saldo = round(float(user['saldo']) + monto, 2)
        cursor.execute("UPDATE usuarios SET saldo = %s WHERE id = %s", (nuevo_saldo, user_id))
        
        # Registrar recarga
        cursor.execute("""
            INSERT INTO transacciones (id_tarjetero, id_usuario, monto, tipo, estado, fecha, descripcion)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (1, user_id, monto, 'recarga', 'aprobada', datetime.now(), f'Recarga {metodo_pago}'))
        
        conn.commit()
        
        return jsonify({
            'mensaje': 'Recarga exitosa',
            'nuevo_saldo': nuevo_saldo
        }), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/canjear-tarjeta', methods=['POST'])
@auth_required
def canjear_tarjeta_recarga():
    user_id = request.user_id
    data = request.get_json()
    
    codigo = data.get('codigo', '').strip().upper()
    
    if not codigo:
        return jsonify({'error': 'Código de tarjeta requerido'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        conn.start_transaction()
        
        # Buscar tarjeta
        cursor.execute("""
            SELECT id, codigo, monto, usado 
            FROM tarjetas_recarga 
            WHERE codigo = %s FOR UPDATE
        """, (codigo,))
        tarjeta = cursor.fetchone()
        
        if not tarjeta:
            conn.rollback()
            return jsonify({'error': 'Código de tarjeta inválido'}), 404
        
        if tarjeta['usado']:
            conn.rollback()
            return jsonify({'error': 'Esta tarjeta ya fue utilizada'}), 400
        
        monto = float(tarjeta['monto'])
        
        # Marcar tarjeta como usada
        cursor.execute("""
            UPDATE tarjetas_recarga 
            SET usado = TRUE, 
                id_usuario_uso = %s, 
                fecha_uso = NOW() 
            WHERE id = %s
        """, (user_id, tarjeta['id']))
        
        # Actualizar saldo usuario
        cursor.execute("""
            UPDATE usuarios 
            SET saldo = saldo + %s 
            WHERE id = %s
        """, (monto, user_id))
        
        # Registrar transacción
        cursor.execute("""
            INSERT INTO transacciones (id_tarjetero, id_usuario, monto, tipo, descripcion)
            VALUES (1, %s, %s, 'recarga', %s)
        """, (user_id, monto, f'Recarga con tarjeta {codigo}'))
        
        conn.commit()
        
        # Obtener nuevo saldo
        cursor.execute("SELECT saldo FROM usuarios WHERE id = %s", (user_id,))
        nuevo_saldo = cursor.fetchone()['saldo']
        
        return jsonify({
            'mensaje': 'Tarjeta canjeada exitosamente',
            'monto': monto,
            'nuevo_saldo': float(nuevo_saldo),
            'codigo': codigo
        }), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/tarjetas-disponibles', methods=['GET'])
@auth_required
def tarjetas_disponibles():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT monto, COUNT(*) as cantidad
            FROM tarjetas_recarga
            WHERE usado = FALSE
            GROUP BY monto
            ORDER BY monto
        """)
        tarjetas = cursor.fetchall()
        
        return jsonify({
            'tarjetas': [{
                'monto': float(t['monto']),
                'cantidad': t['cantidad']
            } for t in tarjetas]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# ============= BÚSQUEDA DE USUARIOS =============
@app.route('/api/buscar_usuario', methods=['POST'])
@auth_required
def buscar_usuario():
    data = request.get_json()
    ci = data.get('ci')
    
    if not ci:
        return jsonify({'error': 'CI requerido'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT id, ci, nombre, email, saldo, activo
            FROM usuarios WHERE ci = %s
        """, (ci,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        return jsonify({
            'usuario': {
                'id': user['id'],
                'ci': user['ci'],
                'nombre': user['nombre'],
                'email': user['email'],
                'saldo': float(user['saldo']),
                'activo': bool(user['activo'])
            }
        }), 200
        
    finally:
        cursor.close()
        conn.close()

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint no encontrado'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Error interno del servidor'}), 500

# ============= ASISTENTE IA CON OLLAMA =============
@app.route('/api/ai-chat', methods=['POST'])
@auth_required
def ai_chat():
    data = request.get_json()
    pregunta = data.get('pregunta', '')
    user_id = request.user_id
    
    if not pregunta:
        return jsonify({'error': 'Pregunta requerida'}), 400
    
    def generate():
        try:
            # Obtener contexto del usuario
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Datos del usuario
            cursor.execute("""
                SELECT nombre, ci, saldo 
                FROM usuarios 
                WHERE id = %s
            """, (user_id,))
            usuario = cursor.fetchone()
            
            # Últimas 10 transacciones
            cursor.execute("""
                SELECT t.monto, t.tipo, t.fecha, t.descripcion,
                       tar.nombre as tarjetero
                FROM transacciones t
                LEFT JOIN tarjeteros tar ON t.id_tarjetero = tar.id
                WHERE t.id_usuario = %s
                ORDER BY t.fecha DESC
                LIMIT 10
            """, (user_id,))
            transacciones = cursor.fetchall()
            
            # Transferencias recientes
            cursor.execute("""
                SELECT tf.monto, tf.fecha, tf.descripcion,
                       u.nombre as destinatario
                FROM transferencias tf
                INNER JOIN usuarios u ON tf.id_destino = u.id
                WHERE tf.id_origen = %s
                ORDER BY tf.fecha DESC
                LIMIT 5
            """, (user_id,))
            transferencias_enviadas = cursor.fetchall()
            
            cursor.execute("""
                SELECT tf.monto, tf.fecha, tf.descripcion,
                       u.nombre as remitente
                FROM transferencias tf
                INNER JOIN usuarios u ON tf.id_origen = u.id
                WHERE tf.id_destino = %s
                ORDER BY tf.fecha DESC
                LIMIT 5
            """, (user_id,))
            transferencias_recibidas = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            # Construir contexto detallado
            contexto_usuario = f"""
DATOS DEL USUARIO:
- Nombre: {usuario['nombre']}
- CI: {usuario['ci']}
- Saldo actual: ${float(usuario['saldo']):.2f}

TRANSACCIONES RECIENTES:
"""
            
            if transacciones:
                for t in transacciones:
                    fecha = t['fecha'].strftime('%Y-%m-%d %H:%M') if t['fecha'] else 'N/A'
                    contexto_usuario += f"- {fecha}: {t['tipo'].upper()} ${float(t['monto']):.2f} - {t['descripcion'] or t['tarjetero'] or 'Sin descripción'}\n"
            else:
                contexto_usuario += "- No hay transacciones recientes\n"
            
            contexto_usuario += "\nTRANSFERENCIAS ENVIADAS:\n"
            if transferencias_enviadas:
                for tf in transferencias_enviadas:
                    fecha = tf['fecha'].strftime('%Y-%m-%d %H:%M') if tf['fecha'] else 'N/A'
                    contexto_usuario += f"- {fecha}: Enviado ${float(tf['monto']):.2f} a {tf['destinatario']} - {tf['descripcion'] or 'Sin descripción'}\n"
            else:
                contexto_usuario += "- No hay transferencias enviadas\n"
            
            contexto_usuario += "\nTRANSFERENCIAS RECIBIDAS:\n"
            if transferencias_recibidas:
                for tf in transferencias_recibidas:
                    fecha = tf['fecha'].strftime('%Y-%m-%d %H:%M') if tf['fecha'] else 'N/A'
                    contexto_usuario += f"- {fecha}: Recibido ${float(tf['monto']):.2f} de {tf['remitente']} - {tf['descripcion'] or 'Sin descripción'}\n"
            else:
                contexto_usuario += "- No hay transferencias recibidas\n"
            
            # Contexto del asistente
            sistema = """Eres un asistente financiero profesional y experto. Analiza los datos financieros del usuario y proporciona:

1. Análisis objetivo de patrones de gasto
2. Recomendaciones específicas basadas en sus transacciones reales
3. Consejos prácticos para optimizar finanzas personales
4. Identificación de oportunidades de ahorro
5. Estrategias de presupuesto personalizadas

Responde de forma profesional, directa y útil. Usa números y datos concretos cuando sea relevante. Si no hay suficiente información, indícalo claramente."""
            
            prompt_completo = f"{sistema}\n\n{contexto_usuario}\n\nPREGUNTA: {pregunta}\n\nRESPUESTA PROFESIONAL:"
            
            # Llamada streaming a Ollama
            ollama_response = requests.post(
                'http://localhost:11434/api/generate',
                json={
                    'model': 'gemma2',
                    'prompt': prompt_completo,
                    'stream': True
                },
                stream=True,
                timeout=60
            )
            
            if ollama_response.status_code == 200:
                for line in ollama_response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            if 'response' in chunk:
                                yield f"data: {json.dumps({'text': chunk['response']})}\n\n"
                            if chunk.get('done', False):
                                yield f"data: {json.dumps({'done': True})}\n\n"
                                break
                        except json.JSONDecodeError:
                            continue
            else:
                yield f"data: {json.dumps({'error': 'Error al conectar con el modelo IA'})}\n\n"
                
        except requests.exceptions.ConnectionError:
            yield f"data: {json.dumps({'error': 'No se pudo conectar con Ollama. Asegúrate de que está corriendo en el puerto 11434.'})}\n\n"
        except requests.exceptions.Timeout:
            yield f"data: {json.dumps({'error': 'El modelo tardó demasiado en responder.'})}\n\n"
        except Exception as e:
            print(f"Error en AI Chat: {str(e)}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)