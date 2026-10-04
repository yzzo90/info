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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
}

# ==========================================
# 1. AVVISI ALIMENTARI (Ministero della Salute)
# ==========================================
BASE_URL = "https://www.salute.gov.it"
RICHIAMI_PAGINATED_URL = "https://www.salute.gov.it/new/it/avvisi-e-richiami-di-prodotti-alimentari?pagina={}"

def _fetch_da_html(session, max_pagine=3):
    """
    Raccoglie i richiami alimentari navigando su più pagine ed entrando nei dettagli.
    """
    risultati = []
    visti_link = set()

    for pagina in range(1, max_pagine + 1):
        url_pagina = RICHIAMI_PAGINATED_URL.format(pagina)
        try:
            resp = session.get(url_pagina, timeout=12)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Seleziona solo i link che puntano a vere schede di richiamo
            cards = soup.find_all("a", href=re.compile(r"/ext-avviso-sicurezza-alimentare/", re.I))

            for card in cards:
                link = card.get("href", "")
                if not link.startswith("http"):
                    link = BASE_URL + link

                if link in visti_link:
                    continue
                visti_link.add(link)

                # Estrazione testo del blocco per estrarre informazioni chiave
                testo_card = card.get_text(separator=" ", strip=True)
                
                # Ignora link generici o di navigazione del ministero
                if "portale ufficiale" in testo_card.lower() or "consultazione diretta" in testo_card.lower():
                    continue

                # Estrazione Data
                match_data = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", testo_card)
                data_str = match_data.group(1) if match_data else ""
                
                dt_obj = datetime.min
                if data_str:
                    try:
                        dt_obj = datetime.strptime(data_str, "%d/%m/%Y")
                    except ValueError:
                        pass

                # Pulizia Titolo e Marca
                marca = ""
                titolo = testo_card

                # Prova ad estrarre marca e titolo basandoti sulla struttura HTML del blocco
                marca_el = card.find(class_=re.compile(r"marca|brand|company", re.I))
                titolo_el = card.find(class_=re.compile(r"title|titolo|denominazione", re.I))

                if marca_el:
                    marca = marca_el.get_text(strip=True)
                if titolo_el:
                    titolo = titolo_el.get_text(strip=True)

                if not marca and " - " in testo_card:
                    parti = testo_card.split(" - ")
                    if len(parti) >= 2:
                        marca = parti[0].strip()
                        titolo = " - ".join(parti[1:]).strip()

                # Se non c'è una data visibile nella card, usa la data corrente di fallback
                if not data_str and dt_obj == datetime.min:
                    dt_obj = datetime.now()
                    data_str = dt_obj.strftime("%d/%m/%Y")

                risultati.append({
                    "Data": data_str,
                    "dt_obj": dt_obj,
                    "Marca": marca or "N/D",
                    "Titolo": titolo or "Avviso di Sicurezza Alimentare",
                    "Motivo": "Richiamo per rischio sanitario / alimentare",
                    "Link": link,
                })

        except Exception as e:
            logging.error(f"Errore nel recupero della pagina {pagina}: {e}")
            continue

    # Ordina i risultati per data decrescente (i più recenti prima)
    risultati.sort(key=lambda x: x["dt_obj"], reverse=True)
    return risultati


@st.cache_data(ttl=1800, show_spinner="Caricamento richiami alimentari...")
def fetch_data_alimentari():
    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        session.get("https://www.salute.gov.it/new/it/", timeout=5)
    except Exception:
        pass

    # Impostiamo max_pagine=5 per recuperare più record (es. 20-30 elementi)
    return _fetch_da_html(session, max_pagine=5)


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

# --- TAB 2: RICHIAMI ALIMENTARI ---
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

        st.subheader(f"Richiami e Avvisi Sanitari ({len(df)})")

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
