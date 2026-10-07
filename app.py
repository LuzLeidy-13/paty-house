from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
from datetime import datetime
from collections import Counter
from sqlalchemy import create_engine, text


app = Flask(__name__)
app.secret_key = 'paty_house_puno_2025_secret_key_cambiar'

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------- BASE DE DATOS ----------------
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///paty_house.db')

if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

if 'channel_binding' in DATABASE_URL:
    from urllib.parse import urlparse, parse_qs, urlunparse
    parsed = urlparse(DATABASE_URL)
    qs = parse_qs(parsed.query)
    qs.pop('channel_binding', None)
    new_query = '&'.join([f"{k}={v[0]}" for k, v in qs.items()])
    DATABASE_URL = urlunparse(parsed._replace(query=new_query))

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
IS_POSTGRES = DATABASE_URL.startswith('postgresql')


def query(sql, params=None, fetch=None):
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        if fetch == 'all':
            return [dict(row._mapping) for row in result]
        elif fetch == 'one':
            row = result.fetchone()
            return dict(row._mapping) if row else None
        else:
            conn.commit()
            return result


# ---------------- INICIALIZAR BD ----------------
def init_db():
    if IS_POSTGRES:
        query('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                nombre VARCHAR(100) NOT NULL,
                rol VARCHAR(20) NOT NULL
            )
        ''')
        query('''
            CREATE TABLE IF NOT EXISTS perros (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                edad VARCHAR(20) NOT NULL,
                tamano VARCHAR(20) NOT NULL,
                estado_salud VARCHAR(50) NOT NULL,
                esterilizado VARCHAR(10) NOT NULL,
                temperamento VARCHAR(50) NOT NULL,
                distrito VARCHAR(50) NOT NULL,
                latitud FLOAT,
                longitud FLOAT,
                descripcion TEXT,
                foto VARCHAR(200),
                fecha_registro VARCHAR(50) NOT NULL,
                estado VARCHAR(20) DEFAULT 'En espera',
                fecha_adopcion VARCHAR(20),
                institucion VARCHAR(50),
                creado_por VARCHAR(50)
            )
        ''')
        query('''
            CREATE TABLE IF NOT EXISTS solicitudes (
                id SERIAL PRIMARY KEY,
                perro_id INTEGER NOT NULL,
                nombre VARCHAR(150) NOT NULL,
                dni VARCHAR(20) NOT NULL,
                telefono VARCHAR(30),
                email VARCHAR(100),
                distrito VARCHAR(50),
                tiene_mascotas VARCHAR(10),
                vivienda VARCHAR(30),
                motivacion TEXT,
                acepta_seguimiento VARCHAR(10),
                fecha_solicitud VARCHAR(50),
                estado VARCHAR(20) DEFAULT 'Pendiente',
                respuesta TEXT,
                atendido_por VARCHAR(50)
            )
        ''')
        query('''
            CREATE TABLE IF NOT EXISTS historial (
                id SERIAL PRIMARY KEY,
                perro_id INTEGER NOT NULL,
                tipo VARCHAR(30) NOT NULL,
                descripcion TEXT NOT NULL,
                fecha VARCHAR(20) NOT NULL,
                veterinario VARCHAR(100),
                registrado_por VARCHAR(50)
            )
        ''')
    else:
        # SQLite local
        query('''CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            nombre TEXT NOT NULL, rol TEXT NOT NULL)''')
        query('''CREATE TABLE IF NOT EXISTS perros (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, edad TEXT NOT NULL,
            tamano TEXT NOT NULL, estado_salud TEXT NOT NULL, esterilizado TEXT NOT NULL,
            temperamento TEXT NOT NULL, distrito TEXT NOT NULL, latitud REAL, longitud REAL,
            descripcion TEXT, foto TEXT, fecha_registro TEXT NOT NULL,
            estado TEXT DEFAULT 'En espera', fecha_adopcion TEXT,
            institucion TEXT, creado_por TEXT)''')
        query('''CREATE TABLE IF NOT EXISTS solicitudes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, perro_id INTEGER NOT NULL,
            nombre TEXT NOT NULL, dni TEXT NOT NULL, telefono TEXT, email TEXT,
            distrito TEXT, tiene_mascotas TEXT, vivienda TEXT, motivacion TEXT,
            acepta_seguimiento TEXT, fecha_solicitud TEXT,
            estado TEXT DEFAULT 'Pendiente', respuesta TEXT, atendido_por TEXT)''')
        query('''CREATE TABLE IF NOT EXISTS historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT, perro_id INTEGER NOT NULL,
            tipo TEXT NOT NULL, descripcion TEXT NOT NULL, fecha TEXT NOT NULL,
            veterinario TEXT, registrado_por TEXT)''')

    # Crear usuarios por defecto si no existen
    usuarios_default = [
        ('admin', 'admin123', 'Equipo PATY HOUSE', 'admin'),
        ('municipalidad', 'muni123', 'Municipalidad Provincial de Puno', 'municipalidad'),
        ('albergue', 'albergue123', 'Asociación Patitas Felices', 'albergue'),
        ('veterinaria', 'vet123', 'Facultad de Veterinaria UNAP', 'veterinaria'),
    ]
    for username, pwd, nombre, rol in usuarios_default:
        existe = query('SELECT id FROM usuarios WHERE username=:u', {'u': username}, fetch='one')
        if not existe:
            query('INSERT INTO usuarios (username, password_hash, nombre, rol) VALUES (:u, :p, :n, :r)',
                  {'u': username, 'p': generate_password_hash(pwd), 'n': nombre, 'r': rol})

    print(f"✅ Base de datos inicializada ({'PostgreSQL' if IS_POSTGRES else 'SQLite'})")


init_db()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------- DECORADORES DE ROL ----------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Debes iniciar sesión', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


def rol_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                flash('Debes iniciar sesión', 'error')
                return redirect(url_for('login'))
            if session.get('rol') not in roles:
                flash('No tienes permiso para acceder a esta sección', 'error')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ---------------- AUTH ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = query('SELECT * FROM usuarios WHERE username=:u', {'u': username}, fetch='one')
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['nombre'] = user['nombre']
            session['rol'] = user['rol']
            flash(f'Bienvenido/a, {user["nombre"]}', 'success')
            return redirect(url_for('index'))
        flash('Usuario o contraseña incorrectos', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada', 'success')
    return redirect(url_for('login'))


# ---------------- RUTAS PÚBLICAS ----------------
@app.route('/')
def index():
    total = query('SELECT COUNT(*) AS c FROM perros', fetch='one')['c']
    adoptados = query("SELECT COUNT(*) AS c FROM perros WHERE estado='Adoptado'", fetch='one')['c']
    en_espera = total - adoptados
    distritos = query('SELECT DISTINCT distrito FROM perros', fetch='all')
    solicitudes_pend = 0
    if session.get('rol') in ('admin', 'albergue'):
        solicitudes_pend = query("SELECT COUNT(*) AS c FROM solicitudes WHERE estado='Pendiente'", fetch='one')['c']
    return render_template('index.html',
                           total=total, adoptados=adoptados,
                           en_espera=en_espera, distritos=len(distritos),
                           solicitudes_pend=solicitudes_pend)


@app.route('/perros')
def perros():
    filtro = request.args.get('estado', '')
    if filtro:
        rows = query('SELECT * FROM perros WHERE estado=:e ORDER BY id DESC', {'e': filtro}, fetch='all')
    else:
        rows = query('SELECT * FROM perros ORDER BY id DESC', fetch='all')
    return render_template('perros.html', perros=rows, filtro=filtro)


@app.route('/perro/<int:pid>')
def detalle(pid):
    perro = query('SELECT * FROM perros WHERE id=:id', {'id': pid}, fetch='one')
    if not perro:
        flash('Perro no encontrado', 'error')
        return redirect(url_for('perros'))
    historial = query('SELECT * FROM historial WHERE perro_id=:id ORDER BY id DESC', {'id': pid}, fetch='all')
    solicitudes = query('SELECT * FROM solicitudes WHERE perro_id=:id ORDER BY id DESC', {'id': pid}, fetch='all') \
        if session.get('rol') in ('admin', 'albergue') else []
    puede_editar = session.get('rol') == 'admin' or session.get('username') == perro.get('creado_por')
    return render_template('detalle.html', perro=perro, historial=historial,
                           solicitudes=solicitudes, puede_editar=puede_editar)


@app.route('/mapa')
def mapa():
    rows = query('SELECT * FROM perros WHERE latitud IS NOT NULL AND longitud IS NOT NULL', fetch='all')
    return render_template('mapa.html', perros=rows)


@app.route('/api/perros')
def api_perros():
    return jsonify(query('SELECT * FROM perros', fetch='all'))


@app.route('/priorizacion')
def priorizacion():
    todos = query('SELECT * FROM perros', fetch='all')
    adoptados = query("SELECT * FROM perros WHERE estado='Adoptado'", fetch='all')
    total = len(todos); total_adoptados = len(adoptados)
    dias_promedio = 0
    if adoptados:
        sumas = []
        for a in adoptados:
            try:
                f1 = datetime.strptime(a['fecha_registro'], '%Y-%m-%d %H:%M')
                f2 = datetime.strptime(a['fecha_adopcion'], '%Y-%m-%d')
                sumas.append((f2 - f1).days)
            except Exception:
                pass
        if sumas:
            dias_promedio = round(sum(sumas) / len(sumas), 1)
    prioridad = []
    for p in todos:
        if p['estado'] == 'Adoptado':
            continue
        score = 0
        if p['edad'] == 'Cachorro': score += 3
        elif p['edad'] == 'Joven': score += 2
        if p['tamano'] == 'Pequeño': score += 3
        elif p['tamano'] == 'Mediano': score += 2
        if p['estado_salud'] == 'Saludable': score += 2
        if p['temperamento'] == 'Juguetón': score += 2
        elif p['temperamento'] == 'Tranquilo': score += 1
        if p['foto']: score += 2
        prioridad.append({'perro': p, 'score': score})
    prioridad.sort(key=lambda x: x['score'], reverse=True)
    return render_template('priorizacion.html',
                           total=total, total_adoptados=total_adoptados,
                           dias_promedio=dias_promedio, prioridad=prioridad,
                           dist_edad=dict(Counter([p['edad'] for p in todos])),
                           dist_tamano=dict(Counter([p['tamano'] for p in todos])),
                           dist_distrito=dict(Counter([p['distrito'] for p in todos])))


# ---------------- REGISTRAR PERRO (solo logueados) ----------------
@app.route('/registrar', methods=['GET', 'POST'])
@login_required
def registrar():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip() or 'Sin nombre'
        foto_filename = None
        if 'foto' in request.files:
            file = request.files['foto']
            if file and file.filename and allowed_file(file.filename):
                foto_filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], foto_filename))

        lat = request.form.get('latitud') or None
        lng = request.form.get('longitud') or None

        query('''INSERT INTO perros (nombre, edad, tamano, estado_salud, esterilizado,
                    temperamento, distrito, latitud, longitud, descripcion, foto,
                    fecha_registro, estado, institucion, creado_por)
                VALUES (:nombre, :edad, :tamano, :salud, :est, :temp, :dist, :lat, :lng,
                        :desc, :foto, :fecha, 'En espera', :inst, :user)''',
              {'nombre': nombre, 'edad': request.form.get('edad'),
               'tamano': request.form.get('tamano'),
               'salud': request.form.get('estado_salud'),
               'est': request.form.get('esterilizado'),
               'temp': request.form.get('temperamento'),
               'dist': request.form.get('distrito'),
               'lat': float(lat) if lat else None,
               'lng': float(lng) if lng else None,
               'desc': request.form.get('descripcion', '').strip(),
               'foto': foto_filename,
               'fecha': datetime.now().strftime('%Y-%m-%d %H:%M'),
               'inst': session.get('rol'),
               'user': session.get('username')})
        flash('✅ Perro registrado correctamente', 'success')
        return redirect(url_for('perros'))
    return render_template('registrar.html')


@app.route('/adoptar/<int:pid>', methods=['POST'])
@rol_required('admin', 'albergue')
def adoptar(pid):
    query("UPDATE perros SET estado='Adoptado', fecha_adopcion=:f WHERE id=:id",
          {'f': datetime.now().strftime('%Y-%m-%d'), 'id': pid})
    flash('🎉 Adopción registrada', 'success')
    return redirect(url_for('detalle', pid=pid))


# ---------------- SOLICITUDES DE ADOPCIÓN ----------------
@app.route('/solicitar/<int:pid>', methods=['GET', 'POST'])
def solicitar(pid):
    perro = query('SELECT * FROM perros WHERE id=:id', {'id': pid}, fetch='one')
    if not perro:
        flash('Perro no encontrado', 'error')
        return redirect(url_for('perros'))
    if request.method == 'POST':
        query('''INSERT INTO solicitudes (perro_id, nombre, dni, telefono, email, distrito,
                    tiene_mascotas, vivienda, motivacion, acepta_seguimiento, fecha_solicitud, estado)
                VALUES (:pid, :n, :d, :t, :e, :dist, :tm, :v, :m, :seg, :f, 'Pendiente')''',
              {'pid': pid,
               'n': request.form.get('nombre'),
               'd': request.form.get('dni'),
               't': request.form.get('telefono'),
               'e': request.form.get('email'),
               'dist': request.form.get('distrito'),
               'tm': request.form.get('tiene_mascotas'),
               'v': request.form.get('vivienda'),
               'm': request.form.get('motivacion'),
               'seg': request.form.get('acepta_seguimiento'),
               'f': datetime.now().strftime('%Y-%m-%d %H:%M')})
        flash('✅ Solicitud enviada. Pronto te contactarán.', 'success')
        return redirect(url_for('detalle', pid=pid))
    return render_template('solicitar.html', perro=perro)


@app.route('/solicitudes')
@rol_required('admin', 'albergue')
def solicitudes():
    rows = query('''SELECT s.*, p.nombre AS perro_nombre, p.foto AS perro_foto
                    FROM solicitudes s JOIN perros p ON p.id = s.perro_id
                    ORDER BY s.id DESC''', fetch='all')
    return render_template('solicitudes.html', solicitudes=rows)


@app.route('/solicitud/<int:sid>/<accion>', methods=['POST'])
@rol_required('admin', 'albergue')
def resolver_solicitud(sid, accion):
    sol = query('SELECT * FROM solicitudes WHERE id=:id', {'id': sid}, fetch='one')
    if not sol:
        flash('Solicitud no encontrada', 'error')
        return redirect(url_for('solicitudes'))
    nuevo_estado = 'Aprobada' if accion == 'aprobar' else 'Rechazada'
    query('UPDATE solicitudes SET estado=:e, respuesta=:r, atendido_por=:u WHERE id=:id',
          {'e': nuevo_estado, 'r': request.form.get('respuesta', ''),
           'u': session.get('username'), 'id': sid})
    if accion == 'aprobar':
        query("UPDATE perros SET estado='Adoptado', fecha_adopcion=:f WHERE id=:id",
              {'f': datetime.now().strftime('%Y-%m-%d'), 'id': sol['perro_id']})
    flash(f'Solicitud {nuevo_estado.lower()}', 'success')
    return redirect(url_for('solicitudes'))


# ---------------- HISTORIAL CLÍNICO ----------------
@app.route('/perro/<int:pid>/historial', methods=['POST'])
@rol_required('admin', 'veterinaria')
def agregar_historial(pid):
    query('''INSERT INTO historial (perro_id, tipo, descripcion, fecha, veterinario, registrado_por)
              VALUES (:pid, :t, :d, :f, :v, :u)''',
          {'pid': pid, 't': request.form.get('tipo'),
           'd': request.form.get('descripcion'),
           'f': request.form.get('fecha') or datetime.now().strftime('%Y-%m-%d'),
           'v': request.form.get('veterinario', ''),
           'u': session.get('username')})
    flash('✅ Registro clínico añadido', 'success')
    return redirect(url_for('detalle', pid=pid))


# ---------------- PANEL ADMIN ----------------
@app.route('/admin')
@rol_required('admin')
def admin_panel():
    usuarios = query('SELECT id, username, nombre, rol FROM usuarios ORDER BY id', fetch='all')
    return render_template('admin.html', usuarios=usuarios)


@app.route('/admin/crear_usuario', methods=['POST'])
@rol_required('admin')
def crear_usuario():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    nombre = request.form.get('nombre', '')
    rol = request.form.get('rol', 'albergue')
    if query('SELECT id FROM usuarios WHERE username=:u', {'u': username}, fetch='one'):
        flash('Ese usuario ya existe', 'error')
    else:
        query('INSERT INTO usuarios (username, password_hash, nombre, rol) VALUES (:u, :p, :n, :r)',
              {'u': username, 'p': generate_password_hash(password), 'n': nombre, 'r': rol})
        flash(f'Usuario {username} creado', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/eliminar_usuario/<int:uid>', methods=['POST'])
@rol_required('admin')
def eliminar_usuario(uid):
    if uid == session.get('user_id'):
        flash('No puedes eliminarte a ti mismo', 'error')
    else:
        query('DELETE FROM usuarios WHERE id=:id', {'id': uid})
        flash('Usuario eliminado', 'success')
    return redirect(url_for('admin_panel'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)