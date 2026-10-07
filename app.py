from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from collections import Counter

# 🆕 Importar SQLAlchemy para PostgreSQL
from sqlalchemy import create_engine, text

app = Flask(__name__)
app.secret_key = 'paty_house_puno_2025'

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 🆕 CONEXIÓN A LA BASE DE DATOS
# Lee DATABASE_URL desde las variables de entorno de Render.
# Si no existe (en tu PC), usa SQLite local como respaldo.
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///paty_house.db')

# Render a veces da URLs con "postgres://" pero SQLAlchemy necesita "postgresql://"
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# Quitamos channel_binding si está presente (psycopg2 no lo soporta bien)
if 'channel_binding' in DATABASE_URL:
    from urllib.parse import urlparse, parse_qs, urlunparse
    parsed = urlparse(DATABASE_URL)
    qs = parse_qs(parsed.query)
    qs.pop('channel_binding', None)
    new_query = '&'.join([f"{k}={v[0]}" for k, v in qs.items()])
    DATABASE_URL = urlunparse(parsed._replace(query=new_query))

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
IS_POSTGRES = DATABASE_URL.startswith('postgresql')


# 🆕 FUNCIÓN AUXILIAR — adapta las consultas según el motor
def query(sql, params=None, fetch=None):
    """
    Ejecuta una consulta SQL.
    - fetch='all'  → devuelve todas las filas
    - fetch='one'  → devuelve una fila
    - fetch=None   → solo ejecuta (INSERT/UPDATE/CREATE)
    """
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


# 🆕 INICIALIZAR BASE DE DATOS AL ARRANCAR
def init_db():
    """Crea la tabla perros si no existe. Funciona en SQLite y PostgreSQL."""
    if IS_POSTGRES:
        # PostgreSQL usa SERIAL en lugar de AUTOINCREMENT
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
                fecha_adopcion VARCHAR(20)
            )
        ''')
    else:
        # SQLite (para desarrollo local)
        query('''
            CREATE TABLE IF NOT EXISTS perros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                edad TEXT NOT NULL,
                tamano TEXT NOT NULL,
                estado_salud TEXT NOT NULL,
                esterilizado TEXT NOT NULL,
                temperamento TEXT NOT NULL,
                distrito TEXT NOT NULL,
                latitud REAL,
                longitud REAL,
                descripcion TEXT,
                foto TEXT,
                fecha_registro TEXT NOT NULL,
                estado TEXT DEFAULT 'En espera',
                fecha_adopcion TEXT
            )
        ''')
    print(f"✅ Base de datos inicializada ({'PostgreSQL' if IS_POSTGRES else 'SQLite'})")


# Ejecutar la inicialización al arrancar la app (funciona con gunicorn)
init_db()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------- RUTAS ----------
@app.route('/')
def index():
    total = query('SELECT COUNT(*) AS c FROM perros', fetch='one')['c']
    adoptados = query("SELECT COUNT(*) AS c FROM perros WHERE estado='Adoptado'", fetch='one')['c']
    en_espera = total - adoptados
    distritos = query('SELECT DISTINCT distrito FROM perros', fetch='all')

    return render_template('index.html',
                           total=total,
                           adoptados=adoptados,
                           en_espera=en_espera,
                           distritos=len(distritos))


@app.route('/registrar', methods=['GET', 'POST'])
def registrar():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip() or 'Sin nombre'
        edad = request.form.get('edad')
        tamano = request.form.get('tamano')
        estado_salud = request.form.get('estado_salud')
        esterilizado = request.form.get('esterilizado')
        temperamento = request.form.get('temperamento')
        distrito = request.form.get('distrito')
        latitud = request.form.get('latitud') or None
        longitud = request.form.get('longitud') or None
        descripcion = request.form.get('descripcion', '').strip()

        foto_filename = None
        if 'foto' in request.files:
            file = request.files['foto']
            if file and file.filename and allowed_file(file.filename):
                foto_filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], foto_filename))

        query('''
            INSERT INTO perros (nombre, edad, tamano, estado_salud, esterilizado,
                                temperamento, distrito, latitud, longitud, descripcion,
                                foto, fecha_registro, estado)
            VALUES (:nombre, :edad, :tamano, :estado_salud, :esterilizado,
                    :temperamento, :distrito, :latitud, :longitud, :descripcion,
                    :foto, :fecha_registro, 'En espera')
        ''', {
            'nombre': nombre, 'edad': edad, 'tamano': tamano,
            'estado_salud': estado_salud, 'esterilizado': esterilizado,
            'temperamento': temperamento, 'distrito': distrito,
            'latitud': float(latitud) if latitud else None,
            'longitud': float(longitud) if longitud else None,
            'descripcion': descripcion, 'foto': foto_filename,
            'fecha_registro': datetime.now().strftime('%Y-%m-%d %H:%M')
        })

        flash('✅ Perro registrado correctamente', 'success')
        return redirect(url_for('perros'))

    return render_template('registrar.html')


@app.route('/perros')
def perros():
    filtro = request.args.get('estado', '')
    if filtro:
        rows = query('SELECT * FROM perros WHERE estado=:estado ORDER BY id DESC',
                     {'estado': filtro}, fetch='all')
    else:
        rows = query('SELECT * FROM perros ORDER BY id DESC', fetch='all')
    return render_template('perros.html', perros=rows, filtro=filtro)


@app.route('/perro/<int:pid>')
def detalle(pid):
    perro = query('SELECT * FROM perros WHERE id=:id', {'id': pid}, fetch='one')
    if not perro:
        flash('Perro no encontrado', 'error')
        return redirect(url_for('perros'))
    return render_template('detalle.html', perro=perro)


@app.route('/adoptar/<int:pid>', methods=['POST'])
def adoptar(pid):
    query("UPDATE perros SET estado='Adoptado', fecha_adopcion=:fecha WHERE id=:id",
          {'fecha': datetime.now().strftime('%Y-%m-%d'), 'id': pid})
    flash('🎉 ¡Adopción registrada con éxito!', 'success')
    return redirect(url_for('detalle', pid=pid))


@app.route('/mapa')
def mapa():
    rows = query('SELECT * FROM perros WHERE latitud IS NOT NULL AND longitud IS NOT NULL', fetch='all')
    return render_template('mapa.html', perros=rows)


@app.route('/api/perros')
def api_perros():
    rows = query('SELECT * FROM perros', fetch='all')
    return jsonify(rows)


@app.route('/priorizacion')
def priorizacion():
    todos = query('SELECT * FROM perros', fetch='all')
    adoptados = query("SELECT * FROM perros WHERE estado='Adoptado'", fetch='all')

    total = len(todos)
    total_adoptados = len(adoptados)

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
        if p['edad'] == 'Cachorro':
            score += 3
        elif p['edad'] == 'Joven':
            score += 2
        if p['tamano'] == 'Pequeño':
            score += 3
        elif p['tamano'] == 'Mediano':
            score += 2
        if p['estado_salud'] == 'Saludable':
            score += 2
        if p['temperamento'] == 'Juguetón':
            score += 2
        elif p['temperamento'] == 'Tranquilo':
            score += 1
        if p['foto']:
            score += 2
        prioridad.append({'perro': p, 'score': score})

    prioridad.sort(key=lambda x: x['score'], reverse=True)

    dist_edad = Counter([p['edad'] for p in todos])
    dist_tamano = Counter([p['tamano'] for p in todos])
    dist_distrito = Counter([p['distrito'] for p in todos])

    return render_template('priorizacion.html',
                           total=total,
                           total_adoptados=total_adoptados,
                           dias_promedio=dias_promedio,
                           prioridad=prioridad,
                           dist_edad=dict(dist_edad),
                           dist_tamano=dict(dist_tamano),
                           dist_distrito=dict(dist_distrito))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)