import json
import sqlite3
from datetime import date, datetime
import pandas as pd
import streamlit as st

# ==============================================================================
# CONFIGURACIÓN DE PÁGINA (SIX - DEPÓSITO Y TIENDA)
# ==============================================================================
st.set_page_config(
    page_title="Six - Control de Inventario y Ventas",
    page_icon="🍺",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilos CSS adaptados para temática de Tienda/Depósito Six
st.markdown(
    """
    <style>
    .six-header {
        background: linear-gradient(135deg, #DC2626 0%, #991B1B 100%);
        padding: 1.2rem 1.6rem;
        border-radius: 14px;
        color: white;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 12px rgba(220, 38, 38, 0.2);
    }
    .six-header h1 {
        margin: 0;
        font-size: 1.8rem;
        font-weight: 800;
        color: white;
    }
    .six-header p {
        margin: 0.2rem 0 0 0;
        font-size: 0.95rem;
        color: #FEE2E2;
    }
    
    div[data-testid="stMetric"] {
        background-color: rgba(220, 38, 38, 0.04);
        border: 1px solid rgba(220, 38, 38, 0.15);
        border-radius: 12px;
        padding: 10px 14px;
    }
    div[data-testid="stMetricValue"] {
        font-weight: 800;
        color: #991B1B;
    }
    
    .workflow-info {
        background-color: #FEF2F2;
        border-left: 4px solid #DC2626;
        padding: 12px 14px;
        border-radius: 0 8px 8px 0;
        font-size: 0.88rem;
        margin-bottom: 1rem;
        color: #7F1D1D;
    }

    button[kind="primary"] {
        background-color: #DC2626 !important;
        border-color: #DC2626 !important;
        font-weight: 700 !important;
    }
    
    .cloud-badge-ok {
        background-color: #DEF7EC;
        color: #03543F;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 700;
        display: inline-block;
        border: 1px solid #31C48D;
    }
    
    .cloud-badge-warn {
        background-color: #FEF08A;
        color: #713F12;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 700;
        display: inline-block;
        border: 1px solid #FACC15;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

DB_PATH = "inventario_antigravity.db"

# ==============================================================================
# CONEXIÓN UNIVERSAL DE BASE DE DATOS (NUBE POSTGRESQL O SQLITE LOCAL)
# Soporta Neon.tech, Supabase o cualquier PostgreSQL en la nube para que los
# datos NUNCA se borren cuando Streamlit Cloud duerme el contenedor.
# ==============================================================================
def get_connection():
    db_url = None
    try:
        if "DATABASE_URL" in st.secrets:
            db_url = st.secrets["DATABASE_URL"]
        elif "postgres" in st.secrets and "url" in st.secrets["postgres"]:
            db_url = st.secrets["postgres"]["url"]
    except Exception:
        db_url = None

    if db_url:
        import psycopg2
        try:
            conn = psycopg2.connect(db_url)
        except Exception:
            # Fallback en caso de incompatibilidad con parámetros de canal
            clean_url = db_url.replace("&channel_binding=require", "").replace("?channel_binding=require", "")
            conn = psycopg2.connect(clean_url)
        return conn, "postgres"
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn, "sqlite"

def init_db():
    conn, db_type = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            if db_type == "postgres":
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS articulos (
                        id SERIAL PRIMARY KEY,
                        descripcion TEXT NOT NULL,
                        precio NUMERIC(10,2) NOT NULL CHECK(precio >= 0),
                        cantidad_inventario INTEGER NOT NULL CHECK(cantidad_inventario >= 0),
                        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ventas (
                        id SERIAL PRIMARY KEY,
                        articulo_id INTEGER NOT NULL,
                        descripcion TEXT NOT NULL,
                        precio NUMERIC(10,2) NOT NULL,
                        cantidad_vendida INTEGER NOT NULL CHECK(cantidad_vendida > 0),
                        stock_previo INTEGER NOT NULL,
                        stock_resultante INTEGER NOT NULL,
                        fecha_venta DATE NOT NULL,
                        total NUMERIC(10,2) NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
            else:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS articulos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        descripcion TEXT NOT NULL,
                        precio REAL NOT NULL CHECK(precio >= 0),
                        cantidad_inventario INTEGER NOT NULL CHECK(cantidad_inventario >= 0),
                        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ventas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        articulo_id INTEGER NOT NULL,
                        descripcion TEXT NOT NULL,
                        precio REAL NOT NULL,
                        cantidad_vendida INTEGER NOT NULL CHECK(cantidad_vendida > 0),
                        stock_previo INTEGER NOT NULL,
                        stock_resultante INTEGER NOT NULL,
                        fecha_venta DATE NOT NULL,
                        total REAL NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (articulo_id) REFERENCES articulos (id)
                    );
                    """
                )
    finally:
        conn.close()

init_db()

# ==============================================================================
# OPERACIONES DE GESTIÓN Y EDICIÓN DEL INVENTARIO
# ==============================================================================
def obtener_articulos():
    conn, db_type = get_connection()
    try:
        df = pd.read_sql_query(
            "SELECT id, descripcion, precio, cantidad_inventario, fecha_creacion FROM articulos ORDER BY descripcion ASC",
            conn,
        )
        if not df.empty:
            df["precio"] = pd.to_numeric(df["precio"], errors="coerce").fillna(0.0)
            df["cantidad_inventario"] = pd.to_numeric(df["cantidad_inventario"], errors="coerce").fillna(0).astype(int)
        return df
    finally:
        conn.close()

def agregar_articulo(descripcion: str, precio: float, cantidad_inventario: int):
    conn, db_type = get_connection()
    q = "%s" if db_type == "postgres" else "?"
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                f"INSERT INTO articulos (descripcion, precio, cantidad_inventario) VALUES ({q}, {q}, {q})",
                (descripcion.strip(), round(float(precio), 2), int(cantidad_inventario)),
            )
    finally:
        conn.close()

def actualizar_articulo(articulo_id: int, nueva_descripcion: str, nuevo_precio: float, nuevo_stock: int):
    conn, db_type = get_connection()
    q = "%s" if db_type == "postgres" else "?"
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE articulos SET descripcion = {q}, precio = {q}, cantidad_inventario = {q} WHERE id = {q}",
                (nueva_descripcion.strip(), round(float(nuevo_precio), 2), int(nuevo_stock), int(articulo_id)),
            )
    finally:
        conn.close()

def eliminar_articulo(articulo_id: int):
    conn, db_type = get_connection()
    q = "%s" if db_type == "postgres" else "?"
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM articulos WHERE id = {q}", (int(articulo_id),))
    finally:
        conn.close()

def vaciar_inventario():
    conn, db_type = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM articulos")
            cursor.execute("DELETE FROM ventas")
    finally:
        conn.close()

# ==============================================================================
# FLUJO DE TRABAJO (ANTIGRAVITY WORKFLOW: SALIDAS Y RESTA AUTOMÁTICA)
# ==============================================================================
def ejecutar_workflow_salida(articulo_id: int, cantidad_vendida: int, fecha_venta: date):
    conn, db_type = get_connection()
    q = "%s" if db_type == "postgres" else "?"
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT descripcion, precio, cantidad_inventario FROM articulos WHERE id = {q}",
                (int(articulo_id),),
            )
            item = cursor.fetchone()
            if not item:
                return False, "❌ El producto seleccionado no existe."
                
            descripcion, precio, stock_actual = item
            precio = float(precio)
            stock_actual = int(stock_actual)
            
            if cantidad_vendida <= 0:
                return False, "❌ La cantidad que se vende debe ser mayor a 0."
                
            if cantidad_vendida > stock_actual:
                return (
                    False,
                    f"❌ Stock insuficiente en el Six. Solo quedan {stock_actual} unidades de '{descripcion}'.",
                )
                
            nuevo_stock = stock_actual - cantidad_vendida
            total = round(precio * cantidad_vendida, 2)
            
            # Ejecución atómica de la resta
            cursor.execute(
                f"UPDATE articulos SET cantidad_inventario = {q} WHERE id = {q}",
                (nuevo_stock, int(articulo_id)),
            )
            
            # Registro en tabla de ventas con fecha_venta
            cursor.execute(
                f"""
                INSERT INTO ventas (
                    articulo_id, descripcion, precio, cantidad_vendida, 
                    stock_previo, stock_resultante, fecha_venta, total
                )
                VALUES ({q}, {q}, {q}, {q}, {q}, {q}, {q}, {q})
                """,
                (
                    int(articulo_id),
                    descripcion,
                    precio,
                    int(cantidad_vendida),
                    stock_actual,
                    nuevo_stock,
                    str(fecha_venta),
                    total,
                ),
            )
            return True, {
                "descripcion": descripcion,
                "cantidad_vendida": cantidad_vendida,
                "stock_previo": stock_actual,
                "nuevo_stock": nuevo_stock,
                "fecha_venta": fecha_venta,
                "total": total,
            }
    except Exception as e:
        return False, f"❌ Error en la transacción: {str(e)}"
    finally:
        conn.close()

def obtener_historial_ventas():
    conn, db_type = get_connection()
    try:
        df = pd.read_sql_query(
            """
            SELECT 
                id AS "Folio",
                fecha_venta AS "Fecha de Venta",
                descripcion AS "Artículo / Producto",
                precio AS "Precio ($)",
                cantidad_vendida AS "Cant. Vendida",
                stock_previo AS "Stock Previo",
                stock_resultante AS "Stock Actual",
                total AS "Total ($)",
                timestamp AS "Hora"
            FROM ventas
            ORDER BY id DESC
            """,
            conn,
        )
        if not df.empty:
            df["Precio ($)"] = pd.to_numeric(df["Precio ($)"], errors="coerce").fillna(0.0)
            df["Total ($)"] = pd.to_numeric(df["Total ($)"], errors="coerce").fillna(0.0)
            df["Cant. Vendida"] = pd.to_numeric(df["Cant. Vendida"], errors="coerce").fillna(0).astype(int)
        return df
    finally:
        conn.close()

# ==============================================================================
# ENCABEZADO Y ESTADO DE ALMACENAMIENTO
# ==============================================================================
_, current_db_type = get_connection()

st.markdown(
    """
    <div class="six-header">
        <h1>🍺 Six - Control de Inventario & Punto de Venta</h1>
        <p>Sistema nativo para tienda Six • Base de datos persistente y flujo de ventas</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### 🏪 Menú del Six")
    vista_seleccionada = st.radio(
        "Ir a la vista:",
        [
            "🏷️ Catálogo (Gestionar y Editar)", 
            "🛒 Punto de Venta (Cobro)", 
            "📜 Historial de Salidas",
            "💾 Respaldos & Nube Permanente"
        ],
        index=0,
    )
    st.markdown("---")
    
    # Estado de la conexión
    if current_db_type == "postgres":
        st.markdown('<div class="cloud-badge-ok">🟢 Base en la Nube (Permanente)</div>', unsafe_allow_html=True)
        st.caption("Tus productos y ventas se guardan en la nube y NUNCA se borran.")
    else:
        st.markdown('<div class="cloud-badge-warn">⚠️ Almacenamiento Local (Temporal)</div>', unsafe_allow_html=True)
        st.caption("En Streamlit Cloud, los archivos locales se reinician cuando la app duerme. Conecta la nube gratis en la sección **💾 Respaldos & Nube Permanente**.")

    st.markdown("---")
    st.markdown(
        """
        **⚡ Regla del Workflow:**
        - Al registrar una venta:
          `cantidad_inventario = cantidad_inventario - cantidad_vendida`
        - Guarda `fecha_venta`.
        """
    )
    st.caption("🍺 Tienda Six • Antigravity Engine")

# ==============================================================================
# VISTA 1: CATÁLOGO DE PRODUCTOS (GESTIÓN Y EDICIÓN COMPLETA)
# ==============================================================================
if vista_seleccionada == "🏷️ Catálogo (Gestionar y Editar)":
    st.subheader("🏷️ Catálogo de Artículos del Six")
    st.write("Agrega tus productos, edita precios, reabastece existencias y consulta tu inventario.")

    df_art = obtener_articulos()

    tab_nuevo, tab_editar = st.tabs([
        "➕ Agregar Producto",
        "✏️ Editar / Reabastecer Artículo"
    ])

    # ----------------------------------------------------
    # TAB 1: AGREGAR NUEVO ARTÍCULO
    # ----------------------------------------------------
    with tab_nuevo:
        st.write("Ingresa los datos del artículo para darlo de alta en tu inventario:")
        with st.form("form_alta_producto", clear_on_submit=True):
            col_d, col_p, col_c = st.columns([3, 2, 2])
            with col_d:
                desc_input = st.text_input("Descripción del artículo *", placeholder="Ej: Six Pack Tecate Light, Caguama Carta Blanca, Hielo 5kg...")
            with col_p:
                precio_input = st.number_input("Precio al público ($) *", min_value=0.01, step=1.0, value=25.00, format="%.2f")
            with col_c:
                stock_input = st.number_input("Cantidad de inventario inicial *", min_value=0, step=1, value=12)
            
            submit_producto = st.form_submit_button("💾 Guardar Artículo en el Catálogo", type="primary", use_container_width=True)
            if submit_producto:
                if not desc_input.strip():
                    st.error("Por favor ingresa una descripción para el artículo.")
                else:
                    agregar_articulo(desc_input, precio_input, stock_input)
                    st.success(f"✅ ¡Artículo '{desc_input}' guardado con éxito con {stock_input} unidades a ${precio_input:,.2f}!")
                    st.rerun()

    # ----------------------------------------------------
    # TAB 2: EDITAR / REABASTECER ARTÍCULO EXISTENTE
    # ----------------------------------------------------
    with tab_editar:
        if df_art.empty:
            st.info("Aún no tienes artículos registrados. Agrega tus primeros productos en la pestaña **➕ Agregar Producto**.")
        else:
            dict_articulos = {
                f"{row['descripcion']} (Stock: {row['cantidad_inventario']} | ${row['precio']:,.2f})": row["id"]
                for _, row in df_art.iterrows()
            }

            articulo_a_editar_label = st.selectbox(
                "Selecciona el artículo que deseas modificar o reabastecer:",
                options=list(dict_articulos.keys()),
                key="select_edit_item"
            )
            item_id = dict_articulos[articulo_a_editar_label]
            item_data = df_art[df_art["id"] == item_id].iloc[0]

            with st.form("form_editar_articulo"):
                col_e1, col_e2, col_e3 = st.columns([3, 2, 2])
                with col_e1:
                    edit_desc = st.text_input("Descripción del artículo:", value=str(item_data["descripcion"]))
                with col_e2:
                    edit_precio = st.number_input(
                        "Precio ($):", 
                        min_value=0.01, 
                        value=float(item_data["precio"]), 
                        step=0.50, 
                        format="%.2f"
                    )
                with col_e3:
                    edit_stock = st.number_input(
                        "Cantidad en inventario actual:", 
                        min_value=0, 
                        value=int(item_data["cantidad_inventario"]), 
                        step=1
                    )

                st.caption("💡 Puedes cambiar el nombre, actualizar precios o sumar nuevo stock cuando llegue mercancía de tus distribuidores.")

                c_save, c_del = st.columns([4, 1])
                with c_save:
                    btn_guardar_edicion = st.form_submit_button("💾 Guardar Cambios", type="primary", use_container_width=True)
                with c_del:
                    btn_eliminar = st.form_submit_button("🗑️ Eliminar", use_container_width=True)

                if btn_guardar_edicion:
                    if not edit_desc.strip():
                        st.error("La descripción no puede estar vacía.")
                    else:
                        actualizar_articulo(item_id, edit_desc, edit_precio, edit_stock)
                        st.success(f"✅ ¡Artículo '{edit_desc}' actualizado con éxito! Nuevo stock: {edit_stock} unid. | Precio: ${edit_precio:,.2f}")
                        st.rerun()

                if btn_eliminar:
                    eliminar_articulo(item_id)
                    st.warning(f"🗑️ Artículo '{item_data['descripcion']}' eliminado.")
                    st.rerun()

    st.markdown("---")

    # Métricas Globales del Inventario
    total_articulos = len(df_art)
    total_unidades = int(df_art["cantidad_inventario"].sum()) if not df_art.empty else 0
    valor_inventario = (df_art["precio"] * df_art["cantidad_inventario"]).sum() if not df_art.empty else 0.0

    m1, m2, m3 = st.columns(3)
    m1.metric("📦 Variedad de Productos", f"{total_articulos} artículos")
    m2.metric("🍺 Stock Total en Tienda", f"{total_unidades} unidades")
    m3.metric("💰 Valor del Inventario", f"${valor_inventario:,.2f}")

    # Tabla con Buscador
    st.markdown("### 📋 Lista de Inventario del Six")
    
    if df_art.empty:
        st.info("💡 **El inventario está listo y vacío.** Comienza a registrar tus productos en la pestaña superior **➕ Agregar Producto**.")
    else:
        c_search, c_check = st.columns([3, 1])
        with c_search:
            filtro_txt = st.text_input("🔍 Buscar artículo por nombre:", placeholder="Escribe para buscar...")
        with c_check:
            solo_bajo = st.checkbox("⚠️ Ver solo stock bajo (≤ 5 unid.)", value=False)

        df_mostrar = df_art.copy()
        if filtro_txt:
            df_mostrar = df_mostrar[df_mostrar["descripcion"].str.contains(filtro_txt, case=False, na=False)]
        if solo_bajo:
            df_mostrar = df_mostrar[df_mostrar["cantidad_inventario"] <= 5]

        df_presentacion = df_mostrar.rename(
            columns={
                "id": "ID",
                "descripcion": "Descripción del Artículo",
                "precio": "Precio al Público ($)",
                "cantidad_inventario": "Cantidad de Inventario",
                "fecha_creacion": "Fecha de Alta",
            }
        )

        st.dataframe(
            df_presentacion.style.format({
                "Precio al Público ($)": "${:,.2f}",
                "Cantidad de Inventario": "{:d} unid."
            }),
            use_container_width=True,
            hide_index=True,
        )

# ==============================================================================
# VISTA 2: PUNTO DE VENTA (REGISTRO DE SALIDAS Y FLUJO DE TRABAJO)
# ==============================================================================
elif vista_seleccionada == "🛒 Punto de Venta (Cobro)":
    st.subheader("🛒 Punto de Venta - Mostrador Six")
    st.write("Registra salidas y ventas de producto. El flujo de trabajo restará automáticamente la mercancía y guardará la fecha.")

    df_art = obtener_articulos()
    disponibles = df_art[df_art["cantidad_inventario"] > 0] if not df_art.empty else pd.DataFrame()

    if df_art.empty:
        st.info("⚠️ Aún no has registrado ningún producto. Ve al **Catálogo** para agregar los artículos de tu Six.")
    elif disponibles.empty:
        st.warning("⚠️ Hay artículos registrados pero todos están agotados (stock 0). Reabastece inventario en el **Catálogo**.")
    else:
        col_form, col_ticket = st.columns([3, 2])

        with col_form:
            st.markdown(
                """
                <div class="workflow-info">
                    <strong>⚙️ Flujo de Trabajo en Antigravity:</strong><br>
                    Al presionar <em>'Confirmar Venta'</em>, se descuenta el stock de manera atómica:
                    <br><code>Inventario Final = Inventario Actual - Cantidad que se vende</code>
                    <br>y se registra la <strong>Fecha de Venta</strong> en el libro de transacciones.
                </div>
                """,
                unsafe_allow_html=True,
            )

            dict_opciones = {
                f"{row['descripcion']} (Stock: {row['cantidad_inventario']} | ${row['precio']:,.2f})": row["id"]
                for _, row in disponibles.iterrows()
            }

            with st.form("form_pos_six"):
                item_label = st.selectbox(
                    "Selecciona el producto a despachar *",
                    options=list(dict_opciones.keys()),
                )
                articulo_id = dict_opciones[item_label]
                item_row = disponibles[disponibles["id"] == articulo_id].iloc[0]

                stock_maximo = int(item_row["cantidad_inventario"])
                precio_unitario = float(item_row["precio"])
                descripcion_sel = str(item_row["descripcion"])

                c_cant, c_fec = st.columns(2)
                with c_cant:
                    cant_vender = st.number_input(
                        "Cantidad que se vende *",
                        min_value=1,
                        max_value=stock_maximo,
                        value=1,
                        step=1,
                    )
                with c_fec:
                    fecha_sel = st.date_input(
                        "Fecha de venta *",
                        value=date.today(),
                    )

                btn_vender = st.form_submit_button("⚡ Confirmar Venta y Restar del Inventario", type="primary", use_container_width=True)

                if btn_vender:
                    exito, detalle = ejecutar_workflow_salida(articulo_id, cant_vender, fecha_sel)
                    if exito:
                        st.success(
                            f"✅ **¡Venta Registrada Exitosamente!**  \n"
                            f"• **Producto:** {detalle['descripcion']}  \n"
                            f"• **Salida:** -{detalle['cantidad_vendida']} unidades  \n"
                            f"• **Stock:** {detalle['stock_previo']} → **{detalle['nuevo_stock']} unidades**  \n"
                            f"• **Fecha guardada:** {detalle['fecha_venta']}  \n"
                            f"• **Total cobrado:** ${detalle['total']:,.2f}"
                        )
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(detalle)

        with col_ticket:
            st.markdown("### 🧾 Ticket de Cobro")
            subtotal = cant_vender * precio_unitario
            stock_queda = stock_maximo - cant_vender

            st.markdown(
                f"""
                - **Producto:** `{descripcion_sel}`
                - **Precio unitario:** `${precio_unitario:,.2f}`
                - **Stock actual:** `{stock_maximo}` unid.
                - **Cantidad a vender:** `{cant_vender}` unid.
                - **Quedarán en bodega:** **`{stock_queda}`** unid.
                - **Fecha de operación:** `{fecha_sel}`
                ---
                ### Total a Cobrar:
                # `${subtotal:,.2f}`
                """
            )

# ==============================================================================
# VISTA 3: HISTORIAL DE SALIDAS Y AUDITORÍA
# ==============================================================================
elif vista_seleccionada == "📜 Historial de Salidas":
    st.subheader("📜 Historial de Salidas del Six")
    st.write("Auditoría de todas las ventas realizadas, fechas registradas y stock deducido.")

    df_historial = obtener_historial_ventas()

    if df_historial.empty:
        st.info("Aún no se han registrado ventas en el sistema.")
    else:
        total_acumulado = df_historial["Total ($)"].sum()
        total_unidades = int(df_historial["Cant. Vendida"].sum())
        total_transacciones = len(df_historial)

        c1, c2, c3 = st.columns(3)
        c1.metric("💵 Total Vendido en Caja", f"${total_acumulado:,.2f}")
        c2.metric("🛍️ Unidades Despachadas", f"{total_unidades} unid.")
        c3.metric("📝 Ventas Registradas", f"{total_transacciones}")

        st.dataframe(
            df_historial.style.format({
                "Precio ($)": "${:,.2f}",
                "Total ($)": "${:,.2f}",
                "Cant. Vendida": "{:d} unid.",
                "Stock Previo": "{:d}",
                "Stock Actual": "{:d}",
            }),
            use_container_width=True,
            hide_index=True,
        )

# ==============================================================================
# VISTA 4: RESPALDOS Y CONEXIÓN PERMANENTE A LA NUBE
# ==============================================================================
elif vista_seleccionada == "💾 Respaldos & Nube Permanente":
    st.subheader("🛡️ Protección de Datos y Nube Permanente")
    
    st.markdown(
        """
        > **¿Por qué se borran los datos al día siguiente en Streamlit Cloud?**  
        > El plan gratuito de Streamlit Community Cloud apaga los servidores cuando nadie los está usando para ahorrar energía. 
        > Al volver a abrir la página, Streamlit enciende un servidor nuevo desde GitHub y **borra cualquier archivo local**, incluyendo bases de datos SQLite temporales.
        """
    )
    
    col_cloud, col_backup = st.columns([3, 2])
    
    with col_cloud:
        st.markdown("### ☁️ Solución Definitiva: Conectar Base de Datos en la Nube (Gratis)")
        st.write(
            "Con una base de datos PostgreSQL gratuita en la nube, **tus datos quedan guardados para siempre**, nunca se borran y se actualizan al instante entre celulares y computadoras."
        )
        
        with st.expander("👉 Pasos para activar la Nube Gratuita en 2 minutos (con Neon.tech)", expanded=True):
            st.markdown(
                """
                1. Entra a **[neon.tech](https://neon.tech)** y haz clic en **Sign up** (puedes iniciar sesión con tu cuenta de GitHub con 1 solo clic).
                2. Haz clic en **Create Project** (nómbralo `six-inventario`).
                3. Copia la cadena de conexión **Connection String** que te da (se ve como `postgresql://neondb_owner:xxxxx@ep-xyz.us-east-2.aws.neon.tech/neondb?sslmode=require`).
                4. Ve a tu panel en **[share.streamlit.io](https://share.streamlit.io)**:
                   - Haz clic en los **3 puntitos `...`** junto a tu app $\\rightarrow$ **Settings** $\\rightarrow$ **Secrets**.
                   - Pega lo siguiente y guarda:
                     ```toml
                     DATABASE_URL = "tu_cadena_de_conexion_aqui"
                     ```
                5. **¡Listo!** Tu aplicación ahora guardará todo en la nube permanente 24/7 sin borrarse jamás.
                """
            )
            
    with col_backup:
        st.markdown("### 💾 Copia de Seguridad Inmediata")
        st.write("Descarga tu inventario a tu computadora o celular para tener un respaldo en archivo:")
        
        df_art_b = obtener_articulos()
        df_ventas_b = obtener_historial_ventas()
        
        backup_dict = {
            "articulos": df_art_b.to_dict(orient="records"),
            "ventas": df_ventas_b.to_dict(orient="records"),
            "fecha_respaldo": str(datetime.now())
        }
        json_backup = json.dumps(backup_dict, indent=2, default=str)
        
        st.download_button(
            label="💾 Descargar Copia de Seguridad (.json)",
            data=json_backup,
            file_name=f"respaldo_six_{date.today()}.json",
            mime="application/json",
            use_container_width=True
        )
        
        st.write("---")
        st.markdown("### 📥 Restaurar Copia de Seguridad")
        st.write("Si alguna vez se reinicia tu servidor, sube tu archivo aquí para recuperar todo en 1 segundo:")
        
        archivo_subido = st.file_uploader("Selecciona tu archivo .json de respaldo", type=["json"])
        if archivo_subido is not None:
            if st.button("🚀 Restaurar Datos desde Archivo", type="primary"):
                try:
                    data = json.load(archivo_subido)
                    articulos_cargados = data.get("articulos", [])
                    
                    conn, db_type = get_connection()
                    q = "%s" if db_type == "postgres" else "?"
                    with conn:
                        cursor = conn.cursor()
                        for art in articulos_cargados:
                            cursor.execute(
                                f"INSERT INTO articulos (descripcion, precio, cantidad_inventario) VALUES ({q}, {q}, {q})",
                                (art["descripcion"], float(art["precio"]), int(art["cantidad_inventario"]))
                            )
                    st.success(f"✅ ¡Se restauraron {len(articulos_cargados)} artículos con éxito!")
                    st.rerun()
                except Exception as err:
                    st.error(f"Error al restaurar: {str(err)}")
