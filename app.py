import re
import logging
import requests
import feedparser
from datetime import datetime
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

# ==========================================
# 0. CONFIGURAZIONE PAGINA
# ==========================================
st.set_page_config(
    page_title="Dashboard Avvisi & News", 
    page_icon="📢", 
    layout="wide"
)

logging.getLogger("urllib3").setLevel(logging.ERROR)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Fonti Ufficiali
URL_RSS_MINISTERO = "https://www.salute.gov.it/portale/news/RSS_avvisi_richiami_osa.xml"
URL_MINISTERO_PAGE = "https://www.salute.gov.it/portale/news/p3_2_1_1.jsp?lingua=italiano&menu=notizie&p=richiamialimentari"

# ==========================================
# 1. AVVISI ALIMENTARI (Feed RSS + Parsing XML)
# ==========================================

def _fetch_via_rss():
    """Strategia 1: Feed RSS Ufficiale del Ministero (Esente da blocchi WAF/Cloudflare)."""
    risultati = []
    
    # Parsing del feed XML ufficiale
    feed = feedparser.parse(URL_RSS_MINISTERO)
    
    if feed.entries:
        for entry in feed.entries:
            titolo_raw = entry.get("title", "")
            link = entry.get("link", URL_MINISTERO_PAGE)
            descrizione = entry.get("summary", "") or entry.get("description", "")
            
            # Pulizia HTML dalla descrizione se presente
            if "<" in descrizione:
                descrizione = BeautifulSoup(descrizione, "html.parser").get_text(strip=True)
            
            # Formattazione data pubblicazione
            data_pub = datetime.now().strftime("%d/%m/%Y")
            if "published_parsed" in entry and entry.published_parsed:
                dt = datetime(*entry.published_parsed[:6])
                data_pub = dt.strftime("%d/%m/%Y")
            
            # Estrazione Marca / Prodotto se separati da '-' o ':'
            marca = "Ministero Salute"
            titolo = titolo_raw
            
            if " - " in titolo_raw:
                parti = titolo_raw.split(" - ", 1)
                marca, titolo = parti[0].strip(), parti[1].strip()
            elif ":" in titolo_raw:
                parti = titolo_raw.split(":", 1)
                marca, titolo = parti[0].strip(), parti[1].strip()

            risultati.append({
                "Data": data_pub,
                "Marca": marca,
                "Titolo": titolo,
                "Motivo": descrizione if descrizione else "Richiamo per rischio sanitario / alimentare",
                "Link": link
            })
            
    return risultati


def _fetch_via_html_legacy():
    """Strategia 2: Scraper di riserva sulla sezione news storica."""
    risultati = []
    resp = requests.get(URL_MINISTERO_PAGE, headers=HEADERS, timeout=10)
    
    if resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.find_all("a", href=re.compile(r"richiam|avviso", re.I))
        
        for item in items:
            link = item.get("href", "")
            if not link.startswith("http"):
                link = "https://www.salute.gov.it" + link
            
            txt = item.get_text(strip=True)
            if len(txt) > 10 and "richiam" in txt.lower():
                risultati.append({
                    "Data": datetime.now().strftime("%d/%m/%Y"),
                    "Marca": "Ministero della Salute",
                    "Titolo": txt,
                    "Motivo": "Richiamo ufficiale di sicurezza alimentare",
                    "Link": link
                })
    return risultati


@st.cache_data(ttl=1800, show_spinner="Caricamento richiami alimentari...")
def fetch_data_alimentari():
    # 1. Prova prima il Feed RSS Ufficiale (Soluzione ottimale per Streamlit Cloud)
    try:
        dati_rss = _fetch_via_rss()
        if dati_rss:
            return dati_rss
    except Exception:
        pass

    # 2. Prova lo scraping HTML di riserva
    try:
        dati_html = _fetch_via_html_legacy()
        if dati_html:
            return dati_html
    except Exception:
        pass

    # 3. Messaggio di fallback in caso eccezionale di disservizio del server ministeriale
    return [{
        "Data": datetime.now().strftime("%d/%m/%Y"),
        "Marca": "Ministero della Salute",
        "Titolo": "Consulta la tabella completa dei richiami sul portale ufficiale del Ministero.",
        "Motivo": "Connessione temporaneamente limitata",
        "Link": URL_MINISTERO_PAGE
    }]


# ==========================================
# 2. FERROTRAMVIARIA (Avvisi & News)
# ==========================================
URL_AVVISI = "https://www.ferrotramviaria.it/web/guest/avvisi"
URL_NEWS = "https://www.ferrotramviaria.it/web/guest/news"


@st.cache_data(ttl=900)
def estrai_avvisi_ferrovia():
    try:
        response = requests.get(URL_AVVISI, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

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
    except Exception:
        return []


@st.cache_data(ttl=900)
def estrai_news_ferrovia():
    try:
        response = requests.get(URL_NEWS, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

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
    except Exception:
        return []


# ==========================================
# 3. INTERFACCIA UTENTE STREAMLIT
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

# --- TAB 2: RICHIAMI ALIMENTARI ---
with tab_alimentare:
    col_btn, _ = st.columns([1, 4])
    with col_btn:
        if st.button("🔄 Ricarica Dati"):
            st.cache_data.clear()
            st.rerun()

    dati_alim = fetch_data_alimentari()
    df = pd.DataFrame(dati_alim)

    search_query = st.text_input(
        "🔍 Cerca nei richiami alimentari (es. marca o prodotto):", ""
    )
    if search_query and not df.empty:
        df = df[
            df["Marca"].astype(str).str.contains(search_query, case=False, na=False, regex=False)
            | df["Titolo"].astype(str).str.contains(search_query, case=False, na=False, regex=False)
            | df["Motivo"].astype(str).str.contains(search_query, case=False, na=False, regex=False)
        ]

    st.subheader(f"Richiami e Avvisi Sanitari ({len(df)})")

    st.dataframe(
        df[["Data", "Marca", "Titolo", "Motivo", "Link"]],
        column_config={
            "Link": st.column_config.LinkColumn("Scheda Ufficiale", display_text="Apri Scheda")
        },
        use_container_width=True,
        hide_index=True,
    )
