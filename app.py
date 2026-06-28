import os
import json
import datetime
import secrets
import requests
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'clave_super_secreta_marcani_2024'

# --- CONFIGURACIÓN ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# Configuración de subida de imágenes
if os.environ.get('RENDER'):
    UPLOAD_FOLDER = '/tmp/uploads_marcani'
else:
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=30)

# --- CONFIGURACIÓN DE GITHUB ---
# PUEDES DEJAR ESTO ASÍ. LA PRIMERA VEZ QUE GUARDES, SE CREARÁ SOLO.
GITHUB_TOKEN = None
GIST_ID = None
GIST_FILENAME = 'marcani_db.json'

# --- FUNCIONES DE SINCRO DE DATOS ---
def sync_from_github():
    """Descarga los datos desde GitHub Gist y los guarda en la carpeta data/ local."""
    global GIST_ID, GITHUB_TOKEN
    
    if not GITHUB_TOKEN or not GIST_ID:
        return False
        
    try:
        url = f"https://api.github.com/gists/{GIST_ID}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            gist_data = response.json()
            files = gist_data.get('files', {})
            if GIST_FILENAME in files:
                raw_url = files[GIST_FILENAME]['raw_url']
                raw_response = requests.get(raw_url)
                if raw_response.status_code == 200:
                    contenido = raw_response.json()
                    # Sobrescribimos los archivos locales con los de la nube
                    for tabla, datos in contenido.items():
                        filepath = os.path.join(DATA_DIR, f"{tabla}.json")
                        with open(filepath, 'w', encoding='utf-8') as f:
                            json.dump(datos, f, indent=4, ensure_ascii=False)
                    return True
    except:
        pass
    return False

def sync_to_github():
    """Sube todos los datos locales a la Gist de GitHub."""
    global GIST_ID, GITHUB_TOKEN
    
    # 1. Buscar si existe un token guardado
    token_path = os.path.join(DATA_DIR, 'github_config.json')
    if os.path.exists(token_path):
        try:
            with open(token_path, 'r') as f:
                config = json.load(f)
                GITHUB_TOKEN = config.get('token')
                GIST_ID = config.get('gist_id')
        except:
            pass

    # Si no hay token, no podemos guardar en GitHub
    if not GITHUB_TOKEN:
        return False

    # 2. Crear el payload con todos los datos
    all_data = {}
    json_files = ['clientes', 'productos', 'empleados', 'proveedores', 'inventario', 'ventas', 'usuarios']
    for tabla in json_files:
        filepath = os.path.join(DATA_DIR, f"{tabla}.json")
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                all_data[tabla] = json.load(f)
        except:
            all_data[tabla] = []

    # 3. Subir a GitHub
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        payload = {
            "files": {
                GIST_FILENAME: {
                    "content": json.dumps(all_data, indent=4)
                }
            }
        }
        
        if GIST_ID:
            # Actualizar Gist existente
            url = f"https://api.github.com/gists/{GIST_ID}"
            requests.patch(url, headers=headers, json=payload)
        else:
            # Crear Gist nuevo
            payload["public"] = False
            url = "https://api.github.com/gists"
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 201:
                gist_data = response.json()
                GIST_ID = gist_data['id']
                # Guardamos el token y el ID localmente
                with open(token_path, 'w') as f:
                    json.dump({'token': GITHUB_TOKEN, 'gist_id': GIST_ID}, f)
        return True
    except:
        return False

# --- FUNCIONES DE BASE DE DATOS (Con respaldo en GitHub) ---
def load_data(filename):
    # Ruta local
    local_path = os.path.join(DATA_DIR, filename)
    
    # Si el archivo no existe localmente, intentamos descargar de GitHub
    if not os.path.exists(local_path):
        if sync_from_github():
            pass # Si se descargó, ya existe
    
    # Cargar local
    if not os.path.exists(local_path):
        return []
    try:
        with open(local_path, 'r', encoding='utf-8') as f:
            contenido = f.read().strip()
            if not contenido: return []
            return json.loads(contenido)
    except:
        return []

def save_data(filename, data):
    # Guardar localmente primero
    local_path = os.path.join(DATA_DIR, filename)
    try:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except:
        pass
    
    # Subir todo a GitHub como respaldo en la nube
    sync_to_github()
    return True

# --- DECORADOR DE SEGURIDAD ---
def login_required(f):
    def wrap(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# --- RUTAS DE AUTENTICACIÓN ---
@app.route('/registro', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not nombre or not email or not password:
            return render_template('auth/register.html', error="Todos los campos son obligatorios.")
        
        if password != confirm_password:
            return render_template('auth/register.html', error="Las contraseñas no coinciden.")

        usuarios = load_data('usuarios.json')
        for u in usuarios:
            if u['email'] == email:
                return render_template('auth/register.html', error="El correo ya está registrado.")

        nuevo_usuario = {
            'id_usuario': len(usuarios) + 1,
            'nombre': nombre,
            'username': username if username else nombre.split()[0],
            'email': email,
            'password_hash': generate_password_hash(password)
        }
        usuarios.append(nuevo_usuario)
        save_data('usuarios.json', usuarios)
        return redirect(url_for('login'))
    return render_template('auth/register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        remember_me = request.form.get('remember_me')

        if not email or not password:
            return render_template('auth/login.html', error="Por favor, completa todos los campos.")
        
        usuarios = load_data('usuarios.json')
        user = None
        for u in usuarios:
            if u['email'] == email:
                user = u
                break

        if not user or not check_password_hash(user['password_hash'], password):
            return render_template('auth/login.html', error="Correo o contraseña incorrectos.")

        session['user_id'] = user['id_usuario']
        session['user_name'] = user['nombre']
        
        if remember_me:
            session.permanent = True
            
        return redirect(url_for('home'))
    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- RUTAS DEL SISTEMA ---
@app.route('/')
@login_required
def home():
    clientes = load_data('clientes.json')
    ventas = load_data('ventas.json')
    total_clientes = len(clientes)
    total_ventas_general = sum(v.get('total', 0) for v in ventas)
    hoy = datetime.date.today().isoformat()
    ganancias_hoy = sum(v.get('total', 0) for v in ventas if v.get('fecha') == hoy)
    return render_template('home.html', total_clientes=total_clientes, total_ventas=total_ventas_general, ganancias_hoy=ganancias_hoy)

@app.route('/clientes', methods=['GET', 'POST'])
@login_required
def clientes_view():
    clientes = load_data('clientes.json')
    if request.method == 'POST':
        accion = request.form.get('accion')
        if accion == 'eliminar':
            try:
                cliente_id = int(request.form.get('cliente_id'))
                clientes = [c for c in clientes if c['id_cliente'] != cliente_id]
                save_data('clientes.json', clientes)
                return redirect(url_for('clientes_view'))
            except Exception:
                return render_template('clientes.html', clientes=clientes, error="Error al eliminar")
        nombre = request.form.get('nombre', '').strip()
        if not nombre:
            return render_template('clientes.html', clientes=clientes, error="El nombre es obligatorio")
        nuevo_cliente = {'id_cliente': len(clientes) + 1, 'nombre': nombre, 'telefono': request.form.get('telefono', ''), 'email': request.form.get('email', '')}
        clientes.append(nuevo_cliente)
        save_data('clientes.json', clientes)
        return redirect(url_for('clientes_view'))
    return render_template('clientes.html', clientes=clientes, error=None)

@app.route('/productos', methods=['GET', 'POST'])
@login_required
def productos_view():
    productos = load_data('productos.json')
    inventario = load_data('inventario.json')
    if request.method == 'POST':
        accion = request.form.get('accion')
        if accion == 'eliminar':
            try:
                producto_id = int(request.form.get('producto_id'))
                productos = [p for p in productos if p['id_producto'] != producto_id]
                save_data('productos.json', productos)
                inventario = [i for i in inventario if i['id_inventario'] != producto_id]
                save_data('inventario.json', inventario)
                return redirect(url_for('productos_view'))
            except Exception:
                return render_template('productos.html', productos=productos, inventario=inventario, error="Error al eliminar")
        nombre_producto = request.form.get('nombre_producto', '').strip()
        precio_str = request.form.get('precio', '0')
        stock_str = request.form.get('stock', '0')
        if not nombre_producto:
            return render_template('productos.html', productos=productos, inventario=inventario, error="El nombre es obligatorio")
        try:
            precio = float(precio_str)
            stock = int(stock_str)
            if precio <= 0 or stock < 0: raise ValueError
        except ValueError:
            return render_template('productos.html', productos=productos, inventario=inventario, error="Precio y Stock inválidos")
        imagen_url = ""
        if 'imagen_file' in request.files:
            file = request.files['imagen_file']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_name = secrets.token_hex(8) + "_" + filename
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
                imagen_url = url_for('static', filename='uploads/' + unique_name)
        if not imagen_url:
            imagen_url = request.form.get('imagen_url', '').strip()
        if accion == 'editar':
            try:
                producto_id = int(request.form.get('producto_id'))
                for p in productos:
                    if p['id_producto'] == producto_id:
                        p['nombre_producto'] = nombre_producto
                        p['precio'] = precio
                        if imagen_url: p['imagen'] = imagen_url
                        break
                inventario_data = load_data('inventario.json')
                for item in inventario_data:
                    if item['id_inventario'] == producto_id:
                        item['cantidad'] = stock
                        break
                save_data('productos.json', productos)
                save_data('inventario.json', inventario_data)
                return redirect(url_for('productos_view'))
            except Exception as e:
                return render_template('productos.html', productos=productos, inventario=inventario, error=f"Error al editar: {e}")
        else:
            data = load_data('productos.json')
            new_id = len(data) + 1
            nuevo_producto = {
                'id_producto': new_id,
                'nombre_producto': nombre_producto,
                'precio': precio,
                'imagen': imagen_url
            }
            data.append(nuevo_producto)
            save_data('productos.json', data)
            inv_data = load_data('inventario.json')
            nuevo_stock = {
                'id_inventario': new_id,
                'material': f"Stock de {nombre_producto}",
                'cantidad': stock,
                'proveedor': 'Stock Inicial'
            }
            inv_data.append(nuevo_stock)
            save_data('inventario.json', inv_data)
            return redirect(url_for('productos_view'))
    return render_template('productos.html', productos=productos, inventario=inventario, error=None)

@app.route('/empleados', methods=['GET', 'POST'])
@login_required
def empleados_view():
    empleados = load_data('empleados.json')
    if request.method == 'POST':
        accion = request.form.get('accion')
        if accion == 'eliminar':
            try:
                empleado_id = int(request.form.get('empleado_id'))
                empleados = [e for e in empleados if e['id_empleado'] != empleado_id]
                save_data('empleados.json', empleados)
                return redirect(url_for('empleados_view'))
            except Exception:
                return render_template('empleados.html', empleados=empleados, error="Error al eliminar")
        nombre = request.form.get('nombre', '').strip()
        if not nombre:
            return render_template('empleados.html', empleados=empleados, error="El nombre es obligatorio")
        nuevo_empleado = {'id_empleado': len(empleados) + 1, 'nombre': nombre, 'cargo': request.form.get('cargo', ''), 'telefono': request.form.get('telefono', '')}
        empleados.append(nuevo_empleado)
        save_data('empleados.json', empleados)
        return redirect(url_for('empleados_view'))
    return render_template('empleados.html', empleados=empleados, error=None)

@app.route('/proveedores', methods=['GET', 'POST'])
@login_required
def proveedores_view():
    proveedores = load_data('proveedores.json')
    if request.method == 'POST':
        accion = request.form.get('accion')
        if accion == 'eliminar':
            try:
                proveedor_id = int(request.form.get('proveedor_id'))
                proveedores = [p for p in proveedores if p['id_proveedor'] != proveedor_id]
                save_data('proveedores.json', proveedores)
                return redirect(url_for('proveedores_view'))
            except Exception:
                return render_template('proveedores.html', proveedores=proveedores, error="Error al eliminar")
        nombre_empresa = request.form.get('nombre_empresa', '').strip()
        que_provee = request.form.get('que_provee', '').strip()
        if not nombre_empresa:
            return render_template('proveedores.html', proveedores=proveedores, error="El nombre es obligatorio")
        if accion == 'editar':
            try:
                proveedor_id = int(request.form.get('proveedor_id'))
                for p in proveedores:
                    if p['id_proveedor'] == proveedor_id:
                        p['nombre_empresa'] = nombre_empresa
                        p['que_provee'] = que_provee
                        p['telefono'] = request.form.get('telefono', '').strip()
                        p['email'] = request.form.get('email', '').strip()
                        break
                save_data('proveedores.json', proveedores)
                return redirect(url_for('proveedores_view'))
            except Exception as e:
                return render_template('proveedores.html', proveedores=proveedores, error=f"Error al editar: {e}")
        else:
            nuevo_proveedor = {
                'id_proveedor': len(proveedores) + 1, 
                'nombre_empresa': nombre_empresa, 
                'que_provee': que_provee,
                'telefono': request.form.get('telefono', '').strip(), 
                'email': request.form.get('email', '').strip()
            }
            proveedores.append(nuevo_proveedor)
            save_data('proveedores.json', proveedores)
            return redirect(url_for('proveedores_view'))
    return render_template('proveedores.html', proveedores=proveedores, error=None)

@app.route('/inventario', methods=['GET', 'POST'])
@login_required
def inventario_view():
    inventario = load_data('inventario.json')
    proveedores = load_data('proveedores.json')
    if request.method == 'POST':
        accion = request.form.get('accion')
        if accion == 'eliminar':
            try:
                inventario_id = int(request.form.get('inventario_id'))
                inventario = [i for i in inventario if i['id_inventario'] != inventario_id]
                save_data('inventario.json', inventario)
                return redirect(url_for('inventario_view'))
            except Exception:
                return render_template('inventario.html', inventario=inventario, proveedores=proveedores, error="Error al eliminar")
        if accion == 'editar':
            try:
                inventario_id = int(request.form.get('inventario_id'))
                nueva_cantidad = int(request.form.get('cantidad', '0'))
                nueva_unidad = request.form.get('unidad_medida', '').strip()
                nuevo_material = request.form.get('material', '').strip()
                if nueva_cantidad < 0: raise ValueError
                for item in inventario:
                    if item['id_inventario'] == inventario_id:
                        item['material'] = nuevo_material if nuevo_material else item['material']
                        item['cantidad'] = nueva_cantidad
                        item['unidad_medida'] = nueva_unidad if nueva_unidad else item.get('unidad_medida', '')
                        break
                save_data('inventario.json', inventario)
                return redirect(url_for('inventario_view'))
            except ValueError:
                return render_template('inventario.html', inventario=inventario, proveedores=proveedores, error="Cantidad inválida")
        material = request.form.get('material', '').strip()
        cantidad = request.form.get('cantidad', '0')
        proveedor = request.form.get('proveedor', '').strip()
        unidad_medida = request.form.get('unidad_medida', '').strip()
        if not material or not proveedor or not unidad_medida:
            return render_template('inventario.html', inventario=inventario, proveedores=proveedores, error="Material, Proveedor y Unidad son obligatorios")
        try:
            cantidad = int(cantidad)
            if cantidad < 0: raise ValueError
        except ValueError:
            return render_template('inventario.html', inventario=inventario, proveedores=proveedores, error="Cantidad inválida")
        nuevo_item = {'id_inventario': len(inventario) + 1, 'material': material, 'cantidad': cantidad, 'unidad_medida': unidad_medida, 'proveedor': proveedor}
        inventario.append(nuevo_item)
        save_data('inventario.json', inventario)
        return redirect(url_for('inventario_view'))
    return render_template('inventario.html', inventario=inventario, proveedores=proveedores, error=None)

@app.route('/catalogo')
@login_required
def catalogo_view():
    productos = load_data('productos.json')
    inventario = load_data('inventario.json')
    return render_template('catalogo.html', productos=productos, inventario=inventario)

@app.route('/ventas', methods=['GET', 'POST'])
@login_required
def ventas_view():
    productos = load_data('productos.json')
    inventario = load_data('inventario.json')
    clientes = load_data('clientes.json')
    ventas = load_data('ventas.json')
    if request.method == 'POST':
        try:
            id_cliente = int(request.form.get('id_cliente', 0))
            id_producto = int(request.form.get('id_producto', 0))
            cantidad_vender = int(request.form.get('cantidad', 0))
            if id_cliente <= 0 or id_producto <= 0 or cantidad_vender <= 0:
                return render_template('ventas.html', productos=productos, inventario=inventario, clientes=clientes, ventas=ventas, error="Datos inválidos")
            precio_unitario = 0
            for p in productos:
                if p['id_producto'] == id_producto:
                    precio_unitario = p['precio']
                    break
            if precio_unitario == 0:
                return render_template('ventas.html', productos=productos, inventario=inventario, clientes=clientes, ventas=ventas, error="Producto no encontrado")
            inventario_data = load_data('inventario.json')
            stock_suficiente = False
            for item in inventario_data:
                if item['id_inventario'] == id_producto:
                    if item['cantidad'] >= cantidad_vender:
                        item['cantidad'] -= cantidad_vender
                        stock_suficiente = True
                    break
            if not stock_suficiente:
                return render_template('ventas.html', productos=productos, inventario=inventario, clientes=clientes, ventas=ventas, error="Stock insuficiente")
            save_data('inventario.json', inventario_data)
            total = precio_unitario * cantidad_vender
            ventas_data = load_data('ventas.json')
            nueva_venta = {
                'id_venta': len(ventas_data) + 1,
                'id_cliente': id_cliente,
                'id_producto': id_producto,
                'fecha': datetime.date.today().isoformat(),
                'cantidad': cantidad_vender,
                'total': total
            }
            ventas_data.append(nueva_venta)
            save_data('ventas.json', ventas_data)
            return redirect(url_for('ventas_view'))
        except ValueError:
            return render_template('ventas.html', productos=productos, inventario=inventario, clientes=clientes, ventas=ventas, error="Error en formato de números")
    return render_template('ventas.html', productos=productos, inventario=inventario, clientes=clientes, ventas=ventas, error=None)

@app.errorhandler(404)
def page_not_found(e): return redirect(url_for('login'))

@app.route('/manifest.json')
def serve_manifest(): return app.send_static_file('manifest.json')
@app.route('/sw.js')
def serve_sw(): return app.send_static_file('sw.js')

# --- RUTA DE SEMBRADO ---
@app.route('/seed_database')
@login_required
def seed_database():
    if not load_data('clientes.json'):
        save_data('clientes.json', [
            {'id_cliente': 1, 'nombre': 'Ana María Gutiérrez', 'telefono': '71234567', 'email': 'ana@email.com'},
            {'id_cliente': 2, 'nombre': 'Carlos López', 'telefono': '72345678', 'email': 'carlos@email.com'},
            {'id_cliente': 3, 'nombre': 'María Fernanda Rojas', 'telefono': '73456789', 'email': 'maria@email.com'},
            {'id_cliente': 4, 'nombre': 'José Luis Martínez', 'telefono': '74567890', 'email': 'jose@email.com'},
            {'id_cliente': 5, 'nombre': 'Lucía Torres', 'telefono': '75678901', 'email': 'lucia@email.com'}
        ])
    if not load_data('empleados.json'):
        save_data('empleados.json', [
            {'id_empleado': 1, 'nombre': 'Pedro Rodríguez', 'cargo': 'Vendedor Senior', 'telefono': '70123456'},
            {'id_empleado': 2, 'nombre': 'Laura Fernández', 'cargo': 'Cortadora de Cuero', 'telefono': '70234567'},
            {'id_empleado': 3, 'nombre': 'Miguel Ángel Cruz', 'cargo': 'Encargado de Inventario', 'telefono': '70345678'},
            {'id_empleado': 4, 'nombre': 'Sofía Herrera', 'cargo': 'Vendedora', 'telefono': '70456789'}
        ])
    if not load_data('proveedores.json'):
        save_data('proveedores.json', [
            {'id_proveedor': 1, 'nombre_empresa': 'Cueros Premium S.A.', 'que_provee': 'Cueros vacunos y ovinos', 'telefono': '77123456', 'email': 'ventas@cuerospremium.com'},
            {'id_proveedor': 2, 'nombre_empresa': 'Herrajes La Tijera', 'que_provee': 'Hebillas, broches y tachuelas', 'telefono': '77234567', 'email': 'info@herrajes.com'},
            {'id_proveedor': 3, 'nombre_empresa': 'Hilos y Textiles Bolivia', 'que_provee': 'Hilos encerados y nylon', 'telefono': '77345678', 'email': 'contacto@hilostextiles.bo'},
            {'id_proveedor': 4, 'nombre_empresa': 'Maquilas y Bordados', 'que_provee': 'Parches y grabados láser', 'telefono': '77456789', 'email': 'maquilas@bordados.com'}
        ])
    return redirect(url_for('home'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)