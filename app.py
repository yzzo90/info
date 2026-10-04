import re
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

# --- Configurazione Pagina Streamlit ---
st.set_page_config(page_title="Dashboard Avvisi & News", page_icon="📢", layout="wide")

CURRENT_YEAR = datetime.now().year
logging.getLogger("urllib3").setLevel(logging.ERROR)

URL_JSON = "https://www.salute.gov.it/new/page-data/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/page-data.json"
URL_RSS = "https://www.salute.gov.it/portale/news/rssRichiami.jsp?tipo=richiami"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
}


# ==========================================
# 1. PARSER DATI ALIMENTARI
# ==========================================
def _parse_json_data(json_data):
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

    visti = set()
    unici = []
    for item in risultati:
        if item["Link"] not in visti:
            visti.add(item["Link"])
            unici.append(item)

    unici.sort(key=lambda x: x["dt_obj"], reverse=True)
    return unici


def _parse_rss_data(xml_content):
    root = ET.fromstring(xml_content.strip())
    out = []
    for item in root.findall(".//item"):
        titolo = item.findtext("title", default="").strip()
        link = item.findtext("link", default="").strip()
        if not titolo or not link:
            continue
        try:
            dt = parsedate_to_datetime(item.findtext("pubDate", default="")).replace(tzinfo=None)
        except Exception:
            dt = datetime.now()

        if dt.year != CURRENT_YEAR:
            continue

        marca = ""
        if " - " in titolo:
            marca, titolo = titolo.split(" - ", 1)

        out.append({
            "Data": dt.strftime("%d/%m/%Y"),
            "dt_obj": dt,
            "Marca": marca,
            "Titolo": titolo,
            "Motivo": item.findtext("description", default="").strip(),
            "Link": link,
        })

    visti = set()
    unici = []
    for item in out:
        if item["Link"] not in visti:
            visti.add(item["Link"])
            unici.append(item)

    unici.sort(key=lambda x: x["dt_obj"], reverse=True)
    return unici


@st.cache_data(ttl=3600, show_spinner="Scarico i richiami dal Ministero...")
def fetch_data_alimentari():
    session = requests.Session()
    session.headers.update(HEADERS)

    # 1. Tentativo con API JSON
    try:
        session.get("https://www.salute.gov.it/new/it/", timeout=5)
        res = session.get(URL_JSON, timeout=10)
        res.raise_for_status()
        
        raw_start = res.content.lstrip()[:10]
        if raw_start.startswith(b"{") or raw_start.startswith(b"["):
            dati = _parse_json_data(res.json())
            if dati:
                return dati
    except Exception:
        pass

    # 2. Fallback automatico a Feed RSS XML
    try:
        res_rss = session.get(URL_RSS, timeout=10)
        res_rss.raise_for_status()
        raw_rss = res_rss.content.lstrip()[:20]
        if raw_rss.startswith(b"<?xml") or raw_rss.startswith(b"<rss"):
            return _parse_rss_data(res_rss.content)
    except Exception:
        pass

    return []


# ==========================================
# 2. FERROTRAMVIARIA
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
# 3. INTERFACCIA UTENTE
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
    col_btn, _ = st.columns([1, 4])
    with col_btn:
        if st.button("🔄 Ricarica Dati"):
            st.cache_data.clear()
            st.rerun()

    dati_alim = fetch_data_alimentari()

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
        st.warning("Nessun dato alimentare disponibile al momento. Riprova più tardi o clicca su 'Ricarica Dati'.")
