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
    </style>
    """,
    unsafe_allow_html=True,
)

DB_PATH = "inventario_antigravity.db"

# ==============================================================================
# BASE DE DATOS (SQLite)
# Base limpia: No contiene productos precargados; el cliente ingresa su catálogo.
# Campos:
# - descripcion: descripción del artículo
# - precio: precio del artículo
# - cantidad_inventario: cantidad de inventario
# - cantidad_vendida: cantidad que se vende
# - fecha_venta: fecha de venta
# ==============================================================================
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Tabla del Catálogo de Artículos (inicia 100% limpia)
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
        
        # Tabla del Punto de Venta / Salidas
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
        conn.commit()

init_db()

# ==============================================================================
# OPERACIONES DE GESTIÓN Y EDICIÓN DEL INVENTARIO
# ==============================================================================
def obtener_articulos():
    """Recupera todos los artículos registrados por el usuario."""
    with get_connection() as conn:
        df = pd.read_sql_query(
            "SELECT id, descripcion, precio, cantidad_inventario, fecha_creacion FROM articulos ORDER BY descripcion ASC",
            conn,
        )
        return df

def agregar_articulo(descripcion: str, precio: float, cantidad_inventario: int):
    """Agrega un nuevo artículo al catálogo del Six."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO articulos (descripcion, precio, cantidad_inventario) VALUES (?, ?, ?)",
            (descripcion.strip(), round(precio, 2), int(cantidad_inventario)),
        )
        conn.commit()

def actualizar_articulo(articulo_id: int, nueva_descripcion: str, nuevo_precio: float, nuevo_stock: int):
    """Actualiza la descripción, el precio o el inventario de un artículo existente."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE articulos 
            SET descripcion = ?, precio = ?, cantidad_inventario = ? 
            WHERE id = ?
            """,
            (nueva_descripcion.strip(), round(nuevo_precio, 2), int(nuevo_stock), articulo_id),
        )
        conn.commit()

def eliminar_articulo(articulo_id: int):
    """Elimina un artículo del inventario."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM articulos WHERE id = ?", (articulo_id,))
        conn.commit()

def vaciar_inventario():
    """Limpia todo el inventario si el usuario desea reiniciar desde cero."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM articulos")
        cursor.execute("DELETE FROM ventas")
        conn.commit()

# ==============================================================================
# FLUJO DE TRABAJO (ANTIGRAVITY WORKFLOW: SALIDAS Y RESTA AUTOMÁTICA)
# ==============================================================================
def ejecutar_workflow_salida(articulo_id: int, cantidad_vendida: int, fecha_venta: date):
    """
    FLUJO DE TRABAJO AUTOMÁTICO EN ANTIGRAVITY:
    1. Verifica existencia de stock en el Six.
    2. Resta automáticamente: cantidad_inventario = cantidad_inventario - cantidad_vendida
    3. Registra la salida con la fecha de venta.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT descripcion, precio, cantidad_inventario FROM articulos WHERE id = ?",
            (articulo_id,),
        )
        item = cursor.fetchone()
        if not item:
            return False, "❌ El producto seleccionado no existe."
            
        descripcion, precio, stock_actual = item
        
        if cantidad_vendida <= 0:
            return False, "❌ La cantidad que se vende debe ser mayor a 0."
            
        if cantidad_vendida > stock_actual:
            return (
                False,
                f"❌ Stock insuficiente en el Six. Solo quedan {stock_actual} unidades de '{descripcion}'.",
            )
            
        nuevo_stock = stock_actual - cantidad_vendida
        total = round(precio * cantidad_vendida, 2)
        
        # Ejecución atómica de la resta y guardado de fecha
        cursor.execute(
            "UPDATE articulos SET cantidad_inventario = ? WHERE id = ?",
            (nuevo_stock, articulo_id),
        )
        
        cursor.execute(
            """
            INSERT INTO ventas (
                articulo_id, descripcion, precio, cantidad_vendida, 
                stock_previo, stock_resultante, fecha_venta, total
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                articulo_id,
                descripcion,
                precio,
                cantidad_vendida,
                stock_actual,
                nuevo_stock,
                str(fecha_venta),
                total,
            ),
        )
        
        conn.commit()
        return True, {
            "descripcion": descripcion,
            "cantidad_vendida": cantidad_vendida,
            "stock_previo": stock_actual,
            "nuevo_stock": nuevo_stock,
            "fecha_venta": fecha_venta,
            "total": total,
        }

def obtener_historial_ventas():
    with get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT 
                id AS 'Folio',
                fecha_venta AS 'Fecha de Venta',
                descripcion AS 'Artículo / Producto',
                precio AS 'Precio ($)',
                cantidad_vendida AS 'Cant. Vendida',
                stock_previo AS 'Stock Previo',
                stock_resultante AS 'Stock Actual',
                total AS 'Total ($)',
                timestamp AS 'Hora'
            FROM ventas
            ORDER BY id DESC
            """,
            conn,
        )
        return df

# ==============================================================================
# ENCABEZADO Y NAVEGACIÓN
# ==============================================================================
st.markdown(
    """
    <div class="six-header">
        <h1>🍺 Six - Control de Inventario & Punto de Venta</h1>
        <p>Sistema nativo para tienda Six • Catálogo limpio listo para registrar tus productos</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### 🏪 Menú del Six")
    vista_seleccionada = st.radio(
        "Ir a la vista:",
        ["🏷️ Catálogo (Gestionar y Editar)", "🛒 Punto de Venta (Cobro)", "📜 Historial de Salidas"],
        index=0,
    )
    st.markdown("---")
    st.markdown(
        """
        **⚡ Regla del Workflow:**
        - Al registrar una venta:
          `cantidad_inventario = cantidad_inventario - cantidad_vendida`
        - Guarda `fecha_venta`.
        """
    )
    st.markdown("---")
    st.caption("🍺 Tienda Six • Antigravity Engine")

# ==============================================================================
# VISTA 1: CATÁLOGO DE PRODUCTOS (GESTIÓN Y EDICIÓN COMPLETA)
# ==============================================================================
if vista_seleccionada == "🏷️ Catálogo (Gestionar y Editar)":
    st.subheader("🏷️ Catálogo de Artículos del Six")
    st.write("Agrega tus productos, edita precios, reabastece existencias y consulta tu inventario.")

    df_art = obtener_articulos()

    # Si no hay productos, mostramos como primera pestaña "Agregar Producto"
    tab_nuevo, tab_editar, tab_opciones = st.tabs([
        "➕ Agregar Producto",
        "✏️ Editar / Reabastecer Artículo",
        "⚙️ Opciones"
    ])

    # ----------------------------------------------------
    # TAB 1: AGREGAR NUEVO ARTÍCULO (Listo para el cliente)
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
                    st.success(f"✅ ¡Artículo '{desc_input}' agregado exitosamente con {stock_input} unidades a ${precio_input:,.2f}!")
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

    # ----------------------------------------------------
    # TAB 3: OPCIONES ADICIONALES
    # ----------------------------------------------------
    with tab_opciones:
        st.write("Administración de datos:")
        if st.button("🗑️ Vaciar todo el inventario"):
            vaciar_inventario()
            st.warning("Se ha vaciado el inventario.")
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
        st.info("💡 **El inventario está listo y vacío.** Tu cliente puede comenzar a dar de alta sus productos en la pestaña superior **➕ Agregar Producto**.")
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
    disponibles = df_art[df_art["cantidad_inventario"] > 0]

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
