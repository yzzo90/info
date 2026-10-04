import re
import logging
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

# ==========================================
# 0. CONFIGURAZIONE PAGINA & LOGGING
# ==========================================
st.set_page_config(
    page_title="Dashboard Avvisi & News", 
    page_icon="📢", 
    layout="wide"
)

CURRENT_YEAR = datetime.now().year
logging.getLogger("urllib3").setLevel(logging.ERROR)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
}

# ==========================================
# 1. AVVISI ALIMENTARI (Ministero della Salute)
# ==========================================
URLS_RICHIAMI = [
    "https://www.salute.gov.it/new/it/avvisi-e-richiami-di-prodotti-alimentari",
    "https://www.salute.gov.it/new/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/",
    "https://www.salute.gov.it/new/it/tema/sistema-di-controllo-della-sicurezza-alimentare/",
]

def _fetch_da_html(session):
    """Scraping con tentativi su più percorsi del portale del Ministero."""
    risultati = []

    for url in URLS_RICHIAMI:
        try:
            resp = session.get(url, timeout=12, allow_redirects=True)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Seleziona i link relativi alle schede di avviso sicurezza alimentare
            cards = soup.find_all("a", href=re.compile(r"ext-avviso-sicurezza-alimentare", re.I))

            # Fallback generico se la classe/href varia
            if not cards:
                cards = [
                    a for a in soup.find_all("a", href=True)
                    if "/avvisi/" in a["href"] or "richiam" in a["href"]
                ]

            for card in cards:
                link = card.get("href", "")
                if not link.startswith("http"):
                    link = "https://www.salute.gov.it" + link

                testo_card = card.get_text(separator=" ", strip=True)

                # Estrazione data pubblicazione (es. 15/05/2026)
                data_str = ""
                dt_obj = datetime.now()
                match_data = re.search(r"\b\d{2}/\d{2}/\d{4}\b", testo_card)
                if match_data:
                    data_str = match_data.group(0)
                    try:
                        dt_obj = datetime.strptime(data_str, "%d/%m/%Y")
                    except ValueError:
                        pass

                # Pulizia titolo e marca
                titolo = testo_card
                titolo_el = card.find(
                    ["h3", "h4", "p", "div", "span"],
                    class_=re.compile(r"title|titolo|heading|name", re.I)
                )
                if titolo_el:
                    titolo = titolo_el.get_text(strip=True)

                marca = ""
                if " - " in titolo:
                    parti = titolo.split(" - ", 1)
                    marca, titolo = parti[0], parti[1]

                if link:
                    risultati.append({
                        "Data": data_str or dt_obj.strftime("%d/%m/%Y"),
                        "dt_obj": dt_obj,
                        "Marca": marca,
                        "Titolo": titolo,
                        "Motivo": "Richiamo per rischio sanitario / alimentare",
                        "Link": link,
                    })

            if risultati:
                break

        except Exception:
            continue

    # Rimuovi duplicati basandoti sul link unico
    visti = set()
    unici = []
    for r in risultati:
        if r["Link"] not in visti:
            visti.add(r["Link"])
            unici.append(r)

    unici.sort(key=lambda x: x["dt_obj"], reverse=True)
    return unici


@st.cache_data(ttl=1800, show_spinner="Caricamento richiami alimentari...")
def fetch_data_alimentari():
    session = requests.Session()
    session.headers.update(HEADERS)

    # Inizializza cookie di sessione sulla home
    try:
        session.get("https://www.salute.gov.it/new/it/", timeout=5)
    except Exception:
        pass

    dati = _fetch_da_html(session)
    return dati


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
                
                # Evidenzia la parola "sciopero" in rosso
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
# 3. INTERFACCIA STREAMLIT
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

# --- TAB 2: RICHAMI ALIMENTARI ---
with tab_alimentare:
    col_btn, _ = st.columns([1, 4])
    with col_btn:
        if st.button("🔄 Ricarica Dati"):
            st.cache_data.clear()
            st.rerun()

    dati_alim = fetch_data_alimentari()

    if dati_alim:
        df = pd.DataFrame(dati_alim)

        search_query = st.text_input(
            "🔍 Cerca nei richiami alimentari (es. marca, prodotto o motivo):", ""
        )
        if search_query:
            df = df[
                df["Marca"].str.contains(search_query, case=False, na=False, regex=False)
                | df["Titolo"].str.contains(search_query, case=False, na=False, regex=False)
                | df["Motivo"].str.contains(search_query, case=False, na=False, regex=False)
            ]

        st.subheader(f"Richiami Registrati ({len(df)})")

        st.dataframe(
            df[["Data", "Marca", "Titolo", "Motivo", "Link"]],
            column_config={
                "Link": st.column_config.LinkColumn("Scheda Ufficiale", display_text="Apri Scheda")
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning(
            "Nessun dato alimentare disponibile al momento. Clicca su 'Ricarica Dati' per riprovare."
        )
