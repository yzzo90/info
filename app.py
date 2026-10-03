import re
import logging
import requests
from datetime import datetime
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET

# --- Configurazione Pagina Streamlit ---
st.set_page_config(page_title="Dashboard Avvisi & News", page_icon="📢", layout="wide")

CURRENT_YEAR = datetime.now().year
logging.getLogger("urllib3").setLevel(logging.ERROR)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,application/xml,text/html,*/*",
    "Accept-Language": "it-IT,it;q=0.9",
}


# ==========================================
# 1. AVVISI ALIMENTARI (Ministero della Salute)
# ==========================================
URL_JSON = "https://www.salute.gov.it/new/page-data/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/page-data.json"
URL_RSS = "https://www.salute.gov.it/portale/news/rssRichiami.jsp?tipo=richiami"


def _get(url, log, nome):
    try:
        r = requests.get(url, headers=HEADERS, timeout=60)
        log.append(f"{nome}: HTTP {r.status_code}, {len(r.content)} byte")
        if r.status_code == 200 and r.content.strip():
            return r
    except Exception as e:
        log.append(f"{nome}: ERRORE {type(e).__name__}: {e}")
    return None


def _parse_json(json_data):
    risultati = []

    def esplora(node):
        if isinstance(node, dict):
            path = node.get("path")
            alias = path.get("alias") if isinstance(path, dict) else None
            g, m, a = node.get("field_giorno"), node.get("field_mese"), node.get("field_anno")

            if alias and node.get("title") and g and m and a:
                try:
                    dt = datetime(int(a), int(m), int(g))
                except (ValueError, TypeError):
                    dt = None

                if dt and dt.year == CURRENT_YEAR:
                    risultati.append({
                        "Data": dt.strftime("%d/%m/%Y"),
                        "dt_obj": dt,
                        "Marca": node.get("field_marca") or "",
                        "Titolo": node.get("field_prodotto") or node["title"],
                        "Motivo": node.get("field_sostanza") or "",
                        "Link": "https://www.salute.gov.it/new/it" + alias,
                    })

            for v in node.values():
                esplora(v)
        elif isinstance(node, list):
            for i in node:
                esplora(i)

    esplora(json_data)
    unici = {r["Link"]: r for r in risultati}.values()
    return sorted(unici, key=lambda x: x["dt_obj"], reverse=True)


def _parse_rss(content):
    root = ET.fromstring(content.strip())
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
        marca = ""
        if " - " in titolo:
            marca, titolo = titolo.split(" - ", 1)
        out.append({
            "Data": dt.strftime("%d/%m/%Y"), "dt_obj": dt, "Marca": marca,
            "Titolo": titolo, "Motivo": item.findtext("description", default="").strip(),
            "Link": link,
        })
    return sorted(out, key=lambda x: x["dt_obj"], reverse=True)


@st.cache_data(ttl=3600, show_spinner="Scarico i richiami dal Ministero...")
def _fetch_alimentari_cached():
    # Se fallisce solleva un'eccezione: Streamlit NON mette in cache gli errori
    log = []

    r = _get(URL_JSON, log, "JSON")
    if r is not None:
        try:
            dati = _parse_json(r.json())
            log.append(f"JSON parsato: {len(dati)} record (anno {CURRENT_YEAR})")
            if dati:
                return dati, log
        except Exception as e:
            log.append(f"JSON parsing ERRORE: {e}")

    r = _get(URL_RSS, log, "RSS")
    if r is not None:
        try:
            dati = _parse_rss(r.content)
            log.append(f"RSS parsato: {len(dati)} record")
            if dati:
                return dati, log
        except Exception as e:
            log.append(f"RSS parsing ERRORE: {e}")

    raise RuntimeError("\n".join(log))


def fetch_data_alimentari():
    try:
        return _fetch_alimentari_cached()
    except RuntimeError as e:
        return [], str(e).split("\n")


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
    dati_alim, log_alim = fetch_data_alimentari()

    with st.expander("🛠️ Log recupero dati"):
        st.code("\n".join(log_alim))
        if st.button("Svuota cache e riprova"):
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
            column_config={"Link": st.column_config.LinkColumn("Link Scheda", display_text="Apri")},
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning("Nessun dato alimentare disponibile al momento. Controlla il log qui sopra.")
