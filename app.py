import re
import random
import logging
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

            titolo = re.sub(
                r"(sciopero)",
                r'<span style="color:red; font-weight:bold;">\1</span>',
                titolo_raw,
                flags=re.IGNORECASE,
            )
            avvisi.append({"titolo": titolo, "link": link})
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
        title = title_tag.get_text(strip=True) if title_tag else "–"
        link_tag = article.find("a", class_="nav-link", href=True)
        link = link_tag["href"] if link_tag else "#"
        if link.startswith("/"):
            link = "https://www.ferrotramviaria.it" + link
        news.append({"titolo": title, "link": link})
    return news

# ==========================================
# 2. INTERFACCIA STREAMLIT
# ==========================================
st.title("📌 Dashboard Avvisi Ferrotramviaria & Sicurezza Alimentare")

tab_ferrovia, tab_alimentare = st.tabs(
    ["🚆 Ferrotramviaria", "🥗 Avvisi Alimentari"]
)

# --- TAB 1: FERROTRAMVIARIA ---
with tab_ferrovia:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔔 Avvisi di Servizio")
        avvisi_ft = estrai_avvisi_ferrovia()
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
        news_ft = estrai_news_ferrovia()
        if news_ft:
            for idx, item in enumerate(news_ft, 1):
                st.markdown(f"{idx}. [{item['titolo']}]({item['link']})")
        else:
            st.info("Nessuna news disponibile al momento.")

# --- TAB 2: RICHIAMI ALIMENTARI (WEB APP KOYEB) ---
with tab_alimentare:
    app_url = "https://wrong-aurie-alimenti190-497b0369.koyeb.app/"
    
    # Intestazione con Tasto Refresh affiancato
    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.subheader("🥗 Richiami & Avvisi Alimentari")
    with col_btn:
        if st.button("🔄 Aggiorna", use_container_width=True):
            st.rerun()

    # Recupera il contenuto HTML dall'app esterna
    res = fetch_url(app_url)
    
    if res and res.text:
        # CSS per forzare il contrasto dei colori (testo bianco su sfondo scuro)
        custom_css = """
        <style>
            /* Testo bianco visibile su tutto il frame */
            body, p, div, span, td, th, table {
                color: #ffffff !important;
            }
            /* Sfondo scuro per le celle della tabella */
            table, tr, td {
                background-color: #121212 !important;
            }
            /* Intestazione della tabella con sfondo chiaro e testo nero */
            th {
                background-color: #e0e0e0 !important;
                color: #000000 !important;
            }
            /* Link ben visibili in azzurro chiaro */
            a {
                color: #4da6ff !important;
                font-weight: bold !important;
            }
            /* Input di ricerca */
            input, select, textarea {
                color: #000000 !important;
                background-color: #ffffff !important;
            }
        </style>
        """
        
        # Inietta il CSS prima del codice HTML dell'app
        html_modificato = custom_css + res.text
        
        # Rendering dell'HTML modificato
        components.html(html_modificato, height=800, scrolling=True)
    else:
        # Fallback iframe se non si riesce a leggere il sorgente
        components.iframe(src=app_url, height=800, scrolling=True)
