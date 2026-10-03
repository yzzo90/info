import os
import re
import logging
import requests
from datetime import datetime
from bs4 import BeautifulSoup
import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET

# --- Configurazione Pagina Streamlit ---
st.set_page_config(
    page_title="Dashboard Avvisi & News",
    page_icon="📢",
    layout="wide"
)

CURRENT_YEAR = datetime.now().year
TODAY = datetime.now().date()

# Disattiva log ridondanti
logging.getLogger('urllib3').setLevel(logging.ERROR)


# ==========================================
# 1. FUNZIONI SCRAPING: SALUTE GOV (Alimentari)
# ==========================================
@st.cache_data(ttl=900)
def fetch_data_alimentari():
    """
    Recupera i richiami alimentari tramite il feed RSS/XML del Ministero della Salute,
    molto meno soggetto a blocchi anti-bot rispetto all'API JSON e alle pagine HTML.
    """
    url_rss = "https://www.salute.gov.it/portale/news/rssRichiami.jsp?tipo=richiami"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8"
    }

    try:
        response = requests.get(url_rss, headers=headers, timeout=12)
        response.raise_for_status()

        # Parse del contenuto XML
        root = ET.fromstring(response.content)
        
        risultati = []
        
        # Gli elementi del feed RSS risiedono sotto channel/item
        for item in root.findall(".//item"):
            titolo = item.findtext("title", default="").strip()
            link = item.findtext("link", default="").strip()
            pub_date_raw = item.findtext("pubDate", default="").strip()
            description = item.findtext("description", default="").strip()

            if not titolo or not link:
                continue

            # Parsing della data RSS (es. "Wed, 04 Oct 2026 10:00:00 GMT" o formato standard)
            dt_obj = datetime.now()
            data_str = TODAY.strftime("%d/%m/%Y")
            
            if pub_date_raw:
                try:
                    # Tenta il formato standard RFC 822 (RSS)
                    from email.utils import parsedate_to_datetime
                    dt_obj = parsedate_to_datetime(pub_date_raw)
                    data_str = dt_obj.strftime("%d/%m/%Y")
                except Exception:
                    pass

            # Tenta di estrarre Marca e Motivo dalla descrizione o dal titolo
            marca = ""
            motivo = description

            if " - " in titolo:
                parti = titolo.split(" - ")
                marca = parti[0]
                titolo = " - ".join(parti[1:])

            risultati.append({
                'Data': data_str,
                'dt_obj': dt_obj,
                'Marca': marca,
                'Titolo': titolo,
                'Motivo': motivo,
                'Link': link
            })

        # Ordina per data decrescente
        risultati.sort(key=lambda x: x['dt_obj'], reverse=True)
        return risultati

    except Exception as e:
        # Fallback in caso di blocco totale: restituisce un messaggio chiaro nella UI
        st.warning(f"Impossibile collegarsi al feed del Ministero: {e}")
        return []

    def esplora(node):
        if isinstance(node, dict):
            data_raw = node.get('dataPubblicazione') or node.get('field_data_pubblicazione')
            marca = node.get('field_marca')
            title = node.get('title')

            motivo = None
            motivo_obj = node.get('relationships', {}).get('field_motivo_segnalazione')
            if isinstance(motivo_obj, dict):
                motivo = motivo_obj.get('name')

            link = None
            path = node.get('path')
            if isinstance(path, dict):
                alias = path.get('alias')
                if alias:
                    link = "https://www.salute.gov.it/new/it" + alias

            if data_raw and title and link:
                try:
                    dt = datetime.strptime(data_raw, '%d/%m/%Y')
                    if dt.year == CURRENT_YEAR:
                        risultati.append({
                            'Data': data_raw,
                            'dt_obj': dt,
                            'Marca': marca or '',
                            'Titolo': title,
                            'Motivo': motivo or '',
                            'Link': link
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
        if item['Link'] not in visti:
            visti.add(item['Link'])
            unici.append(item)

    unici.sort(key=lambda x: x['dt_obj'], reverse=True)
    return unici


# ==========================================
# 2. FUNZIONI SCRAPING: FERROTRAMVIARIA
# ==========================================
URL_AVVISI = "https://www.ferrotramviaria.it/web/guest/avvisi"
URL_NEWS = "https://www.ferrotramviaria.it/web/guest/news"

@st.cache_data(ttl=900)
def estrai_avvisi_ferrovia():
    try:
        response = requests.get(URL_AVVISI, timeout=10)
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

                # Evidenziazione keyword sciopero per rendering markdown/HTML
                titolo_formatted = re.sub(r'(sciopero)', r'<span style="color:red; font-weight:bold;">\1</span>', titolo_raw, flags=re.IGNORECASE)

                avvisi.append({"titolo": titolo_formatted, "link": link})

        return avvisi
    except Exception as e:
        st.error(f"Errore nel recupero avvisi Ferrotramviaria: {e}")
        return []

@st.cache_data(ttl=900)
def estrai_news_ferrovia():
    try:
        response = requests.get(URL_NEWS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        news = []
        for article in soup.find_all("div", class_="article"):
            title_tag = article.find("div", class_="article-title")
            title = title_tag.get_text(strip=True) if title_tag else "–"
            link_tag = article.find("a", class_="nav-link", href=True)
            link = link_tag["href"] if link_tag else "#"

            if link.startswith("/"):
                link = "https://ferrotramviaria.it" + link

            news.append({"titolo": title, "link": link})
        return news
    except Exception as e:
        st.error(f"Errore nel recupero news Ferrotramviaria: {e}")
        return []


# ==========================================
# 3. INTERFACCIA UTENTE (STREAMLIT)
# ==========================================
st.title("📌 Centro Info")

# Definizione dei due tab centrali (Ferrotramviaria è il primo, quindi si apre di default)
tab_ferrovia, tab_alimentare = st.tabs(["🚆 Ferrotramviaria (News & Avvisi)", "🥗 Avvisi Alimentari"])

# --- TAB 1: FERROTRAMVIARIA (DEFAULT) ---
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

# --- TAB 2: AVVISI ALIMENTARI ---
with tab_alimentare:
    dati_alim = fetch_data_alimentari()

    st.subheader(f"Avvisi Sicurezza Alimentare - {len(dati_alim)} risultati (Anno {CURRENT_YEAR})")

    if dati_alim:
        df = pd.DataFrame(dati_alim)

        # Campo di ricerca per filtrare la tabella
        search_query = st.text_input("🔍 Cerca nei richiami alimentari (marca, prodotto, motivo...):", "")

        if search_query:
            df = df[
                df['Marca'].str.contains(search_query, case=False, na=False) |
                df['Titolo'].str.contains(search_query, case=False, na=False) |
                df['Motivo'].str.contains(search_query, case=False, na=False)
            ]

        # Seleziona e ordina le colonne da visualizzare
        df_display = df[['Data', 'Marca', 'Titolo', 'Motivo', 'Link']]

        # Rendering della tabella interattiva con link cliccabili
        st.dataframe(
            df_display,
            column_config={
                "Link": st.column_config.LinkColumn("Link Scheda", display_text="Apri")
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("Nessun dato alimentari disponibile.")
