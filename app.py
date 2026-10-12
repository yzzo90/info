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
    """Converte stringhe nel formato YYYYMMDDHHMMSS in una data/ora leggibile."""
    if isinstance(val, str) and val.isdigit() and len(val) == 14:
        try:
            dt = datetime.strptime(val, "%Y%m%d%H%M%S")
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        except ValueError:
            pass
    return val

def process_dataframe(df):
    """Applica la formattazione leggibile a tutte le colonne del DataFrame."""
    if df is not None and not df.empty:
        for col in df.columns:
            df[col] = df[col].apply(format_datetime_value)
    return df

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
                df_p = process_dataframe(df_p)
                st.dataframe(df_p, use_container_width=True)
            else:
                if isinstance(json_data, list):
                    df = pd.DataFrame(json_data)
                    df = process_dataframe(df)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.write(json_data)

        with tab_a:
            if arrivi:
                df_a = pd.DataFrame(arrivi)
                df_a = process_dataframe(df_a)
                st.dataframe(df_a, use_container_width=True)
            else:
                st.info("Nessun dato sugli arrivi disponibile.")
    except Exception as e:
        st.warning(f"Impossibile formattare i dati tabulari automaticamente. Ecco i dati grezzi:")
        st.json(json_data)

# ==========================================
# 3. INTERFACCIA STREAMLIT
# ==========================================
st.title("📌 Dashboard Avvisi Ferrotramviaria & Sicurezza Alimentare")

tab_ferrovia, tab_realtime, tab_alimentare = st.tabs(
    ["🚆 Ferrotramviaria", "🕒 Realtime Treni", "🥗 Avvisi Alimentari"]
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

# --- TAB 2: REALTIME TRENI (API JSON CON AUTO-REFRESH & DATE FORMATTATE) ---
with tab_realtime:
    auto_refresh_script = """
    <script>
        setTimeout(function(){
            window.location.reload();
        }, 60000);
    </script>
    """
    components.html(auto_refresh_script, height=0, width=0)

    col_rt_head, col_rt_btn = st.columns([4, 1])
    with col_rt_btn:
        if st.button("🔄 Aggiorna Treni", use_container_width=True):
            fetch_realtime_data.clear()
            st.rerun()

    st.markdown("### Tabellone in Tempo Reale (Aggiornamento automatico ogni 1 min)")
    
    stazione_scelta = st.selectbox(
        "Seleziona Stazione", 
        options=["Stazione Europa (S01136)", "Stazione Ruvo (S01160)"]
    )

    if "Europa" in stazione_scelta:
        data_json = fetch_realtime_data("S01136")
        format_realtime_table(data_json, "Treni in Tempo Reale - Stazione Europa")
    else:
        data_json = fetch_realtime_data("S01160")
        format_realtime_table(data_json, "Treni in Tempo Reale - Stazione Ruvo")

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
