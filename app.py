import streamlit as st
import pandas as pd
import io
import re
import os

# Configuración de página
st.set_page_config(
    page_title="Mesa de Homologación AGC",
    page_icon="⚙️",
    layout="wide"
)

st.title("⚙️ Agro Industrial Center (AGC) - Portal de Homologación")
st.markdown("Herramienta web comercial: Homologa solicitudes de repuestos, calcula intervalos de confianza y genera la plantilla oficial **FR-053 v02**.")

# -------------------------------------------------------------
# 1. Funciones de Carga Robusta y Normalización
# -------------------------------------------------------------
def asegurar_columnas_unicas(columnas):
    """Evita el error de PyArrow 'Duplicate column names found' garantizando unicidad absoluta."""
    vistas = {}
    unicas = []
    for col in columnas:
        c = str(col).strip()
        if c in vistas:
            vistas[c] += 1
            unicas.append(f"{c}_{vistas[c]}")
        else:
            vistas[c] = 0
            unicas.append(c)
    return unicas

def normalizar_df(df):
    """Limpia nombres de columnas y garantiza que sean únicos."""
    df.columns = [str(c).replace('\ufeff', '').replace('ï»¿', '').strip() for c in df.columns]
    df.columns = asegurar_columnas_unicas(df.columns)
    return df

def leer_archivo_cualquiera(fuente):
    """Lee CSV (cualquier separador/codificación) o Excel (.xlsx/.xls)."""
    # Si es bytes o uploaded file
    es_excel = False
    if hasattr(fuente, "name"):
        if fuente.name.lower().endswith((".xlsx", ".xls")):
            es_excel = True
    elif isinstance(fuente, str) and fuente.lower().endswith((".xlsx", ".xls")):
        es_excel = True

    if es_excel:
        df = pd.read_excel(fuente)
        return normalizar_df(df)

    # Si es CSV, detectar codificación y delimitador
    if hasattr(fuente, "seek"):
        fuente.seek(0)
    
    delimitadores = [';', ',', '\t']
    encodings = ['utf-8-sig', 'latin1', 'cp1252', 'utf-8']
    
    for enc in encodings:
        for sep in delimitadores:
            try:
                if hasattr(fuente, "seek"):
                    fuente.seek(0)
                df = pd.read_csv(fuente, sep=sep, encoding=enc, engine='python')
                if len(df.columns) > 1 and len(df) > 0:
                    return normalizar_df(df)
            except Exception:
                continue

    # Fallback genérico
    if hasattr(fuente, "seek"):
        fuente.seek(0)
    df = pd.read_csv(fuente, sep=None, engine='python')
    return normalizar_df(df)

def normalizar_columnas_cliente(df):
    """Mapea con seguridad las columnas del cliente sin duplicar 'PRODUCTO'."""
    cols_orig = list(df.columns)
    mapping = {}
    asignados = set()

    for c in cols_orig:
        c_upper = str(c).upper().strip()
        if any(k in c_upper for k in ["NUMERO DE PARTE", "P/N", "PART NO", "PARTE", "CODIGO"]):
            if "NUMERO DE PARTE" not in asignados:
                mapping[c] = "NUMERO DE PARTE"
                asignados.add("NUMERO DE PARTE")
                continue
        if any(k in c_upper for k in ["CANTIDAD", "QTY", "CANT", "SOLICITADA"]):
            if "CANTIDAD SOLICITADA" not in asignados:
                mapping[c] = "CANTIDAD SOLICITADA"
                asignados.add("CANTIDAD SOLICITADA")
                continue
        if any(k in c_upper for k in ["MAQUINA", "EQUIPO", "MACHINE"]):
            if "MAQUINA" not in asignados:
                mapping[c] = "MAQUINA"
                asignados.add("MAQUINA")
                continue
        if c_upper in ["ITEM", "POS", "POSICION", "NO", "NO.", "#"]:
            if "ITEM" not in asignados:
                mapping[c] = "ITEM"
                asignados.add("ITEM")
                continue
        if any(k in c_upper for k in ["PRODUCTO", "DESCRIPCION", "DESCRIPTION", "REPUESTO", "ARTICULO"]):
            if "PRODUCTO" not in asignados:
                mapping[c] = "PRODUCTO"
                asignados.add("PRODUCTO")
                continue
        mapping[c] = c

    df_renombrado = df.rename(columns=mapping)
    df_renombrado.columns = asegurar_columnas_unicas(df_renombrado.columns)
    return df_renombrado

# -------------------------------------------------------------
# 2. Carga del Catálogo Maestro AGC
# -------------------------------------------------------------
@st.cache_data
def cargar_catalogo_maestro():
    posibles_rutas = [
        "CATALOGO_AGC.csv", "CATALOGO AGC.csv", "catalogo_agc.csv", "catalogo agc.csv",
        "../CATALOGO_AGC.csv", "/workspace/knowledge/CATALOGO_AGC.csv"
    ]
    for ruta in posibles_rutas:
        if os.path.exists(ruta):
            try:
                df = leer_archivo_cualquiera(ruta)
                # Normalizar columnas del catálogo
                cols_cat = {}
                for col in df.columns:
                    cu = col.upper()
                    if "DESC" in cu: cols_cat[col] = "DESCRIPCION AGC"
                    elif "SEG" in cu: cols_cat[col] = "SEGMENTO"
                    elif "MAR" in cu: cols_cat[col] = "MARCA"
                    elif "MOD" in cu: cols_cat[col] = "MODELO"
                df = df.rename(columns=cols_cat)
                if "DESCRIPCION AGC" in df.columns:
                    return df
            except Exception:
                continue
    return None

df_cat = cargar_catalogo_maestro()

# Barra lateral
with st.sidebar:
    st.header("⚙️ Configuración")
    if df_cat is not None:
        st.success(f"Catálogo cargado: {len(df_cat):,} referencias.")
    else:
        st.error("⚠️ No se encontró CATALOGO_AGC.csv en la carpeta.")
        cat_subido = st.file_uploader("Subir Catálogo AGC manualmente (.csv o .xlsx)", type=["csv", "xlsx", "xls"])
        if cat_subido is not None:
            df_cat = leer_archivo_cualquiera(cat_subido)
            st.success(f"Catálogo cargado: {len(df_cat):,} referencias.")

    st.markdown("---")
    st.header("👤 Datos de Gestión Comercial")
    vendedor = st.text_input("Vendedor", value="Ejecutivo Comercial AGC")
    cliente = st.text_input("Cliente", placeholder="Ej: Extractora San Fernando")
    area = st.selectbox("Área de Proceso", ["Extracción / Prensas", "Clarificación", "Palmistería", "Calderas", "Cosecha y Campo"])
    st.markdown("---")
    st.caption("Norma: RFQ FR-053 v02")

# -------------------------------------------------------------
# 3. Motor de Homologación Bilingüe e Intervalos de Confianza
# -------------------------------------------------------------
def homologar_item(row, catalogo):
    pn_raw = str(row.get("NUMERO DE PARTE", "")).strip()
    maq_raw = str(row.get("MAQUINA", "")).strip()
    prod_raw = str(row.get("PRODUCTO", "")).strip()

    maq_upper = maq_raw.upper()
    prod_upper = prod_raw.upper()

    pn = pn_raw
    if pn.lower() in ["nan", "#ref!", "none", "s/n", "-", "0", "null", ""]:
        pn = ""

    # A) BUSQUEDA POR P/N
    if pn:
        pn_clean = re.sub(r"\s+", "", pn)
        variantes = [pn_clean]
        if "." in pn_clean: variantes.append(pn_clean.replace(".", ","))
        if "," in pn_clean: variantes.append(pn_clean.replace(",", "."))
        variantes = list(set(variantes))

        patron_pn = re.compile(rf"(?:P/N|NO\.?|ITEM|PART)?\s*(?:{'|'.join(re.escape(v) for v in variantes)})(?:[^0-9A-Za-z]|$)", re.IGNORECASE)
        coincidencias = catalogo[catalogo["DESCRIPCION AGC"].astype(str).apply(lambda x: bool(patron_pn.search(x)))]

        if len(coincidencias) > 0:
            # Desambiguación por máquina / marca
            sub = coincidencias
            if "KWY" in maq_upper:
                k = coincidencias[coincidencias["MARCA"].str.contains("KWY", na=False, case=False)]
                if len(k) > 0: sub = k
            elif "GS P2" in maq_upper or "GS P2-25" in maq_upper:
                k = coincidencias[coincidencias["MODELO"].str.contains("GS|P2", na=False, case=False)]
                if len(k) > 0: sub = k
            elif "SWECO" in maq_upper or "TAMIZ" in maq_upper:
                k = coincidencias[coincidencias["MARCA"].str.contains("SWECO", na=False, case=False)]
                if len(k) > 0: sub = k
            elif "KEW" in maq_upper or "SEK" in maq_upper:
                k = coincidencias[coincidencias["MARCA"].str.contains("KEW", na=False, case=False)]
                if len(k) > 0: sub = k

            top = sub.iloc[0]
            desc = str(top["DESCRIPCION AGC"])
            m_man = re.search(r"\((.*?)\)", desc)
            desc_man = m_man.group(1) if m_man else desc

            if len(sub) == 1:
                return desc, top["SEGMENTO"], top["MARCA"], top["MODELO"], desc_man, "🟢 ALTA (100%)", "Coincidencia exacta de P/N y Modelo", "HOMOLOGADO"
            else:
                return desc, top["SEGMENTO"], top["MARCA"], top["MODELO"], desc_man, "🟡 MEDIA (80%)", f"P/N compartido ({len(sub)} variantes en modelo)", "CONFIRMAR VARIANTE"

    # B) BUSQUEDA BILINGÜE Y DIMENSIONAL (Ej. Cosecha, Bombas, Prensas en Español)
    # 1. Tubos de Aluminio / Varas de Cosecha (Aluminium Harvesting Pole)
    if any(k in prod_upper for k in ["TUBO", "ALUMINIO", "VARA", "COSECHA", "POLE", "HARVESTING"]):
        nums = re.findall(r"(\d+(?:[\.,]\d+)?)", prod_raw)
        sub_poles = catalogo[catalogo["DESCRIPCION AGC"].str.contains("HarvestingPole|AluminiumHarvesting", case=False, na=False)]
        
        candidatos = sub_poles
        # Cotejar cotas (ej: 38mm, 2.2mm, 30ft / 9m / 10m)
        if "38" in prod_raw:
            c38 = candidatos[candidatos["DESCRIPCION AGC"].str.contains("38mm", case=False, na=False)]
            if len(c38) > 0: candidatos = c38
        if "2.2" in prod_raw or "2,2" in prod_raw:
            c22 = candidatos[candidatos["DESCRIPCION AGC"].str.contains("2,2mm|2.2mm", case=False, na=False)]
            if len(c22) > 0: candidatos = c22
        if "30FT" in prod_upper or "30 FT" in prod_upper or "10M" in prod_upper or "9M" in prod_upper:
            c10 = candidatos[candidatos["DESCRIPCION AGC"].str.contains("10m|9m", case=False, na=False)]
            if len(c10) > 0: candidatos = c10

        if len(candidatos) > 0:
            top = candidatos.iloc[0]
            desc = str(top["DESCRIPCION AGC"])
            m_man = re.search(r"\((.*?)\)", desc)
            desc_man = m_man.group(1) if m_man else desc
            conf = "🟢 ALTA (95%)" if len(candidatos) <= 3 else "🟡 MEDIA (75%)"
            return desc, top["SEGMENTO"], top["MARCA"], top["MODELO"], desc_man, conf, "Homologación dimensional bilingüe (Español -> English AGC)", "HOMOLOGADO"

    # 2. Cuchillas / Cinceles de Cosecha
    if any(k in prod_upper for k in ["CUCHILLA", "CHISEL", "CINSEL", "M222"]):
        sub_kn = catalogo[catalogo["DESCRIPCION AGC"].str.contains("KnifeHarvesting|HarvestingChisel", case=False, na=False)]
        for pat in ["M222A", "M222B", "M222C", "M222-L", "2\"", "3\"", "4\"", "5\""]:
            if pat in prod_upper:
                m = sub_kn[sub_kn["DESCRIPCION AGC"].str.contains(pat, case=False, na=False)]
                if len(m) > 0:
                    top = m.iloc[0]
                    desc = str(top["DESCRIPCION AGC"])
                    return desc, top["SEGMENTO"], top["MARCA"], top["MODELO"], desc, "🟢 ALTA (90%)", "Homologación herramienta de cosecha", "HOMOLOGADO"

    # C) SUGERENCIA POR PALABRAS CLAVE DEL EQUIPO
    if maq_upper:
        tokens = [t for t in re.split(r"[^A-Za-z0-9]", prod_upper) if len(t) >= 4 and t not in ["PARA", "CON", "ESTANDAR", "LARGO", "ACERO"]]
        if len(tokens) >= 2:
            query = f"(?=.*{tokens[0]})(?=.*{tokens[1]})"
            sub_text = catalogo[catalogo["DESCRIPCION AGC"].str.contains(query, regex=True, case=False, na=False)]
            if len(sub_text) > 0 and len(sub_text) <= 5:
                top = sub_text.iloc[0]
                desc = str(top["DESCRIPCION AGC"])
                return desc, top["SEGMENTO"], top["MARCA"], top["MODELO"], desc, "🟠 SUGERIDO (40%)", "Coincidencia por descripción textual", "SUGERENCIA"

    # D) POR HOMOLOGAR EN PLANO
    return (
        "POR HOMOLOGAR EN PLANO",
        "CPO",
        "AGC",
        "ESTÁNDAR",
        f"{prod_raw} (P/N: {pn_raw})",
        "🔴 REVISIÓN MANUAL (0%)",
        "Sin P/N unívoco o pieza especial (Requiere consultar plano técnico)",
        "REVISIÓN MANUAL"
    )

# -------------------------------------------------------------
# 4. Interfaz de Usuario y Procesamiento
# -------------------------------------------------------------
archivo_subido = st.file_uploader(
    "📂 Arrastra la Solicitud del Cliente (CSV o Excel .xlsx / .xls)",
    type=["csv", "xlsx", "xls"]
)

if archivo_subido is not None and df_cat is not None:
    try:
        df_cliente = leer_archivo_cualquiera(archivo_subido)
        df_cliente = normalizar_columnas_cliente(df_cliente)
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")
        df_cliente = None

    if df_cliente is not None:
        st.subheader(f"📋 Solicitud cargada ({len(df_cliente)} ítems detectados)")
        st.dataframe(df_cliente.head(4), use_container_width=True)

        if st.button("🚀 Homologar Lote y Calcular Intervalos de Confianza", type="primary"):
            with st.spinner("Homologando lote con motor bilingüe y auditoría de confianza..."):
                filas_salida = []
                for idx, r in df_cliente.iterrows():
                    desc, seg, brand, mod, man_desc, conf, crit, stt = homologar_item(r, df_cat)
                    filas_salida.append({
                        "ITEM": r.get("ITEM", idx + 1),
                        "CONFIANZA": conf,
                        "CRITERIO": crit,
                        "DESCRIPTION": desc,
                        "SEGMENT": seg,
                        "BRAND": brand,
                        "MODEL": mod,
                        "U/M": "UN",
                        "QUANTITY": r.get("CANTIDAD SOLICITADA", 1),
                        "OBSERVATIONS-DESCRIPCION CLIENTE": f"{r.get('PRODUCTO', '')} | P/N: {r.get('NUMERO DE PARTE', '')} | Máq: {r.get('MAQUINA', '')}",
                        "DESCRIPCION MANUALES": man_desc,
                        "ESTADO": stt
                    })

                df_salida = pd.DataFrame(filas_salida)
                st.session_state["df_salida"] = df_salida

        # Si ya se homologó, mostrar resultados y métricas
        if "df_salida" in st.session_state:
            df_res = st.session_state["df_salida"]

            total_items = len(df_res)
            alta = len(df_res[df_res["CONFIANZA"].str.contains("ALTA", na=False)])
            media = len(df_res[df_res["CONFIANZA"].str.contains("MEDIA", na=False)])
            sug = len(df_res[df_res["CONFIANZA"].str.contains("SUGERIDO", na=False)])
            revisar = len(df_res[df_res["CONFIANZA"].str.contains("REVISIÓN MANUAL", na=False)])

            st.markdown("---")
            st.subheader("📊 Intervalos de Confianza Comercial")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🟢 Alta Confianza (90-100%)", f"{alta} ({alta/total_items:.1%})", "Listo para cotizar")
            c2.metric("🟡 Confianza Media (70-80%)", f"{media} ({media/total_items:.1%})", "Confirmar variante")
            c3.metric("🟠 Sugeridos (40%)", f"{sug} ({sug/total_items:.1%})", "Revisión sugerida")
            c4.metric("🔴 Requieren Plano (0%)", f"{revisar} ({revisar/total_items:.1%})", "Verificar en despiece")

            # Filtro dinámico
            filtro = st.radio(
                "Filtrar vista:",
                ["Todos los ítems", "🟢 Solo Alta Confianza", "🟡 Solo Media Confianza", "🔴 Solo Requieren Plano"],
                horizontal=True
            )

            df_mostrar = df_res
            if filtro == "🟢 Solo Alta Confianza":
                df_mostrar = df_res[df_res["CONFIANZA"].str.contains("ALTA", na=False)]
            elif filtro == "🟡 Solo Media Confianza":
                df_mostrar = df_res[df_res["CONFIANZA"].str.contains("MEDIA", na=False)]
            elif filtro == "🔴 Solo Requieren Plano":
                df_mostrar = df_res[df_res["CONFIANZA"].str.contains("REVISIÓN MANUAL", na=False)]

            st.dataframe(df_mostrar, use_container_width=True)

            # Construir el CSV oficial con Encabezado FR-053 e INCLUYENDO Confianza y Criterio
            encabezado_oficial = (
                ";;;;;;;;;;;;;;;;;;;;;;;;;;;;;\n"
                ";REQUEST FOR QUOTATION;;;;;;;\"Código: FR-053\\nVersión:02\\nFecha:11/12/2025\";;;;;;;;;;;;;;;;;;;;;\n"
                f";CUSTOMER;{cliente};;;CUSTOMER CODE;;DOCUMENT;RFQ-2026-FR053;;;;;;;;;;;;;;;;;;;\n"
                f";CONTACT;{vendedor};;;#N/D;;;;;;;;;;;;;;;;;;;;;;\n"
                f";POSITION;Ventas;;;AREA;{area};DATE;25/11/2026;;;;;;;;;;;;;;;;;;;\n"
                ";EMAIL;;;;#N/D;;;;;;;;;;;;;;;;;;;;;;;;\n"
                ";PHONE;;;;LINE;INCOTERM;CAMPAING;;;;;;;;;;;;;;;;;;;;;;\n"
                ";UBICATION;;;;Industrial;EXW;FID;;;;;;;;;;;;;;;;;;;;;;\n"
                ";;;;;;;;;;;;;;;;;;;;;;;;;;;;;\n"
            )

            buffer_csv = io.StringIO()
            buffer_csv.write(encabezado_oficial)
            df_res.to_csv(buffer_csv, sep=";", index=False)

            st.download_button(
                label="📥 Descargar RFQ FR-053 Completo (.csv con Intervalo de Confianza)",
                data=buffer_csv.getvalue().encode("latin1", errors="replace"),
                file_name=f"RFQ_FR053_{cliente.replace(' ', '_') or 'HOMOLOGADO'}.csv",
                mime="text/csv",
                type="primary"
            )
