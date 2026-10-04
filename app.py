import re
import random
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

logging.getLogger("urllib3").setLevel(logging.ERROR)

# Lista di User-Agent per mascherare le richieste
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

# Configura qui eventuali proxy HTTP/HTTPS (opzionale: es. "http://user:pass@ip:port")
PROXIES_LIST = [
    None,  # Connessione diretta senza proxy come primissimo tentativo
    # Aggiungi qui i tuoi proxy se ne possiedi uno privato:
    # "http://185.199.229.156:7492",
    # "http://45.152.188.212:3128",
]

BASE_URL = "https://www.salute.gov.it"

def get_random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

def fetch_url_with_proxy(url):
    """Tenta la richiesta all'URL ruotando headers e proxy in caso di blocco/timeout."""
    for proxy_url in PROXIES_LIST:
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
        headers = get_random_headers()
        try:
            resp = requests.get(url, headers=headers, proxies=proxies, timeout=10)
            if resp.status_code == 200 and len(resp.text) > 1000:
                return resp.text
        except Exception:
            continue
    return None

# ==========================================
# 1. AVVISI ALIMENTARI (Ministero della Salute)
# ==========================================
URLS_RICHIAMI = [
    "https://www.salute.gov.it/new/it/avvisi-e-richiami-di-prodotti-alimentari",
    "https://www.salute.gov.it/new/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/",
]

def _fetch_da_html():
    risultati = []
    visti_link = set()

    for url in URLS_RICHIAMI:
        html_content = fetch_url_with_proxy(url)
        if not html_content:
            continue

        soup = BeautifulSoup(html_content, "html.parser")
        links = soup.find_all("a", href=True)

        for a_tag in links:
            href = a_tag["href"].strip()
            testo = a_tag.get_text(separator=" ", strip=True)

            if not any(k in href for k in ["ext-avviso-sicurezza-alimentare", "/avvisi/", "richiam"]):
                continue

            if any(x in testo.lower() for x in ["portale ufficiale", "consultazione diretta", "home", "cerca"]):
                continue

            full_link = href if href.startswith("http") else BASE_URL + (href if href.startswith("/") else "/" + href)

            if full_link in visti_link:
                continue
            visti_link.add(full_link)

            # Estrattore data
            data_str = ""
            dt_obj = datetime.min
            match_data = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", testo)
            if match_data:
                data_str = match_data.group(1)
                try:
                    dt_obj = datetime.strptime(data_str, "%d/%m/%Y")
                except ValueError:
                    pass

            marca = ""
            titolo = testo
            if " - " in testo:
                parti = testo.split(" - ", 1)
                marca = parti[0].strip()
                titolo = parti[1].strip()

            if not marca:
                marca = "Ministero della Salute"

            risultati.append({
                "Data": data_str or "N/D",
                "dt_obj": dt_obj,
                "Marca": marca,
                "Titolo": titolo,
                "Motivo": "Richiamo per rischio sanitario / alimentare",
                "Link": full_link,
            })

        if risultati:
            break

    risultati.sort(key=lambda x: x["dt_obj"], reverse=True)
    return risultati


@st.cache_data(ttl=1800, show_spinner="Caricamento richiami alimentari con proxy/headers...")
def fetch_data_alimentari():
    return _fetch_da_html()


# ==========================================
# 2. FERROTRAMVIARIA (Avvisi & News)
# ==========================================
URL_AVVISI = "https://www.ferrotramviaria.it/web/guest/avvisi"
URL_NEWS = "https://www.ferrotramviaria.it/web/guest/news"

@st.cache_data(ttl=900)
def estrai_avvisi_ferrovia():
    html_content = fetch_url_with_proxy(URL_AVVISI)
    if not html_content:
        return []
    
    soup = BeautifulSoup(html_content, "html.parser")
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

@st.cache_data(ttl=900)
def estrai_news_ferrovia():
    html_content = fetch_url_with_proxy(URL_NEWS)
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "html.parser")
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
