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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
}

# ==========================================
# 1. AVVISI ALIMENTARI (API & Multi-Source)
# ==========================================

def _fetch_from_opendata_api():
    """Strategia 1: Interroga il catalogo OpenData ufficiale dei richiami alimentari."""
    risultati = []
    # Endpoint API OpenData / CKAN
    url_api = "https://www.dati.gov.it/subsets/ministero-salute/richiami-alimentari/api/v1/richiami"
    
    try:
        resp = requests.get(url_api, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", []) or data.get("result", []) or data
            if isinstance(items, list):
                for item in items:
                    data_pub = item.get("data") or item.get("data_pubblicazione") or datetime.now().strftime("%d/%m/%Y")
                    marca = item.get("marca") or item.get("osa") or "Richiamo Alimentare"
                    titolo = item.get("prodotto") or item.get("denominazione") or item.get("titolo") or "Avviso di sicurezza"
                    motivo = item.get("motivo") or item.get("motivo_richiamo") or "Rischio sanitario / microbiologico"
                    link = item.get("link") or item.get("url") or "https://www.salute.gov.it/new/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/"

                    risultati.append({
                        "Data": data_pub,
                        "Marca": marca,
                        "Titolo": titolo,
                        "Motivo": motivo,
                        "Link": link
                    })
    except Exception:
        pass
    return risultati


def _fetch_from_portal_aggregator():
    """Strategia 2: Scrape dall'aggregatore nazionale completo per la sicurezza alimentare."""
    risultati = []
    url_mirror = "https://www.ilfattoalimentare.it/category/richiami"
    
    try:
        resp = requests.get(url_mirror, headers=HEADERS, timeout=12)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            articles = soup.find_all(["article", "div"], class_=re.compile(r"post|entry|article", re.I))
            
            for art in articles:
                link_tag = art.find("a", href=True)
                if not link_tag:
                    continue
                
                link = link_tag["href"]
                titolo = link_tag.get_text(strip=True)
                
                # Cerca eventuale data
                time_tag = art.find("time")
                data_str = time_tag.get_text(strip=True) if time_tag else datetime.now().strftime("%d/%m/%Y")
                
                if len(titolo) > 12 and "richiamo" in titolo.lower() or "ritiro" in titolo.lower() or "salute" in titolo.lower():
                    marca = "Richiamo Alimentare"
                    if ":" in titolo:
                        parti = titolo.split(":", 1)
                        marca, titolo = parti[0].strip(), parti[1].strip()
                    elif " - " in titolo:
                        parti = titolo.split(" - ", 1)
                        marca, titolo = parti[0].strip(), parti[1].strip()

                    if not any(r["Link"] == link for r in risultati):
                        risultati.append({
                            "Data": data_str,
                            "Marca": marca,
                            "Titolo": titolo,
                            "Motivo": "Richiamo ufficiale per rischio sanitario / sicurezza alimentare",
                            "Link": link
                        })
    except Exception:
        pass
    return risultati


@st.cache_data(ttl=1800, show_spinner="Caricamento richiami alimentari...")
def fetch_data_alimentari():
    # 1. Prova l'API OpenData
    dati = _fetch_from_opendata_api()
    if dati and len(dati) > 1:
        return dati

    # 2. Prova l'aggregatore nazionale in tempo reale
    dati = _fetch_from_portal_aggregator()
    if dati and len(dati) > 1:
        return dati

    # 3. Fallback di garanzia con collegamento diretto al Ministero
    return [{
        "Data": datetime.now().strftime("%d/%m/%Y"),
        "Marca": "Ministero della Salute",
        "Titolo": "Accedi al Portale del Ministero della Salute per la consultazione diretta",
        "Motivo": "Consultazione diretta sul sito istituzionale",
        "Link": "https://www.salute.gov.it/new/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/"
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
