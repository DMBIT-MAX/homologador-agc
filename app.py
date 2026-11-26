import streamlit as st
import pandas as pd
import io
import re
import os
import glob

# Configuración de página
st.set_page_config(
    page_title="Mesa de Homologación AGC",
    page_icon="⚙️",
    layout="wide"
)

st.title("⚙️ Agro Industrial Center (AGC) - Portal de Homologación")
st.markdown("Herramienta comercial para ventas: Homologa solicitudes de repuestos multiformato y genera el formato oficial **FR-053 v02**.")

# Función universal de lectura para archivos CSV / Excel
def leer_archivo_inteligente(origen):
    if isinstance(origen, str):
        if not os.path.exists(origen):
            raise FileNotFoundError(f"No existe: {origen}")
        with open(origen, "rb") as f:
            header = f.read(4)
        if header.startswith(b"PK\x03\x04") or origen.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(origen)
        else:
            for enc in ["utf-8-sig", "latin1", "cp1252", "utf-8"]:
                try:
                    df = pd.read_csv(origen, sep=None, engine="python", encoding=enc)
                    break
                except Exception:
                    continue
            else:
                df = pd.read_csv(origen, encoding="latin1")
    else:
        # Buffer de Streamlit
        nombre = getattr(origen, "name", "").lower()
        contenido = origen.read()
        origen.seek(0)
        if contenido.startswith(b"PK\x03\x04") or nombre.endswith((".xlsx", ".xls")):
            df = pd.read_excel(origen)
        else:
            for enc in ["utf-8-sig", "latin1", "cp1252", "utf-8"]:
                try:
                    df = pd.read_csv(io.BytesIO(contenido), sep=None, engine="python", encoding=enc)
                    break
                except Exception:
                    continue
            else:
                df = pd.read_csv(io.BytesIO(contenido), encoding="latin1")

    # Limpieza de nombres de columnas
    df.columns = [str(c).strip().replace("\ufeff", "").replace("ï»¿", "") for c in df.columns]
    return df

# Normalizar columnas del catálogo
def preparar_catalogo(df):
    col_map = {}
    for c in df.columns:
        c_up = c.upper()
        if "DESCRIP" in c_up or "ITEM" in c_up or "PARTE" in c_up or "CODE" in c_up:
            if "DESCRIPCION AGC" not in col_map.values():
                col_map[c] = "DESCRIPCION AGC"
        elif "SEGMENT" in c_up:
            col_map[c] = "SEGMENTO"
        elif "MARCA" in c_up or "BRAND" in c_up:
            col_map[c] = "MARCA"
        elif "MODEL" in c_up:
            col_map[c] = "MODELO"

    df = df.rename(columns=col_map)
    if "DESCRIPCION AGC" not in df.columns and len(df.columns) > 0:
        df = df.rename(columns={df.columns[0]: "DESCRIPCION AGC"})
    for req in ["SEGMENTO", "MARCA", "MODELO"]:
        if req not in df.columns:
            df[req] = "AGC"
    return df

# Cargar catálogo maestro buscando variantes de archivo
@st.cache_data
def buscar_y_cargar_catalogo():
    rutas_probables = [
        "CATALOGO_AGC.csv.xlsx",
        "CATALOGO_AGC.xlsx",
        "CATALOGO_AGC.csv",
        "CATALOGO AGC.csv",
        "CATALOGO AGC.xlsx",
        "catalogo_agc.xlsx",
        "catalogo_agc.csv",
        "catalogo.xlsx",
        "catalogo.csv"
    ]
    # Buscar también en carpeta actual
    for r in rutas_probables:
        if os.path.exists(r):
            df = leer_archivo_inteligente(r)
            return preparar_catalogo(df), r

    archivos_locales = glob.glob("*CATALOGO*") + glob.glob("*catalogo*") + glob.glob("*.xlsx") + glob.glob("*.csv")
    for r in archivos_locales:
        if "CLIENTE" not in r.upper() and "FR053" not in r.upper():
            try:
                df = leer_archivo_inteligente(r)
                if len(df) > 100:  # Es un catálogo maestro
                    return preparar_catalogo(df), r
            except Exception:
                continue

    return None, None

df_cat = None
nombre_cat = None

try:
    df_cat, nombre_cat = buscar_y_cargar_catalogo()
except Exception:
    df_cat = None

# Barra lateral
with st.sidebar:
    st.header("⚙️ Configuración y Catálogo")
    if df_cat is not None:
        st.success(f"✅ Catálogo cargado: {len(df_cat):,} referencias.")
        st.caption(f"Archivo: `{os.path.basename(nombre_cat)}`")
    else:
        st.warning("⚠️ No se detectó automáticamente el catálogo en la carpeta.")
        cat_subido = st.file_uploader("📂 Sube aquí el Catálogo Maestro AGC (.xlsx o .csv):", type=["xlsx", "xls", "csv"])
        if cat_subido is not None:
            try:
                df_cat = preparar_catalogo(leer_archivo_inteligente(cat_subido))
                st.success(f"✅ Catálogo cargado: {len(df_cat):,} referencias.")
            except Exception as e:
                st.error(f"Error al leer catálogo: {e}")

    st.markdown("---")
    st.header("👤 Datos Comerciales")
    vendedor = st.text_input("Vendedor", value="Ejecutivo Comercial")
    cliente = st.text_input("Cliente", placeholder="Ej: Extractora San Fernando")
    area = st.selectbox("Área de Proceso", ["Extracción / Prensas", "Clarificación", "Palmistería", "Calderas"])
    st.caption("Formato normativo: RFQ FR-053 v02")

# Diccionario técnico bilingüe
TRADUCCIONES = {
    r"\btubo\b|\bvara\b|\bpertiga\b": "pole",
    r"\baluminio\b": "aluminium",
    r"\bcosecha\b": "harvesting",
    r"\bcuchilla\b": "knife",
    r"\bcincel\b": "chisel",
    r"\bchumacera\b|\bcaja\s+de\s+rodamiento\b": "bearing housing",
    r"\bsinfin\b|\btornillo\b": "worm screw",
    r"\bcono\b": "cone",
    r"\btamiz\b|\bmalla\b": "screen",
    r"\bseparador\b": "separator",
    r"\bbomba\b": "pump",
    r"\bcentrifuga\b": "centrifugal",
    r"\beje\b": "shaft"
}

def traducir_espanol_ingles(texto):
    t = texto.lower()
    for es_pat, en_word in TRADUCCIONES.items():
        t = re.sub(es_pat, en_word, t)
    return t

def extraer_dimensiones(texto):
    texto = texto.replace(",", ".")
    dims = set()
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:ft|pies|\')", texto, re.IGNORECASE):
        ft = float(m.group(1))
        dims.add(f"{round(ft * 0.3048)}m")
        dims.add(f"{m.group(1)}ft")
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:mm|m\b|\")", texto, re.IGNORECASE):
        dims.add(m.group(1))
    for m in re.finditer(r"\b(\d{2,4})\b", texto):
        dims.add(m.group(1))
    return dims

def normalizar_pn(pn_str):
    if not pn_str or str(pn_str).lower() in ["nan", "none", "#ref!", "s/n", "sn", "-"]:
        return ""
    pn_limpio = str(pn_str).strip()
    return re.sub(r"\s+", "", pn_limpio)

def homologar_item(row, catalogo):
    pn_raw = str(row.get("NUMERO DE PARTE", "")).strip()
    maq_raw = str(row.get("MAQUINA", "")).strip().upper()
    prod_raw = str(row.get("PRODUCTO", "")).strip()

    pn = normalizar_pn(pn_raw)

    if pn:
        pn_regex_variantes = [
            re.escape(pn),
            re.escape(pn.replace(".", ",")),
            re.escape(pn.replace(",", "."))
        ]
        patron_str = rf"(?:P/N|NO\.?|ITEM|PART)?\s*(?:{'|'.join(set(pn_regex_variantes))})(?:[^0-9A-Z]|$)"
        patron = re.compile(patron_str, re.IGNORECASE)

        coincidencias = catalogo[catalogo["DESCRIPCION AGC"].astype(str).apply(lambda x: bool(patron.search(x)))]

        if len(coincidencias) > 0:
            if len(coincidencias) > 1 and maq_raw:
                if "KWY" in maq_raw:
                    sub = coincidencias[coincidencias["MARCA"].str.contains("KWY", na=False, case=False)]
                    if len(sub) > 0: coincidencias = sub
                elif "GS P2-25" in maq_raw or "GS" in maq_raw:
                    sub = coincidencias[coincidencias["MODELO"].str.contains("GS|P2", na=False, case=False)]
                    if len(sub) > 0: coincidencias = sub
                elif "SWECO" in maq_raw or "TAMIZ" in maq_raw:
                    sub = coincidencias[coincidencias["MARCA"].str.contains("SWECO", na=False, case=False)]
                    if len(sub) > 0: coincidencias = sub
                elif "KEW" in maq_raw or "SEK" in maq_raw:
                    sub = coincidencias[coincidencias["MARCA"].str.contains("KEWPUMP|KEW", na=False, case=False)]
                    if len(sub) > 0: coincidencias = sub

            top = coincidencias.iloc[0]
            desc = str(top["DESCRIPCION AGC"])
            m_man = re.search(r"\((.*?)\)", desc)
            desc_manual = m_man.group(1) if m_man else desc

            if len(coincidencias) == 1:
                return desc, top["SEGMENTO"], top["MARCA"], top["MODELO"], desc_manual, "🟢 ALTA (100%)", "Coincidencia exacta de P/N sin ambigüedad"
            else:
                return desc, top["SEGMENTO"], top["MARCA"], top["MODELO"], desc_manual, "🟡 MEDIA (80%)", f"P/N compartido ({len(coincidencias)} variantes de modelo/medida)"

    # Intento 2: Traducción bilingüe + cotas dimensionales
    texto_busqueda = f"{prod_raw} {pn_raw}"
    traducido = traducir_espanol_ingles(texto_busqueda)
    palabras = [w for w in re.findall(r"[a-zA-Z]{3,}", traducido) if w not in ["para", "con", "del", "los", "the", "and", "c/w"]]
    dims = extraer_dimensiones(texto_busqueda)

    if palabras or dims:
        def puntuar(desc_agc):
            desc_l = str(desc_agc).lower()
            pts = 0
            for p in palabras:
                if p in desc_l: pts += 2
            for d in dims:
                if d.lower() in desc_l: pts += 3
            return pts

        scores = catalogo["DESCRIPCION AGC"].apply(puntuar)
        max_score = scores.max()
        if max_score >= 5:
            top = catalogo.iloc[scores.argmax()]
            desc = str(top["DESCRIPCION AGC"])
            m_man = re.search(r"\((.*?)\)", desc)
            desc_manual = m_man.group(1) if m_man else desc
            conf = "🟢 ALTA (95%)" if max_score >= 8 else "🟠 SUGERIDO (40%)"
            crit = "Homologación por traducción técnica y medidas" if max_score >= 8 else "Sugerido por similitud de texto"
            return desc, top["SEGMENTO"], top["MARCA"], top["MODELO"], desc_manual, conf, crit

    return "POR HOMOLOGAR EN PLANO", "CPO", "AGC", "ESTÁNDAR", f"{prod_raw} (P/N {pn_raw})", "🔴 REVISIÓN MANUAL (0%)", "Sin P/N o requiere confirmación de plano/medida"

# Carga de la solicitud del cliente
st.subheader("📂 Cargar Solicitud de Cotización del Cliente")
archivo_subido = st.file_uploader("Arrastra aquí el archivo del cliente (.csv o .xlsx):", type=["csv", "xlsx", "xls"])

if archivo_subido is not None:
    if df_cat is None:
        st.error("⚠️ Debes cargar primero el Catálogo Maestro AGC en la barra lateral para poder homologar.")
    else:
        try:
            df_raw = leer_archivo_inteligente(archivo_subido)
            # Renombrar columnas asegurando que sean únicas
            mapeo = {}
            col_usadas = set()

            def asignar(orig, destino):
                if destino not in col_usadas:
                    mapeo[orig] = destino
                    col_usadas.add(destino)

            for c in df_raw.columns:
                c_clean = str(c).strip().upper()
                if c_clean == "ITEM":
                    asignar(c, "ITEM")
                elif any(k in c_clean for k in ["PARTE", "P/N", "PART", "CODIGO"]):
                    asignar(c, "NUMERO DE PARTE")
                elif any(k in c_clean for k in ["CANTIDAD", "QTY", "CANT"]):
                    asignar(c, "CANTIDAD SOLICITADA")
                elif any(k in c_clean for k in ["MAQUINA", "EQUIPO", "MACHINE"]):
                    asignar(c, "MAQUINA")
                elif any(k in c_clean for k in ["PRODUCTO", "DESCRIP", "REPUESTO", "ITEM"]):
                    asignar(c, "PRODUCTO")

            df_cliente = df_raw.rename(columns=mapeo).copy()

            # Garantizar columnas mínimas
            if "ITEM" not in df_cliente.columns:
                df_cliente.insert(0, "ITEM", range(1, len(df_cliente) + 1))
            if "PRODUCTO" not in df_cliente.columns:
                df_cliente["PRODUCTO"] = ""
            if "NUMERO DE PARTE" not in df_cliente.columns:
                df_cliente["NUMERO DE PARTE"] = ""
            if "CANTIDAD SOLICITADA" not in df_cliente.columns:
                df_cliente["CANTIDAD SOLICITADA"] = 1
            if "MAQUINA" not in df_cliente.columns:
                df_cliente["MAQUINA"] = ""

            st.markdown(f"**Archivo cargado:** `{archivo_subido.name}` ({len(df_cliente)} ítems detectados)")
            st.dataframe(df_cliente.head(4), use_container_width=True)

            if st.button("🚀 Homologar Lote y Calcular Confianza Comercial", type="primary"):
                with st.spinner("Homologando con motor bilingüe y catálogo AGC..."):
                    filas = []
                    for idx, r in df_cliente.iterrows():
                        desc, seg, brand, mod, man_desc, conf, crit = homologar_item(r, df_cat)
                        filas.append({
                            "ITEM": r.get("ITEM", idx + 1),
                            "DESCRIPTION": desc,
                            "SEGMENT": seg,
                            "BRAND": brand,
                            "MODEL": mod,
                            "U/M": "UN",
                            "QUANTITY": r.get("CANTIDAD SOLICITADA", 1),
                            "OBSERVATIONS-DESCRIPCION CLIENTE": f"{r.get('PRODUCTO', '')} | P/N: {r.get('NUMERO DE PARTE', '')} | Máq: {r.get('MAQUINA', '')}",
                            "DESCRIPCION MANUALES": man_desc,
                            "CONFIANZA": conf,
                            "CRITERIO": crit
                        })

                    df_salida = pd.DataFrame(filas)
                    st.session_state["df_resultado"] = df_salida

            if "df_resultado" in st.session_state:
                res = st.session_state["df_resultado"]
                st.success(f"✅ ¡Homologación completada! {len(res)} repuestos procesados.")

                c_alta = len(res[res["CONFIANZA"].str.contains("ALTA")])
                c_media = len(res[res["CONFIANZA"].str.contains("MEDIA")])
                c_sug = len(res[res["CONFIANZA"].str.contains("SUGERIDO")])
                c_rev = len(res[res["CONFIANZA"].str.contains("MANUAL")])

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("🟢 Alta Confianza", f"{c_alta} ({round(c_alta/len(res)*100)}%)", "Listos para cotizar")
                k2.metric("🟡 Media Confianza", f"{c_media} ({round(c_media/len(res)*100)}%)", "Confirmar modelo")
                k3.metric("🟠 Sugeridos", f"{c_sug} ({round(c_sug/len(res)*100)}%)", "Por texto técnico")
                k4.metric("🔴 Requiere Plano", f"{c_rev} ({round(c_rev/len(res)*100)}%)", "Revisión manual")

                filtro = st.radio("Filtrar visualización:", ["Todos", "🟢 Solo Alta Confianza", "🟡 Solo Media", "🔴 Solo Requieren Plano"], horizontal=True)
                df_vista = res
                if filtro == "🟢 Solo Alta Confianza":
                    df_vista = res[res["CONFIANZA"].str.contains("ALTA")]
                elif filtro == "🟡 Solo Media":
                    df_vista = res[res["CONFIANZA"].str.contains("MEDIA")]
                elif filtro == "🔴 Solo Requieren Plano":
                    df_vista = res[res["CONFIANZA"].str.contains("MANUAL")]

                st.dataframe(df_vista, use_container_width=True)

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
                res.to_csv(buffer_csv, sep=";", index=False)

                st.download_button(
                    label="📥 Descargar RFQ FR-053 Completo (.csv con Confianza)",
                    data=buffer_csv.getvalue().encode("latin1", errors="replace"),
                    file_name=f"RFQ_FR053_{cliente.replace(' ', '_') or 'HOMOLOGADO'}.csv",
                    mime="text/csv"
                )

        except Exception as err:
            st.error(f"Error al procesar la solicitud: {err}")
