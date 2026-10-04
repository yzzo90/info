import re
import logging
import requests
from datetime import datetime
from bs4 import BeautifulSoup
import streamlit as st
import pandas as pd

# --- Configurazione Pagina Streamlit ---
st.set_page_config(page_title="Dashboard Avvisi & News", page_icon="📢", layout="wide")

CURRENT_YEAR = datetime.now().year
logging.getLogger("urllib3").setLevel(logging.ERROR)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.salute.gov.it/",
    "Accept-Language": "it-IT,it;q=0.9",
}

# ==========================================
# 1. AVVISI ALIMENTARI (Ministero della Salute)
# ==========================================
URL_JSON = "https://www.salute.gov.it/new/page-data/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/page-data.json"


@st.cache_data(ttl=3600, show_spinner="Scarico i richiami dal Ministero...")
def fetch_data_alimentari():
    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        # Ottieni cookie iniziali per superare eventuali controlli/WAF
        try:
            session.get("https://www.salute.gov.it/", timeout=10)
        except Exception:
            pass

        response = session.get(URL_JSON, timeout=15)
        response.raise_for_status()
        json_data = response.json()

    except Exception as e:
        st.error(f"Errore nel recupero dati dal Ministero della Salute: {e}")
        return []

    risultati = []

    def esplora(node):
        if isinstance(node, dict):
            data_raw = node.get("dataPubblicazione") or node.get("field_data_pubblicazione")
            marca = node.get("field_marca")
            title = node.get("title")

            motivo = None
            motivo_obj = node.get("relationships", {}).get("field_motivo_segnalazione")
            if isinstance(motivo_obj, dict):
                motivo = motivo_obj.get("name")

            link = None
            path = node.get("path")
            if isinstance(path, dict):
                alias = path.get("alias")
                if alias:
                    link = "https://www.salute.gov.it/new/it" + alias

            if data_raw and title and link:
                try:
                    dt = datetime.strptime(data_raw, "%d/%m/%Y")
                    if dt.year == CURRENT_YEAR:
                        risultati.append({
                            "Data": data_raw,
                            "dt_obj": dt,
                            "Marca": marca or "",
                            "Titolo": title,
                            "Motivo": motivo or "",
                            "Link": link,
                        })
                except ValueError:
                    pass

            for value in node.values():
                esplora(value)

        elif isinstance(node, list):
            for item in node:
                esplora(item)

    esplora(json_data)

    # Rimuovi duplicati basandoti sull'URL
    visti = set()
    unici = []
    for item in risultati:
        if item["Link"] not in visti:
            visti.add(item["Link"])
            unici.append(item)

    # Ordina per data decrescente
    unici.sort(key=lambda x: x["dt_obj"], reverse=True)
    return unici


# ==========================================
# 2. FERROTRAMVIARIA
# ==========================================
URL_AVVISI = "https://www.ferrotramviaria.it/web/guest/avvisi"
URL_NEWS = "https://www.ferrotramviaria.it/web/guest/news"


@st.cache_data(ttl=900)
def estrai_avvisi_ferrovia():
    try:
        response = requests.get(URL_AVVISI, headers=HEADERS, timeout=15)
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
    except Exception as e:
        st.error(f"Errore nel recupero avvisi Ferrotramviaria: {e}")
        return []


@st.cache_data(ttl=900)
def estrai_news_ferrovia():
    try:
        response = requests.get(URL_NEWS, headers=HEADERS, timeout=15)
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
    except Exception as e:
        st.error(f"Errore nel recupero news Ferrotramviaria: {e}")
        return []


# ==========================================
# 3. INTERFACCIA
# ==========================================
st.title("📌 Centro Info: Ferrotramviaria & Sicurezza Alimentare")

tab_ferrovia, tab_alimentare = st.tabs(
    ["🚆 Ferrotramviaria (News & Avvisi)", "🥗 Avvisi Alimentari"]
)

with tab_ferrovia:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔔 Avvisi Ferrotramviaria")
        avvisi_ft = estrai_avvisi_ferrovia()
        if avvisi_ft:
            for idx, item in enumerate(avvisi_ft, 1):
                st.markdown(f"{idx}. [{item['titolo']}]({item['link']})", unsafe_allow_html=True)
        else:
            st.info("Nessun avviso trovato.")

    with col2:
        st.subheader("📰 News Ferrotramviaria")
        news_ft = estrai_news_ferrovia()
        if news_ft:
            for idx, item in enumerate(news_ft, 1):
                st.markdown(f"{idx}. [{item['titolo']}]({item['link']})")
        else:
            st.info("Nessuna news trovata.")

with tab_alimentare:
    dati_alim = fetch_data_alimentari()

    col_btn, _ = st.columns([1, 4])
    with col_btn:
        if st.button("🔄 Ricarica Dati Alimentari"):
            st.cache_data.clear()
            st.rerun()

    if dati_alim:
        df = pd.DataFrame(dati_alim)

        search_query = st.text_input(
            "🔍 Cerca nei richiami alimentari (marca, prodotto, motivo...):", ""
        )
        if search_query:
            df = df[
                df["Marca"].str.contains(search_query, case=False, na=False, regex=False)
                | df["Titolo"].str.contains(search_query, case=False, na=False, regex=False)
                | df["Motivo"].str.contains(search_query, case=False, na=False, regex=False)
            ]

        st.subheader(f"Avvisi Sicurezza Alimentare - {len(df)} risultati (Anno {CURRENT_YEAR})")

        st.dataframe(
            df[["Data", "Marca", "Titolo", "Motivo", "Link"]],
            column_config={
                "Link": st.column_config.LinkColumn("Link Scheda", display_text="Apri")
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning("Nessun dato alimentare disponibile al momento.")
