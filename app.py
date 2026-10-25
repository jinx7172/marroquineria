import os
import json
import datetime
import secrets
import requests
import re
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'clave_super_secreta_marcani_2024')

# --- CONFIGURACIÓN ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

if os.environ.get('RENDER'):
    UPLOAD_FOLDER = '/tmp/uploads_marcani'
else:
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=30)

# --- CONFIGURACIÓN DE GITHUB ---
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', None)
GIST_ID = None
GIST_FILENAME = 'marcani_db.json'

# --- CREDENCIALES POR DEFECTO DEL ADMIN ---
ADMIN_USERNAME_DEFAULT = 'admin'
ADMIN_PASSWORD_DEFAULT = 'Carlos_71724444'

# --- FUNCIONES DE VALIDACIÓN ---
def validar_nombre(nombre):
    return bool(re.fullmatch(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑ\s]+$", nombre))

def validar_telefono(telefono):
    if not telefono: return True
    return bool(re.fullmatch(r"^[\d\s\+\-]+$", telefono))

def validar_email(email):
    if not email: return True
    return email.endswith('@gmail.com')

# --- FUNCIONES DE SINCRO DE DATOS ---
def sync_from_github():
    global GIST_ID, GITHUB_TOKEN
    if not GITHUB_TOKEN:
        return False
    token_path = os.path.join(DATA_DIR, 'github_config.json')
    if os.path.exists(token_path):
        try:
            with open(token_path, 'r') as f:
                config = json.load(f)
                GIST_ID = config.get('gist_id')
        except:
            pass
    if not GIST_ID:
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
                    for tabla, datos in contenido.items():
                        filepath = os.path.join(DATA_DIR, f"{tabla}.json")
                        with open(filepath, 'w', encoding='utf-8') as f:
                            json.dump(datos, f, indent=4, ensure_ascii=False)
                    return True
    except:
        pass
    return False

def sync_to_github():
    global GIST_ID, GITHUB_TOKEN
    if not GITHUB_TOKEN:
        return False
    token_path = os.path.join(DATA_DIR, 'github_config.json')
    if os.path.exists(token_path):
        try:
            with open(token_path, 'r') as f:
                config = json.load(f)
                GITHUB_TOKEN = config.get('token')
                GIST_ID = config.get('gist_id')
        except:
            pass
    if not GITHUB_TOKEN:
        return False
    all_data = {}
    json_files = ['clientes', 'productos', 'empleados', 'proveedores', 'inventario', 'ventas', 'usuarios', 'registro_actividad']
    for tabla in json_files:
        filepath = os.path.join(DATA_DIR, f"{tabla}.json")
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                all_data[tabla] = json.load(f)
        except:
            all_data[tabla] = []
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        payload = {"files": {GIST_FILENAME: {"content": json.dumps(all_data, indent=4)}}}
        if GIST_ID:
            url = f"https://api.github.com/gists/{GIST_ID}"
            requests.patch(url, headers=headers, json=payload)
        else:
            payload["public"] = False
            url = "https://api.github.com/gists"
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 201:
                gist_data = response.json()
                GIST_ID = gist_data['id']
                with open(token_path, 'w') as f:
                    json.dump({'token': GITHUB_TOKEN, 'gist_id': GIST_ID}, f)
        return True
    except:
        return False

# --- FUNCIONES DE BASE DE DATOS ---
def load_data(filename):
    local_path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(local_path):
        sync_from_github()
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
    local_path = os.path.join(DATA_DIR, filename)
    try:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except:
        pass
    sync_to_github()
    return True

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    def wrap(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

def registrar_actividad(accion, detalles):
    logs = load_data('registro_actividad.json')
    nuevo_log = {
        'id': len(logs) + 1,
        'fecha': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'usuario': session.get('user_name', 'Admin'),
        'accion': accion,
        'detalles': detalles
    }
    logs.insert(0, nuevo_log)
    save_data('registro_actividad.json', logs)

# --- ASEGURAR ADMIN ÚNICO ---
def ensure_admin_exists():
    usuarios = load_data('usuarios.json')
    if not usuarios:
        admin = {
            'id_usuario': 1,
            'nombre': 'Administrador',
            'username': ADMIN_USERNAME_DEFAULT,
            'email': 'admin@marcani.local',
            'password_hash': generate_password_hash(ADMIN_PASSWORD_DEFAULT)
        }
        save_data('usuarios.json', [admin])

ensure_admin_exists()

# --- RUTAS DE AUTENTICACIÓN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember_me = request.form.get('remember_me')

        if not username or not password:
            return render_template('auth/login.html', error="Por favor, completa todos los campos.")

        usuarios = load_data('usuarios.json')
        user = next((u for u in usuarios if u['username'] == username), None)

        if not user or not check_password_hash(user['password_hash'], password):
            return render_template('auth/login.html', error="Usuario o contraseña incorrectos.")

        session['user_id'] = user['id_usuario']
        session['user_name'] = user['nombre']
        if remember_me: session.permanent = True
        return redirect(url_for('home'))
    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/configuracion', methods=['GET', 'POST'])
@login_required
def configuracion_view():
    usuarios = load_data('usuarios.json')
    if not usuarios:
        ensure_admin_exists()
        usuarios = load_data('usuarios.json')
    admin = usuarios[0]

    if request.method == 'POST':
        accion = request.form.get('accion')
        if accion == 'cambiar_usuario':
            nuevo_nombre = request.form.get('nombre', '').strip()
            nuevo_username = request.form.get('username', '').strip()
            nuevo_email = request.form.get('email', '').strip()
            if not nuevo_nombre or not validar_nombre(nuevo_nombre) or not nuevo_username or (nuevo_email and not validar_email(nuevo_email)):
                return render_template('configuracion.html', admin=admin, error="Datos inválidos.")
            admin['nombre'], admin['username'] = nuevo_nombre, nuevo_username
            if nuevo_email: admin['email'] = nuevo_email
            usuarios[0] = admin
            save_data('usuarios.json', usuarios)
            session['user_name'] = admin['nombre']
            registrar_actividad("Configuración", "Se actualizaron los datos de usuario.")
            return render_template('configuracion.html', admin=admin, success="Datos actualizados.")

        if accion == 'cambiar_password':
            actual = request.form.get('password_actual', '')
            nueva = request.form.get('password_nueva', '')
            confirmar = request.form.get('password_confirmar', '')
            if not check_password_hash(admin['password_hash'], actual) or nueva != confirmar or len(nueva) < 8:
                return render_template('configuracion.html', admin=admin, error="Error en contraseñas.")
            admin['password_hash'] = generate_password_hash(nueva)
            usuarios[0] = admin
            save_data('usuarios.json', usuarios)
            registrar_actividad("Seguridad", "Se cambió la contraseña.")
            return render_template('configuracion.html', admin=admin, success="Contraseña actualizada.")
    return render_template('configuracion.html', admin=admin)

@app.route('/')
@login_required
def home():
    offset_semanas = request.args.get('semana', default=0, type=int)
    clientes = load_data('clientes.json')
    ventas = load_data('ventas.json')
    
    total_clientes = len(clientes)
    total_ventas_general = sum(v.get('total', 0) for v in ventas)
    hoy = datetime.date.today().isoformat()
    ganancias_hoy = sum(v.get('total', 0) for v in ventas if v.get('fecha') == hoy)
    productos_vendidos_hoy = sum(v.get('cantidad', 0) for v in ventas if v.get('fecha') == hoy)
    
    hoy_date = datetime.date.today()
    year, week_num, _ = hoy_date.isocalendar()
    fecha_lunes = datetime.date.fromisocalendar(year, week_num + offset_semanas, 1)
    nombres_dias = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    dias_semana, ganancias_semana_data, productos_semana_data = [], [], []
    
    for i in range(0, 7):
        fecha_str = (fecha_lunes + datetime.timedelta(days=i)).isoformat()
        dias_semana.append(f"{nombres_dias[i]} {(fecha_lunes + datetime.timedelta(days=i)).day}")
        ganancias_semana_data.append(sum(v.get('total', 0) for v in ventas if v.get('fecha') == fecha_str))
        productos_semana_data.append(sum(v.get('cantidad', 0) for v in ventas if v.get('fecha') == fecha_str))
    
    return render_template('home.html', 
                          total_clientes=total_clientes, 
                          total_ventas=total_ventas_general, 
                          ganancias_hoy=ganancias_hoy,
                          productos_vendidos_hoy=productos_vendidos_hoy,
                          ganancias_semana=sum(ganancias_semana_data),
                          productos_vendidos_semana=sum(productos_semana_data),
                          dias_semana=dias_semana,
                          ganancias_semana_data=ganancias_semana_data,
                          productos_semana_data=productos_semana_data,
                          offset_actual=offset_semanas)

@app.route('/clientes', methods=['GET', 'POST'])
@login_required
def clientes_view():
    clientes = load_data('clientes.json')
    productos = load_data('productos.json') # Para el modal de asignación
    
    if request.method == 'POST':
        accion = request.form.get('accion')
        if accion == 'eliminar':
            try:
                cliente_id = int(request.form.get('cliente_id'))
                clientes = [c for c in clientes if c['id_cliente'] != cliente_id]
                save_data('clientes.json', clientes)
                return redirect(url_for('clientes_view'))
            except: pass
            
        if accion == 'asignar_productos':
            try:
                cliente_id = int(request.form.get('cliente_id'))
                # Obtenemos la lista de IDs de productos seleccionados
                productos_asignados = request.form.getlist('productos_asignados[]')
                productos_asignados = [int(pid) for pid in productos_asignados]
                
                for c in clientes:
                    if c['id_cliente'] == cliente_id:
                        c['productos_asignados'] = productos_asignados
                        break
                save_data('clientes.json', clientes)
                return redirect(url_for('clientes_view'))
            except: pass
        
        nombre = request.form.get('nombre', '').strip()
        telefono = request.form.get('telefono', '').strip()
        email = request.form.get('email', '').strip()
        
        if not nombre or not validar_nombre(nombre) or not validar_telefono(telefono) or not validar_email(email):
            return render_template('clientes.html', clientes=clientes, productos=productos, error="Datos inválidos.")
            
        nuevo_cliente = {'id_cliente': len(clientes) + 1, 'nombre': nombre, 'telefono': telefono, 'email': email, 'productos_asignados': []}
        clientes.append(nuevo_cliente)
        save_data('clientes.json', clientes)
        return redirect(url_for('clientes_view'))
    return render_template('clientes.html', clientes=clientes, productos=productos, error=None)

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
            except: pass
        
        nombre = request.form.get('nombre', '').strip()
        telefono = request.form.get('telefono', '').strip()
        if not nombre or not validar_nombre(nombre) or not validar_telefono(telefono):
            return render_template('empleados.html', empleados=empleados, error="Datos inválidos.")
            
        nuevo_empleado = {'id_empleado': len(empleados) + 1, 'nombre': nombre, 'cargo': request.form.get('cargo', ''), 'telefono': telefono}
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
            except: pass
        nombre_empresa = request.form.get('nombre_empresa', '').strip()
        que_provee = request.form.get('que_provee', '').strip()
        if not nombre_empresa:
            return render_template('proveedores.html', proveedores=proveedores, error="El nombre es obligatorio")
        if accion == 'editar':
            try:
                proveedor_id = int(request.form.get('proveedor_id'))
                for p in proveedores:
                    if p['id_proveedor'] == proveedor_id:
                        p['nombre_empresa'], p['que_provee'] = nombre_empresa, que_provee
                        p['telefono'] = request.form.get('telefono', '').strip()
                        p['email'] = request.form.get('email', '').strip()
                        break
                save_data('proveedores.json', proveedores)
                return redirect(url_for('proveedores_view'))
            except: pass
        else:
            proveedores.append({
                'id_proveedor': len(proveedores) + 1, 'nombre_empresa': nombre_empresa, 'que_provee': que_provee,
                'telefono': request.form.get('telefono', '').strip(), 'email': request.form.get('email', '').strip()
            })
            save_data('proveedores.json', proveedores)
            return redirect(url_for('proveedores_view'))
    return render_template('proveedores.html', proveedores=proveedores, error=None)

@app.route('/productos', methods=['GET', 'POST'])
@login_required
def productos_view():
    productos = load_data('productos.json')
    inventario = load_data('inventario.json')
    
    if request.method == 'POST':
        accion = request.form.get('accion')
        
        if accion == 'aumentar_stock':
            try:
                producto_id = int(request.form.get('producto_id'))
                cantidad_aumentar = int(request.form.get('cantidad_aumentar', 0))
                if cantidad_aumentar <= 0: raise ValueError
                prod_actual = next((p for p in productos if p['id_producto'] == producto_id), None)
                if not prod_actual: raise ValueError

                receta = prod_actual.get('materiales', [])
                
                # Verificar stock de materiales
                for item in receta:
                    mat_id = int(item['id_material'])
                    cant_necesaria = float(item['cantidad']) * cantidad_aumentar
                    inv_item = next((i for i in inventario if int(i['id_inventario']) == mat_id), None)
                    if not inv_item or float(inv_item['cantidad']) < cant_necesaria:
                        nom_mat = inv_item['material'] if inv_item else "Desconocido"
                        return render_template('productos.html', productos=productos, inventario=inventario, error=f"Stock insuficiente de '{nom_mat}'.")

                # Descontar materiales
                for item in receta:
                    mat_id = int(item['id_material'])
                    cant_necesaria = float(item['cantidad']) * cantidad_aumentar
                    for inv_item in inventario:
                        if int(inv_item['id_inventario']) == mat_id:
                            inv_item['cantidad'] = float(inv_item['cantidad']) - cant_necesaria
                            break
                
                save_data('inventario.json', inventario)
                
                if 'stock' not in prod_actual: prod_actual['stock'] = 0
                prod_actual['stock'] += cantidad_aumentar
                save_data('productos.json', productos)
                registrar_actividad("Fabricación", f"Se fabricaron {cantidad_aumentar} uds de '{prod_actual['nombre_producto']}'.")
                return redirect(url_for('productos_view'))
            except Exception as e:
                return render_template('productos.html', productos=productos, inventario=inventario, error=f"Error al fabricar: {str(e)}")

        if accion == 'eliminar':
            try:
                producto_id = int(request.form.get('producto_id'))
                productos = [p for p in productos if p['id_producto'] != producto_id]
                save_data('productos.json', productos)
                return redirect(url_for('productos_view'))
            except: pass

        nombre_producto = request.form.get('nombre_producto', '').strip()
        try:
            precio = float(request.form.get('precio', '0'))
            if precio <= 0: raise ValueError
        except:
            return render_template('productos.html', productos=productos, inventario=inventario, error="Precio inválido")
        
        imagen_url = ""
        if 'imagen_file' in request.files:
            file = request.files['imagen_file']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_name = secrets.token_hex(8) + "_" + filename
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
                imagen_url = url_for('static', filename='uploads/' + unique_name)
        if not imagen_url: imagen_url = request.form.get('imagen_url', '').strip()

        # --- AQUI ESTABA EL ERROR 500 (Faltaba convertir y validar las cantidades) ---
        materiales_seleccionados = []
        mat_ids = request.form.getlist('material_id[]')
        mat_cants = request.form.getlist('material_cantidad[]')
        mat_unidades = request.form.getlist('material_unidad[]') # Capturamos la unidad
        
        for i in range(len(mat_ids)):
            if mat_ids[i] and mat_cants[i]:
                try:
                    cant_float = float(mat_cants[i])
                    materiales_seleccionados.append({
                        'id_material': int(mat_ids[i]),
                        'cantidad': cant_float,
                        'unidad': mat_unidades[i] if i < len(mat_unidades) else 'u'
                    })
                except ValueError:
                    pass # Si ponen letras en la cantidad, lo ignoramos en vez de explotar

        if accion == 'editar':
            try:
                producto_id = int(request.form.get('producto_id'))
                for p in productos:
                    if p['id_producto'] == producto_id:
                        p['nombre_producto'], p['precio'] = nombre_producto, precio
                        if imagen_url: p['imagen'] = imagen_url
                        p['mostrar_como_nuevo'] = 'mostrar_como_nuevo' in request.form
                        p['materiales'] = materiales_seleccionados
                        break
                save_data('productos.json', productos)
                return redirect(url_for('productos_view'))
            except: pass
        else:
            data = load_data('productos.json')
            data.append({
                'id_producto': len(data) + 1, 'nombre_producto': nombre_producto, 'precio': precio,
                'imagen': imagen_url, 'mostrar_como_nuevo': 'mostrar_como_nuevo' in request.form,
                'materiales': materiales_seleccionados, 'stock': 0
            })
            save_data('productos.json', data)
            registrar_actividad("Producto Nuevo", f"Se creó el producto '{nombre_producto}'.")
            return redirect(url_for('productos_view'))
            
    return render_template('productos.html', productos=productos, inventario=inventario, error=None)

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
            except: pass
        
        if accion == 'editar':
            try:
                inventario_id = int(request.form.get('inventario_id'))
                nueva_cantidad = float(request.form.get('cantidad', '0'))
                for item in inventario:
                    if item['id_inventario'] == inventario_id:
                        item['cantidad'] = nueva_cantidad
                        break
                save_data('inventario.json', inventario)
                return redirect(url_for('inventario_view'))
            except: pass
        
        material = request.form.get('material', '').strip()
        cantidad = float(request.form.get('cantidad', '0'))
        proveedor = request.form.get('proveedor', '').strip()
        unidad_medida = request.form.get('unidad_medida', '').strip()
        
        if not material or not proveedor or not unidad_medida or cantidad < 0:
            return render_template('inventario.html', inventario=inventario, proveedores=proveedores, error="Datos inválidos")
        
        inventario.append({
            'id_inventario': len(inventario) + 1, 'material': material, 'cantidad': cantidad,
            'unidad_medida': unidad_medida, 'proveedor': proveedor
        })
        save_data('inventario.json', inventario)
        return redirect(url_for('inventario_view'))
    
    return render_template('inventario.html', inventario=inventario, proveedores=proveedores, error=None)

@app.route('/catalogo')
@login_required
def catalogo_view():
    return render_template('catalogo.html', productos=load_data('productos.json'))

@app.route('/ventas', methods=['GET', 'POST'])
@login_required
def ventas_view():
    productos = load_data('productos.json')
    clientes = load_data('clientes.json')
    ventas = load_data('ventas.json')
    
    if request.method == 'POST':
        try:
            id_cliente = int(request.form.get('id_cliente', 0))
            id_producto = int(request.form.get('id_producto', 0))
            cantidad_vender = int(request.form.get('cantidad', 0))
            
            prod_obj = next((p for p in productos if p['id_producto'] == id_producto), None)
            if not prod_obj or prod_obj.get('stock', 0) < cantidad_vender or cantidad_vender <= 0:
                raise ValueError("Datos de venta inválidos o stock insuficiente.")
            
            prod_obj['stock'] -= cantidad_vender
            save_data('productos.json', productos)
            
            ventas.append({
                'id_venta': len(ventas) + 1, 'id_cliente': id_cliente, 'id_producto': id_producto,
                'fecha': datetime.date.today().isoformat(), 'cantidad': cantidad_vender, 'total': prod_obj['precio'] * cantidad_vender
            })
            save_data('ventas.json', ventas)
            
            cli_obj = next((c for c in clientes if c['id_cliente'] == id_cliente), None)
            registrar_actividad("Venta", f"Venta de {cantidad_vender} uds de '{prod_obj['nombre_producto']}' a {cli_obj['nombre'] if cli_obj else 'Desconocido'}.")
            return redirect(url_for('ventas_view'))
        except Exception as e:
            return render_template('ventas.html', productos=productos, clientes=clientes, ventas=ventas, error=str(e))
            
    return render_template('ventas.html', productos=productos, clientes=clientes, ventas=ventas, error=None)

@app.route('/registro')
@login_required
def registro_view():
    return render_template('registro.html', logs=load_data('registro_actividad.json'))

@app.errorhandler(404)
def page_not_found(e): return redirect(url_for('login'))

@app.route('/manifest.json')
def serve_manifest(): return app.send_static_file('manifest.json')
@app.route('/sw.js')
def serve_sw(): return app.send_static_file('sw.js')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)