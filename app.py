from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
import sqlite3
import os
from datetime import datetime
from collections import Counter

app = Flask(__name__)
app.secret_key = 'paty_house_puno_2025'

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB = 'paty_house.db'


# ---------- BASE DE DATOS ----------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''
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
    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# 🆕 INICIALIZAR BASE DE DATOS AL ARRANCAR LA APP
# Esto se ejecuta TANTO con `python app.py` COMO con `gunicorn app:app`
with app.app_context():
    init_db()


# ---------- RUTAS ----------
@app.route('/')
def index():
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) AS c FROM perros').fetchone()['c']
    adoptados = conn.execute("SELECT COUNT(*) AS c FROM perros WHERE estado='Adoptado'").fetchone()['c']
    en_espera = total - adoptados
    distritos = conn.execute('SELECT DISTINCT distrito FROM perros').fetchall()
    conn.close()

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

        conn = get_db()
        conn.execute('''
            INSERT INTO perros (nombre, edad, tamano, estado_salud, esterilizado,
                                temperamento, distrito, latitud, longitud, descripcion,
                                foto, fecha_registro, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'En espera')
        ''', (nombre, edad, tamano, estado_salud, esterilizado, temperamento,
              distrito, latitud, longitud, descripcion, foto_filename,
              datetime.now().strftime('%Y-%m-%d %H:%M')))
        conn.commit()
        conn.close()

        flash('✅ Perro registrado correctamente', 'success')
        return redirect(url_for('perros'))

    return render_template('registrar.html')


@app.route('/perros')
def perros():
    filtro = request.args.get('estado', '')
    conn = get_db()
    if filtro:
        rows = conn.execute('SELECT * FROM perros WHERE estado=? ORDER BY id DESC', (filtro,)).fetchall()
    else:
        rows = conn.execute('SELECT * FROM perros ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('perros.html', perros=rows, filtro=filtro)


@app.route('/perro/<int:pid>')
def detalle(pid):
    conn = get_db()
    perro = conn.execute('SELECT * FROM perros WHERE id=?', (pid,)).fetchone()
    conn.close()
    if not perro:
        flash('Perro no encontrado', 'error')
        return redirect(url_for('perros'))
    return render_template('detalle.html', perro=perro)


@app.route('/adoptar/<int:pid>', methods=['POST'])
def adoptar(pid):
    conn = get_db()
    conn.execute("UPDATE perros SET estado='Adoptado', fecha_adopcion=? WHERE id=?",
                 (datetime.now().strftime('%Y-%m-%d'), pid))
    conn.commit()
    conn.close()
    flash('🎉 ¡Adopción registrada con éxito!', 'success')
    return redirect(url_for('detalle', pid=pid))


@app.route('/mapa')
def mapa():
    conn = get_db()
    rows = conn.execute('SELECT * FROM perros WHERE latitud IS NOT NULL AND longitud IS NOT NULL').fetchall()
    conn.close()
    return render_template('mapa.html', perros=rows)


@app.route('/api/perros')
def api_perros():
    conn = get_db()
    rows = conn.execute('SELECT * FROM perros').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/priorizacion')
def priorizacion():
    conn = get_db()
    todos = conn.execute('SELECT * FROM perros').fetchall()
    adoptados = conn.execute("SELECT * FROM perros WHERE estado='Adoptado'").fetchall()
    conn.close()

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


# 🆕 Esta parte solo se ejecuta si corres `python app.py` localmente
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)