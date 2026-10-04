import re
import logging
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

# ==========================================
# 0. CONFIGURAZIONE GENERALE
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
URL_HTML_ALIMENTI = (
    "https://www.salute.gov.it/new/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/"
)

def _fetch_da_html(session):
    """Esegue lo scraping direttamente dall'indice del portale del Ministero."""
    resp = session.get(URL_HTML_ALIMENTI, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    risultati = []

    # Cerca i link relativi alle schede di richiamo
    cards = soup.select("a[href*='ext-avviso-sicurezza-alimentare']")
    
    # Fallback se la struttura HTML delle classi cambia leggermente
    if not cards:
        cards = [
            a for a in soup.find_all("a", href=True) 
            if "/avvisi/" in a["href"] or "richiam" in a["href"]
        ]

    for card in cards:
        link = card.get("href", "")
        if not link.startswith("http"):
            link = "https://www.salute.gov.it" + link

        # Cerca elementi del titolo
        titolo_el = card.find(
            ["h3", "h4", "p", "div", "span"],
            class_=re.compile(r"title|titolo|heading|name", re.I),
        )
        titolo_testo = (
            titolo_el.get_text(strip=True) if titolo_el else card.get_text(strip=True)
        )

        # Cerca la data pubblicazione nel testo
        data_str = ""
        dt_obj = datetime.now()
        data_match = re.search(r"\b\d{2}/\d{2}/\d{4}\b", card.get_text())
        if data_match:
            data_str = data_match.group(0)
            try:
                dt_obj = datetime.strptime(data_str, "%d/%m/%Y")
            except ValueError:
                pass

        if titolo_testo and link:
            marca = ""
            titolo = titolo_testo
            if " - " in titolo_testo:
                parti = titolo_testo.split(" - ", 1)
                marca, titolo = parti[0], parti[1]

            risultati.append({
                "Data": data_str or dt_obj.strftime("%d/%m/%Y"),
                "dt_obj": dt_obj,
                "Marca": marca,
                "Titolo": titolo,
                "Motivo": "Richiamo per rischio sanitario / alimentare",
                "Link": link,
            })

    # Rimuovi duplicati basandoti sul link
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

    # 1. Scraping HTML dall'indice ufficiale del Ministero
    try:
        session.get("https://www.salute.gov.it/new/it/", timeout=5)
        dati = _fetch_da_html(session)
        if dati:
            return dati
    except Exception as e:
        st.warning(f"Errore durante lo scraping dell'indice HTML: {e}")

    # 2. Fallback facoltativo via API JSON Gatsby
    try:
        res = session.get(
            "https://www.salute.gov.it/new/page-data/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/page-data.json",
            timeout=10,
        )
        if res.status_code == 200 and res.content.lstrip().startswith((b"{", b"[")):
            json_data = res.json()
            risultati_json = []

            def esplora(node):
                if isinstance(node, dict):
                    data_raw = node.get("dataPubblicazione") or node.get("field_data_pubblicazione")
                    title = node.get("title")
                    path = node.get("path")
                    alias = path.get("alias") if isinstance(path, dict) else None

                    if data_raw and title and alias:
                        link = "https://www.salute.gov.it/new/it" + alias
                        try:
                            dt = datetime.strptime(data_raw, "%d/%m/%Y")
                            if dt.year == CURRENT_YEAR:
                                risultati_json.append({
                                    "Data": data_raw,
                                    "dt_obj": dt,
                                    "Marca": node.get("field_marca") or "",
                                    "Titolo": title,
                                    "Motivo": "Richiamo alimentare",
                                    "Link": link,
                                })
                        except ValueError:
                            pass

                    for v in node.values():
                        esplora(v)
                elif isinstance(node, list):
                    for item in node:
                        esplora(item)

            esplora(json_data)
            if risultati_json:
                return sorted(risultati_json, key=lambda x: x["dt_obj"], reverse=True)
    except Exception:
        pass

    return []

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
st.title("📌 Centro Info: Ferrotramviaria & Sicurezza Alimentare")

tab_ferrovia, tab_alimentare = st.tabs(
    ["Dati Ferrotramviaria", "Avvisi Alimentari"]
)

with tab_ferrovia:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔔 Avvisi Ferrotramviaria")
        avvisi_ft = estrai_avvisi_ferrovia()
        if avvisi_ft:
            for idx, item in enumerate(avvisi_ft, 1):
                st.markdown(
                    f"{idx}. [{item['titolo']}]({item['link']})", 
                    unsafe_allow_html=True
                )
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

        st.subheader(f"Avvisi Sicurezza Alimentare - {len(df)} risultati")

        st.dataframe(
            df[["Data", "Marca", "Titolo", "Motivo", "Link"]],
            column_config={
                "Link": st.column_config.LinkColumn("Link Scheda", display_text="Apri")
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning("Nessun dato alimentare disponibile al momento. Clicca su 'Ricarica Dati' per riprovare.")
