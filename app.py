import re
import logging
import requests
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

# Headers ad alta fedeltà per bypassare filtri WAF / Cloudflare
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

URL_MINISTERO = "https://www.salute.gov.it/new/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/"
URL_GATSBY_JSON = "https://www.salute.gov.it/new/page-data/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/page-data.json"
URL_MIRROR_ALT = "https://richiamialimenti.it/"

# ==========================================
# 1. AVVISI ALIMENTARI (Multi-Strategia)
# ==========================================

def _fetch_via_json(session):
    """Strategia 1: recupero dal payload JSON di stato Gatsby del Ministero."""
    risultati = []
    resp = session.get(URL_GATSBY_JSON, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        page_ctx = data.get("result", {}).get("pageContext", {})
        nodes = page_ctx.get("nodes", []) or data.get("result", {}).get("data", {}).get("allAvviso", {}).get("nodes", [])

        for node in nodes:
            titolo = node.get("title") or node.get("titolo") or "Richiamo Alimentare"
            marca = node.get("marca") or node.get("produttore") or "N/D"
            motivo = node.get("motivo") or "Richiamo per rischio sanitario / alimentare"
            path = node.get("path") or node.get("slug") or ""
            link = f"https://www.salute.gov.it/new/it{path}" if path else URL_MINISTERO
            data_pub = node.get("date") or node.get("dataPubblicazione") or datetime.now().strftime("%d/%m/%Y")

            risultati.append({
                "Data": data_pub,
                "Marca": marca,
                "Titolo": titolo,
                "Motivo": motivo,
                "Link": link
            })
    return risultati


def _fetch_via_html(session):
    """Strategia 2: scraping dell'HTML con selettori estesi."""
    risultati = []
    resp = session.get(URL_MINISTERO, timeout=10)
    if resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Cerca tutti i link che portano a schede di sicurezza alimentare
        cards = soup.find_all("a", href=re.compile(r"ext-avviso-sicurezza-alimentare|richiam", re.I))

        for card in cards:
            link = card.get("href", "")
            if not link.startswith("http"):
                link = "https://www.salute.gov.it" + link

            testo = card.get_text(separator=" ", strip=True)
            if len(testo) < 4:
                continue

            match_data = re.search(r"\b\d{2}/\d{2}/\d{4}\b", testo)
            data_str = match_data.group(0) if match_data else datetime.now().strftime("%d/%m/%Y")

            marca = "Ministero Salute"
            titolo = testo
            if " - " in testo:
                parti = testo.split(" - ", 1)
                marca, titolo = parti[0].strip(), parti[1].strip()

            risultati.append({
                "Data": data_str,
                "Marca": marca,
                "Titolo": titolo,
                "Motivo": "Richiamo per rischio sanitario / alimentare",
                "Link": link
            })
    return risultati


def _fetch_via_mirror(session):
    """Strategia 3: fallback su aggregatore aperto."""
    risultati = []
    resp = session.get(URL_MIRROR_ALT, timeout=10)
    if resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.find_all(["div", "article", "li"], class_=re.compile(r"richiamo|item|post", re.I))

        for item in items[:15]:
            link_tag = item.find("a", href=True)
            if not link_tag:
                continue
            
            link = link_tag["href"]
            titolo = link_tag.get_text(strip=True)
            
            if titolo and len(titolo) > 5:
                risultati.append({
                    "Data": datetime.now().strftime("%d/%m/%Y"),
                    "Marca": "Aggiornamento Recente",
                    "Titolo": titolo,
                    "Motivo": "Richiamo di Sicurezza Alimentare",
                    "Link": link if link.startswith("http") else URL_MIRROR_ALT + link,
                })
    return risultati


@st.cache_data(ttl=1800, show_spinner="Caricamento richiami alimentari...")
def fetch_data_alimentari():
    session = requests.Session()
    session.headers.update(HEADERS)

    # Tentativo 1: JSON Interno
    try:
        dati = _fetch_via_json(session)
        if dati:
            return dati
    except Exception:
        pass

    # Tentativo 2: Parsing HTML Diretto
    try:
        dati = _fetch_via_html(session)
        if dati:
            return dati
    except Exception:
        pass

    # Tentativo 3: Mirror Secondario
    try:
        dati = _fetch_via_mirror(session)
        if dati:
            return dati
    except Exception:
        pass

    # Fallback finale se tutti i tentativi falliscono
    return [{
        "Data": datetime.now().strftime("%d/%m/%Y"),
        "Marca": "Ministero della Salute",
        "Titolo": "Accedi direttamente all'elenco aggiornato sul portale ufficiale.",
        "Motivo": "Protezione antiscraping / WAF attiva sul server sorgente",
        "Link": URL_MINISTERO
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
