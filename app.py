import os
import json
from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__)

# Configuración de la carpeta de datos JSON
DATA_FOLDER = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_FOLDER, exist_ok=True)

# --- FUNCIONES DE AYUDA PARA MANEJAR JSON ---
def leer_json(nombre_archivo):
    ruta = os.path.join(DATA_FOLDER, f"{nombre_archivo}.json")
    if not os.path.exists(ruta):
        # Si el archivo no existe, lo inicializamos como una lista vacía
        with open(ruta, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=4)
        return []
    
    try:
        with open(ruta, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def guardar_json(nombre_archivo, datos):
    ruta = os.path.join(DATA_FOLDER, f"{nombre_archivo}.json")
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=4)

# --- RUTAS DE LA APLICACIÓN WEB ---

@app.route('/')
def home():
    return render_template('home.html')

# Lista de páginas que manejan datos JSON de forma idéntica
ENTIDADES = ['catalogo', 'clientes', 'empleados', 'inventario', 'productos', 'proveedores', 'ventas']

@app.route('/<entidad>', methods=['GET', 'POST'])
def gestionar_entidad(entidad):
    if entidad not in ENTIDADES:
        return render_template('404.html'), 404
    
    if request.method == 'POST':
        # Recibir los datos enviados por el formulario o fetch (JSON)
        nuevos_datos = request.form.to_dict() if request.form else request.get_json()
        
        # Leer los datos actuales, agregar el nuevo registro y guardar
        datos_actuales = leer_json(entidad)
        datos_actuales.append(nuevos_datos)
        guardar_json(entidad, datos_actuales)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({"status": "success", "message": f"Datos guardados en {entidad}"})
            
    # Para peticiones GET, cargamos los datos existentes y renderizamos la vista
    datos = leer_json(entidad)
    return render_template(f'{entidad}.html', datos=datos)

# --- RUTAS REQUERIDAS PARA PWA ---

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json', mimetype='application/json')

@app.route('/sw.js')
def serve_sw():
    response = send_from_directory('static', 'sw.js', mimetype='application/javascript')
    # Regla estricta para Service Workers: no almacenar en caché el archivo sw.js del navegador
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

if __name__ == '__main__':
    # Ejecución en modo desarrollo
    app.run(debug=True, port=5000)