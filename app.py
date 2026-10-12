import re
import random
import logging
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# ==========================================
# 0. CONFIGURAZIONE PAGINA & LOGGING
# ==========================================
st.set_page_config(
    page_title="Dashboard Avvisi & News", 
    page_icon="📢", 
    layout="wide"
)

logging.getLogger("urllib3").setLevel(logging.ERROR)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

def fetch_url(url):
    """Richiesta HTTP per recuperare i contenuti HTML dell'app o dei siti esterni."""
    try:
        resp = requests.get(url, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=10)
        if resp.status_code == 200:
            return resp
    except Exception:
        pass
    return None

# ==========================================
# 1. FERROTRAMVIARIA (Avvisi & News)
# ==========================================
URL_AVVISI = "https://www.ferrotramviaria.it/web/guest/avvisi"
URL_NEWS = "https://www.ferrotramviaria.it/web/guest/news"

KEYWORDS_SCIOPERO = ["sciopero", "agitazione sindacale", "agitazioni sindacali", "astensione dal lavoro"]

def contiene_parole_chiave(testo, parole_chiave):
    testo_lower = testo.lower()
    return any(k.lower() in testo_lower for k in parole_chiave)

def evidenzia_parole_chiave(testo, parole_chiave):
    pattern = r"(" + "|".join([re.escape(k) for k in parole_chiave]) + r")"
    return re.sub(pattern, r'<span style="color:red; font-weight:bold;">\1</span>', testo, flags=re.IGNORECASE)

@st.cache_data(ttl=900)
def estrai_avvisi_ferrovia():
    resp = fetch_url(URL_AVVISI)
    if not resp:
        return []
    
    soup = BeautifulSoup(resp.text, "html.parser")
    avvisi = []
    for div in soup.select("div.notice"):
        link_tag = div.find("a", href=True)
        title_tag = div.find("p", class_="title")
        if link_tag and title_tag:
            link = link_tag["href"]
            titolo_raw = title_tag.get_text(strip=True)
            if not link.startswith("http"):
                link = "https://www.ferrotramviaria.it" + link

            titolo_html = evidenzia_parole_chiave(titolo_raw, KEYWORDS_SCIOPERO)
            is_sciopero = contiene_parole_chiave(titolo_raw, KEYWORDS_SCIOPERO)
            
            avvisi.append({
                "titolo_raw": titolo_raw, 
                "titolo": titolo_html, 
                "link": link,
                "is_sciopero": is_sciopero
            })
    return avvisi

@st.cache_data(ttl=900)
def estrai_news_ferrovia():
    resp = fetch_url(URL_NEWS)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    news = []
    for article in soup.find_all("div", class_="article"):
        title_tag = article.find("div", class_="article-title")
        title_raw = title_tag.get_text(strip=True) if title_tag else "–"
        link_tag = article.find("a", class_="nav-link", href=True)
        link = link_tag["href"] if link_tag else "#"
        if link.startswith("/"):
            link = "https://www.ferrotramviaria.it" + link
            
        titolo_html = evidenzia_parole_chiave(title_raw, KEYWORDS_SCIOPERO)
        is_sciopero = contiene_parole_chiave(title_raw, KEYWORDS_SCIOPERO)
        
        news.append({
            "titolo_raw": title_raw,
            "titolo": titolo_html, 
            "link": link,
            "is_sciopero": is_sciopero
        })
    return news

# ==========================================
# 2. FUNZIONE PER DATI REALTIME JSON & FORMATTAZIONE DATE
# ==========================================
@st.cache_data(ttl=30)
def fetch_realtime_data(cod_sito):
    url = f"https://eticket.ferrovienordbarese.it/b2c/json/realtime/dati?codSito={cod_sito}&type=T"
    try:
        resp = requests.get(url, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None

def format_datetime_value(val):
    if isinstance(val, str) and val.isdigit() and len(val) == 14:
        try:
            dt = datetime.strptime(val, "%Y%m%d%H%M%S")
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        except ValueError:
            pass
    return val

def process_dataframe(df):
    if df is not None and not df.empty:
        for col in df.columns:
            df[col] = df[col].apply(format_datetime_value)
            
            if 'ritardo' in col.lower():
                def clean_delay(val):
                    if val is None or str(val).lower() == 'none' or pd.isna(val):
                        return "0 min"
                    try:
                        num = float(val)
                        if num == 0:
                            return "In orario"
                        else:
                            return f"+{int(num)} min"
                    except ValueError:
                        return val
                df[col] = df[col].apply(clean_delay)
    return df

def reorder_columns(df):
    if df is None or df.empty:
        return df
    
    cols_lower = {c.lower(): c for c in df.columns}
    initial_targets = ['nomedestinazione', 'partenza', 'ritardo', 'soppressa']
    ordered = []
    
    for t in initial_targets:
        if t in cols_lower:
            ordered.append(cols_lower[t])
            
    binario_col = next((cols_lower[c] for c in cols_lower if 'binario' in c and 'effettivo' in c), None)
    numero_col = next((cols_lower[c] for c in cols_lower if c == 'numero'), None)
    
    remaining = [c for c in df.columns if c not in ordered and c != binario_col]
    
    if binario_col and numero_col and numero_col in remaining:
        num_idx = remaining.index(numero_col)
        remaining.insert(num_idx, binario_col)
    elif binario_col:
        remaining.append(binario_col)
        
    final_cols = ordered + [c for c in remaining if c not in ordered]
    return df[[c for c in final_cols if c in df.columns]]

def highlight_soppressa(row):
    cols_lower = [c.lower() for c in row.index]
    if 'soppressa' in cols_lower:
        val = str(row.iloc[cols_lower.index('soppressa')]).strip().upper()
        if val and val != 'N' and val != 'FALSE':
            return ['background-color: rgba(255, 0, 0, 0.3)'] * len(row)
    return [''] * len(row)

def format_realtime_table(json_data, titolo_sezione):
    st.subheader(titolo_sezione)
    if not json_data:
        st.info("Nessun dato disponibile o errore di connessione al server.")
        return

    try:
        partenze = json_data.get("partenze", json_data.get("prospettoPartenze", []))
        arrivi = json_data.get("arrivi", json_data.get("prospettoArrivi", []))

        tab_p, tab_a = st.tabs(["Partenze", "Arrivi"])

        with tab_p:
            if partenze:
                df_p = pd.DataFrame(partenze)
                col_partenza = next((c for c in df_p.columns if any(k in c.lower() for k in ['partenza', 'ora', 'data', 'time', 'sched'])), df_p.columns[0])
                
                df_p['_sort_dt'] = pd.to_datetime(df_p[col_partenza].astype(str), format='%Y%m%d%H%M%S', errors='coerce')
                df_p = df_p.sort_values(by='_sort_dt', ascending=True).drop(columns=['_sort_dt'])
                
                df_p = process_dataframe(df_p)
                df_p = reorder_columns(df_p)
                
                styled_df_p = df_p.style.apply(highlight_soppressa, axis=1)
                st.dataframe(styled_df_p, use_container_width=True)
            else:
                if isinstance(json_data, list):
                    df = pd.DataFrame(json_data)
                    col_partenza = next((c for c in df.columns if any(k in c.lower() for k in ['partenza', 'ora', 'data', 'time', 'sched'])), df.columns[0])
                    df['_sort_dt'] = pd.to_datetime(df[col_partenza].astype(str), format='%Y%m%d%H%M%S', errors='coerce')
                    df = df.sort_values(by='_sort_dt', ascending=True).drop(columns=['_sort_dt'])
                    df = process_dataframe(df)
                    df = reorder_columns(df)
                    styled_df = df.style.apply(highlight_soppressa, axis=1)
                    st.dataframe(styled_df, use_container_width=True)
                else:
                    st.write(json_data)

        with tab_a:
            if arrivi:
                df_a = pd.DataFrame(arrivi)
                col_arrivo = next((c for c in df_a.columns if any(k in c.lower() for k in ['arrivo', 'ora', 'data', 'time', 'sched'])), df_a.columns[0])
                df_a['_sort_dt'] = pd.to_datetime(df_a[col_arrivo].astype(str), format='%Y%m%d%H%M%S', errors='coerce')
                df_a = df_a.sort_values(by='_sort_dt', ascending=True).drop(columns=['_sort_dt'])
                df_a = process_dataframe(df_a)
                df_a = reorder_columns(df_a)
                styled_df_a = df_a.style.apply(highlight_soppressa, axis=1)
                st.dataframe(styled_df_a, use_container_width=True)
            else:
                st.info("Nessun dato sugli arrivi disponibile.")
    except Exception as e:
        st.warning("Impossibile formattare i dati tabulari automaticamente. Ecco i dati grezzi:")
        st.json(json_data)

# ==========================================
# 3. INTERFACCIA STREAMLIT
# ==========================================
st.title("📌 Dashboard")

tab_ferrovia, tab_realtime, tab_alimentare, tab_tracking = st.tabs(
    ["🚆 Ferrotramviaria", "🕒 Realtime Treni", "🥗 Avvisi Alimentari", "📦 Tracking Pacchi"]
)

# --- TAB 1: FERROTRAMVIARIA ---
with tab_ferrovia:
    col_head, col_refresh_ft = st.columns([4, 1])
    with col_refresh_ft:
        if st.button("🚆 Aggiorna", use_container_width=True):
            estrai_avvisi_ferrovia.clear()
            estrai_news_ferrovia.clear()
            st.rerun()

    avvisi_ft = estrai_avvisi_ferrovia()
    news_ft = estrai_news_ferrovia()

    elementi_sciopero = [
        item for item in avvisi_ft + news_ft if item.get("is_sciopero")
    ]

    if elementi_sciopero:
        st.toast("⚠️ Trovati avvisi o news di particolare rilevanza!", icon="⚠️")
        
        with st.popover("⚠️ ATTENZIONE: Avvisi sciopero!", use_container_width=True):
            st.warning(f"Sono stati rilevati **{len(elementi_sciopero)}** avvisi o news rilevanti:")
            for item in elementi_sciopero:
                st.markdown(f"• [{item['titolo_raw']}]({item['link']})")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔔 Avvisi di Servizio")
        if avvisi_ft:
            for idx, item in enumerate(avvisi_ft, 1):
                st.markdown(
                    f"{idx}. [{item['titolo']}]({item['link']})", 
                    unsafe_allow_html=True
                )
        else:
            st.info("Nessun avviso di servizio al momento.")

    with col2:
        st.subheader("📰 Ultime News")
        if news_ft:
            for idx, item in enumerate(news_ft, 1):
                st.markdown(
                    f"{idx}. [{item['titolo']}]({item['link']})", 
                    unsafe_allow_html=True
                )
        else:
            st.info("Nessuna news disponibile al momento.")

# --- TAB 2: REALTIME TRENI ---
with tab_realtime:
    col_rt_head, col_rt_btn = st.columns([4, 1])
    with col_rt_btn:
        if st.button("🔄 Aggiorna Treni", use_container_width=True):
            fetch_realtime_data.clear()
            st.rerun()

    st.markdown("### Tabellone in Tempo Reale")
    
    stazione_scelta = st.selectbox(
        "Seleziona Stazione", 
        options=["Stazione Ruvo (S01160)", "Stazione Europa (S01136)"],
        index=0,
        key="stazione_selezionata"
    )

    @st.fragment(run_every=60)
    def render_realtime_board():
        st.caption(f"Ultimo aggiornamento automatico: {datetime.now().strftime('%H:%M:%S')}")
        
        selected = st.session_state.get("stazione_selezionata", "")
        if "Ruvo" in selected:
            data_json = fetch_realtime_data("S01160")
            format_realtime_table(data_json, "Treni in Tempo Reale - Stazione Ruvo")
        else:
            data_json = fetch_realtime_data("S01136")
            format_realtime_table(data_json, "Treni in Tempo Reale - Stazione Europa")

    render_realtime_board()

# --- TAB 3: RICHIAMI ALIMENTARI (WEB APP KOYEB) ---
with tab_alimentare:
    app_url = "https://wrong-aurie-alimenti190-497b0369.koyeb.app/"
    
    col_title, col_btn = st.columns([4, 1])
    with col_btn:
        if st.button("🥗 Aggiorna", use_container_width=True):
            st.rerun()

    res = fetch_url(app_url)
    
    if res and res.text:
        custom_css = """
        <style>
            body, p, div, span, td, th, table {
                color: #ffffff !important;
            }
            table, tr, td {
                background-color: #121212 !important;
            }
            th {
                background-color: #e0e0e0 !important;
                color: #000000 !important;
            }
            a {
                color: #4da6ff !important;
                font-weight: bold !important;
            }
            input, select, textarea {
                color: #000000 !important;
                background-color: #ffffff !important;
            }
        </style>
        """
        html_modificato = custom_css + res.text
        components.html(html_modificato, height=800, scrolling=True)
    else:
        components.iframe(src=app_url, height=800, scrolling=True)

# --- TAB 4: TRACKING PACCHI (PRIVATO NEL BROWSER) ---
with tab_tracking:
    st.subheader("📦 Gestione Tracking Spedizioni Privato")
    st.markdown("I dati inseriti qui vengono salvati **esclusivamente nella memoria locale della sessione** e non vengono condivisi o salvati su alcun server.")

    if "tracking_list" not in st.session_state:
        st.session_state["tracking_list"] = []

    with st.form("form_tracking", clear_on_submit=True):
        col_f1, col_f2, col_f3 = st.columns([2, 3, 3])
        with col_f1:
            nome_pacco = st.text_input("Nome / Corriere")
        with col_f2:
            link_pacco = st.text_input("Link di Tracking (URL)")
        with col_f3:
            stato_pacco = st.text_input("Stato / Note (es. In transito, Consegnato)")
            
        submitted = st.form_submit_button("➕ Aggiungi Spedizione")
        if submitted:
            if nome_pacco and link_pacco:
                st.session_state["tracking_list"].append({
                    "nome": nome_pacco,
                    "link": link_pacco,
                    "stato": stato_pacco if stato_pacco else "In lavorazione"
                })
                st.success("Spedizione aggiunta con successo!")
                st.rerun()
            else:
                st.warning("Inserisci almeno il nome e il link di tracking.")

    st.markdown("### Le tue spedizioni salvate")
    if st.session_state["tracking_list"]:
        for idx, item in enumerate(st.session_state["tracking_list"]):
            col_t1, col_t2, col_t3, col_t4 = st.columns([2, 3, 3, 1])
            with col_t1:
                st.write(f"**{item['nome']}**")
            with col_t2:
                st.markdown(f"[Apri Tracking]({item['link']})")
            with col_t3:
                st.write(f"Stato: *{item['stato']}*")
            with col_t4:
                if st.button("🗑️", key=f"del_track_{idx}"):
                    st.session_state["tracking_list"].pop(idx)
                    st.rerun()
    else:
        st.info("Nessuna spedizione salvata al momento.")
