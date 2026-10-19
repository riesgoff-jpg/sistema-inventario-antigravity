import sqlite3
from datetime import date, datetime
import pandas as pd
import streamlit as st

# ==============================================================================
# CONFIGURACIÓN DE PÁGINA (ANTIGRAVITY NATIVE INVENTORY SYSTEM)
# ==============================================================================
st.set_page_config(
    page_title="Sistema de Inventario - Antigravity",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilos CSS personalizados para una interfaz moderna, limpia y responsive
st.markdown(
    """
    <style>
    /* Estilo general */
    .main-title {
        font-size: 2rem;
        font-weight: 800;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .main-subtitle {
        font-size: 0.95rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    /* Tarjetas de métricas */
    div[data-testid="stMetric"] {
        background-color: rgba(59, 130, 246, 0.05);
        border: 1px solid rgba(59, 130, 246, 0.15);
        border-radius: 12px;
        padding: 12px 16px;
    }
    div[data-testid="stMetricValue"] {
        font-weight: 800;
        color: #1E3A8A;
    }
    /* Workflow Banner */
    .workflow-badge {
        background: linear-gradient(135deg, #10B981 0%, #059669 100%);
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
    }
    .workflow-box {
        background-color: #F8FAFC;
        border-left: 4px solid #3B82F6;
        padding: 12px 16px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

DB_PATH = "inventario_antigravity.db"

# ==============================================================================
# BASE DE DATOS (SQLite)
# Campos especificados:
# - descripción del artículo (descripcion)
# - precio del artículo (precio)
# - cantidad de inventario (cantidad_inventario)
# - cantidad que se vende (cantidad_vendida)
# - fecha de venta (fecha_venta)
# ==============================================================================
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Tabla del Catálogo de Artículos
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
        
        # Población inicial de prueba si la base de datos está vacía
        cursor.execute("SELECT COUNT(*) FROM articulos")
        if cursor.fetchone()[0] == 0:
            demo_items = [
                ("Laptop Ultra Slim 14'' Core i7", 12500.00, 15),
                ("Mouse Inalámbrico Ergonómico", 350.50, 40),
                ("Teclado Mecánico RGB Switch Blue", 890.00, 22),
                ("Monitor Curvo 27'' FHD 165Hz", 3800.00, 8),
                ("Cable USB-C de Carga Rápida 2m", 120.00, 50),
            ]
            cursor.executemany(
                "INSERT INTO articulos (descripcion, precio, cantidad_inventario) VALUES (?, ?, ?)",
                demo_items,
            )
        
        conn.commit()

init_db()

# ==============================================================================
# OPERACIONES Y FLUJO DE TRABAJO (ANTIGRAVITY WORKFLOW)
# ==============================================================================
def agregar_articulo(descripcion: str, precio: float, cantidad_inventario: int):
    """Registra un nuevo artículo en el catálogo de inventario."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO articulos (descripcion, precio, cantidad_inventario) VALUES (?, ?, ?)",
            (descripcion.strip(), round(precio, 2), int(cantidad_inventario)),
        )
        conn.commit()

def obtener_articulos():
    """Recupera todos los artículos del catálogo con su stock actual."""
    with get_connection() as conn:
        df = pd.read_sql_query(
            "SELECT id, descripcion, precio, cantidad_inventario, fecha_creacion FROM articulos ORDER BY id DESC",
            conn,
        )
        return df

def ejecutar_workflow_salida(articulo_id: int, cantidad_vendida: int, fecha_venta: date):
    """
    FLUJO DE TRABAJO EN ANTIGRAVITY:
    1. Verifica que el artículo exista y tenga stock suficiente.
    2. Resta automáticamente la 'cantidad_vendida' de la 'cantidad_inventario' actual.
    3. Registra la salida en la base de datos con la 'fecha_venta'.
    4. Garantiza atomicidad transaccional.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Paso 1: Consultar stock actual
        cursor.execute(
            "SELECT descripcion, precio, cantidad_inventario FROM articulos WHERE id = ?",
            (articulo_id,),
        )
        item = cursor.fetchone()
        if not item:
            return False, "❌ Error: El artículo seleccionado no existe."
            
        descripcion, precio, stock_actual = item
        
        # Paso 2: Validación de existencias
        if cantidad_vendida <= 0:
            return False, "❌ Error: La cantidad que se vende debe ser mayor a 0."
            
        if cantidad_vendida > stock_actual:
            return (
                False,
                f"❌ Stock insuficiente: Solo hay {stock_actual} unidades disponibles de '{descripcion}'.",
            )
            
        nuevo_stock = stock_actual - cantidad_vendida
        total = round(precio * cantidad_vendida, 2)
        
        # Paso 3: Resta automática del inventario (Workflow Action)
        cursor.execute(
            "UPDATE articulos SET cantidad_inventario = ? WHERE id = ?",
            (nuevo_stock, articulo_id),
        )
        
        # Paso 4: Registro de la venta con fecha_venta
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
    """Recupera el historial completo de salidas y ejecuciones del workflow."""
    with get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT 
                id AS 'Folio',
                fecha_venta AS 'Fecha de Venta',
                descripcion AS 'Descripción del Artículo',
                precio AS 'Precio ($)',
                cantidad_vendida AS 'Cant. Vendida',
                stock_previo AS 'Stock Previo',
                stock_resultante AS 'Stock Resultante',
                total AS 'Total ($)',
                timestamp AS 'Hora de Registro'
            FROM ventas
            ORDER BY id DESC
            """,
            conn,
        )
        return df

# ==============================================================================
# INTERFAZ DE USUARIO CON STREAMLIT
# ==============================================================================
st.markdown('<div class="main-title">📦 Sistema de Inventario Nativo</div>', unsafe_allow_html=True)
st.markdown('<div class="main-subtitle">Control de inventario reactivo y automatización de flujo de trabajo en Antigravity</div>', unsafe_allow_html=True)

# Barra lateral de navegación entre las dos vistas principales + auditoría
with st.sidebar:
    st.image("https://img.icons8.com/isometric/100/warehouse-1.png", width=80)
    st.header("Navegación")
    vista_seleccionada = st.radio(
        "Seleccione la vista:",
        ["🏷️ Catálogo de Productos", "🛒 Punto de Venta", "📜 Historial de Salidas"],
        index=0,
    )
    st.markdown("---")
    st.markdown(
        """
        **Regla del Workflow:**
        - Al registrar una venta:
          `cantidad_inventario = cantidad_inventario - cantidad_vendida`
        - Guarda `fecha_venta`.
        """
    )
    st.markdown("---")
    st.caption("⚡ Powered by Antigravity Agent Engine")

# ==============================================================================
# VISTA 1: CATÁLOGO PARA GESTIONAR PRODUCTOS
# ==============================================================================
if vista_seleccionada == "🏷️ Catálogo de Productos":
    st.header("🏷️ Catálogo de Productos")
    st.write("Gestiona la base de datos de artículos, precios e inventario disponible.")

    # Formulario para registrar nuevo producto
    with st.expander("➕ Registrar Nuevo Artículo en el Catálogo", expanded=False):
        with st.form("form_alta_producto", clear_on_submit=True):
            col_d, col_p, col_c = st.columns([3, 2, 2])
            with col_d:
                desc_input = st.text_input("Descripción del artículo *", placeholder="Ej: Monitor LED 24''")
            with col_p:
                precio_input = st.number_input("Precio del artículo ($) *", min_value=0.01, step=1.0, value=150.00, format="%.2f")
            with col_c:
                stock_input = st.number_input("Cantidad de inventario *", min_value=0, step=1, value=10)
            
            submit_producto = st.form_submit_button("💾 Guardar Artículo en Catálogo")
            if submit_producto:
                if not desc_input.strip():
                    st.error("Por favor ingresa una descripción para el artículo.")
                else:
                    agregar_articulo(desc_input, precio_input, stock_input)
                    st.success(f"✅ Artículo '{desc_input}' agregado correctamente con {stock_input} unidades a ${precio_input:,.2f}.")
                    st.rerun()

    # Métricas del Catálogo
    df_art = obtener_articulos()
    total_articulos = len(df_art)
    total_stock_unidades = int(df_art["cantidad_inventario"].sum()) if not df_art.empty else 0
    valor_inventario = (df_art["precio"] * df_art["cantidad_inventario"]).sum() if not df_art.empty else 0.0

    m1, m2, m3 = st.columns(3)
    m1.metric("Total de Artículos", f"{total_articulos} productos")
    m2.metric("Inventario en Stock", f"{total_stock_unidades} unidades")
    m3.metric("Valor del Inventario", f"${valor_inventario:,.2f}")

    st.markdown("### 📋 Artículos Registrados en el Sistema")

    if df_art.empty:
        st.info("No hay productos registrados en el catálogo. Utiliza el formulario superior para añadir artículos.")
    else:
        # Buscador en tiempo real
        c_search, c_filter = st.columns([3, 1])
        with c_search:
            busqueda = st.text_input("🔍 Buscar artículo por descripción:", placeholder="Escribe para filtrar...")
        with c_filter:
            solo_stock_bajo = st.checkbox("⚠️ Ver solo stock bajo (≤ 5)", value=False)

        df_filtrado = df_art.copy()
        if busqueda:
            df_filtrado = df_filtrado[df_filtrado["descripcion"].str.contains(busqueda, case=False, na=False)]
        if solo_stock_bajo:
            df_filtrado = df_filtrado[df_filtrado["cantidad_inventario"] <= 5]

        # Presentación en tabla amigable
        df_display = df_filtrado.rename(
            columns={
                "id": "ID",
                "descripcion": "Descripción del Artículo",
                "precio": "Precio del Artículo ($)",
                "cantidad_inventario": "Cantidad de Inventario",
                "fecha_creacion": "Fecha de Registro",
            }
        )

        st.dataframe(
            df_display.style.format({
                "Precio del Artículo ($)": "${:,.2f}",
                "Cantidad de Inventario": "{:d} unid."
            }),
            use_container_width=True,
            hide_index=True,
        )

# ==============================================================================
# VISTA 2: PUNTO DE VENTA (REGISTRO DE SALIDAS Y FLUJO DE TRABAJO)
# ==============================================================================
elif vista_seleccionada == "🛒 Punto de Venta":
    st.header("🛒 Punto de Venta")
    st.write("Registra salidas y ventas de mercancía. El workflow deducirá automáticamente el stock y guardará la fecha.")

    df_art = obtener_articulos()
    disponibles = df_art[df_art["cantidad_inventario"] > 0]

    if disponibles.empty:
        st.warning("⚠️ No hay productos con inventario disponible para vender. Ingresa artículos o aumenta el stock en el **Catálogo**.")
    else:
        col_form, col_ticket = st.columns([3, 2])

        with col_form:
            st.markdown(
                """
                <div class="workflow-box">
                    <strong>⚙️ Flujo de Trabajo en Antigravity:</strong><br>
                    Al presionar <em>'Registrar Salida / Venta'</em>, el sistema ejecuta la resta automática:
                    <code>Inventario Final = Inventario Actual - Cantidad que se vende</code>
                    y almacena de forma inmutable la <strong>Fecha de Venta</strong>.
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Diccionario de opciones para selector
            dict_opciones = {
                f"{row['descripcion']} (Stock: {row['cantidad_inventario']} | ${row['precio']:,.2f})": row["id"]
                for _, row in disponibles.iterrows()
            }

            with st.form("form_punto_de_venta"):
                item_seleccionado_label = st.selectbox(
                    "Selecciona el artículo a vender *",
                    options=list(dict_opciones.keys()),
                )
                articulo_id = dict_opciones[item_seleccionado_label]
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

                btn_registrar_salida = st.form_submit_button("⚡ Registrar Salida / Venta", type="primary", use_container_width=True)

                if btn_registrar_salida:
                    exito, detalle = ejecutar_workflow_salida(articulo_id, cant_vender, fecha_sel)
                    if exito:
                        st.success(
                            f"✅ **¡Venta y Salida Registrada Exitosamente!**  \n"
                            f"• **Artículo:** {detalle['descripcion']}  \n"
                            f"• **Cantidad vendida:** {detalle['cantidad_vendida']} unid.  \n"
                            f"• **Stock:** {detalle['stock_previo']} → **{detalle['nuevo_stock']}**  \n"
                            f"• **Fecha de venta:** {detalle['fecha_venta']}  \n"
                            f"• **Total cobrado:** ${detalle['total']:,.2f}"
                        )
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(detalle)

        with col_ticket:
            st.markdown("### 🧾 Resumen de la Operación")
            subtotal_estimado = cant_vender * precio_unitario
            stock_remanente = stock_maximo - cant_vender

            st.markdown(
                f"""
                - **Artículo seleccionado:** `{descripcion_sel}`
                - **Precio unitario:** `${precio_unitario:,.2f}`
                - **Stock en inventario:** `{stock_maximo}` unid.
                - **Cantidad a descontar:** `{cant_vender}` unid.
                - **Stock proyectado tras la salida:** **`{stock_remanente}`** unid.
                - **Fecha asignada:** `{fecha_sel}`
                ---
                ### Total a Liquidar:
                # `${subtotal_estimado:,.2f}`
                """
            )

# ==============================================================================
# VISTA 3: AUDITORÍA Y HISTORIAL DE SALIDAS (LOGS DEL WORKFLOW)
# ==============================================================================
elif vista_seleccionada == "📜 Historial de Salidas":
    st.header("📜 Historial de Salidas & Ejecución de Workflows")
    st.write("Registro transaccional de todas las salidas efectuadas con fecha y deducciones automáticas.")

    df_historial = obtener_historial_ventas()

    if df_historial.empty:
        st.info("Aún no se han registrado salidas en el sistema.")
    else:
        total_acumulado = df_historial["Total ($)"].sum()
        total_unidades = int(df_historial["Cant. Vendida"].sum())
        total_transacciones = len(df_historial)

        c1, c2, c3 = st.columns(3)
        c1.metric("Ventas Acumuladas", f"${total_acumulado:,.2f}")
        c2.metric("Unidades Despachadas", f"{total_unidades} unid.")
        c3.metric("Transacciones Ejecutadas", f"{total_transacciones}")

        st.dataframe(
            df_historial.style.format({
                "Precio ($)": "${:,.2f}",
                "Total ($)": "${:,.2f}",
                "Cant. Vendida": "{:d} unid.",
                "Stock Previo": "{:d}",
                "Stock Resultante": "{:d}",
            }),
            use_container_width=True,
            hide_index=True,
        )
