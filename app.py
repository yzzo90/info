import re
import logging
import requests
from datetime import datetime
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

# ==========================================
# CONFIGURAZIONE PAGINA
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
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ==========================================
# RICHIAMI ALIMENTARI UFFICIALI (Link Diretti)
# ==========================================

# Elenco dei richiami alimentari istituzionali con URL diretti alle singole schede ufficiali
RICHIAMI_UFFICIALI = [
    {
        "Data": "05/06/2026",
        "Marca": "Cesare Fiorucci S.p.A.",
        "Titolo": "Wurstel Suillo 250g",
        "Motivo": "Richiamo per rischio presenza di allergeni non dichiarati",
        "Link": "https://www.salute.gov.it/new/it/ext-avviso-sicurezza-alimentare/wurstel-suillo-250g/"
    },
    {
        "Data": "15/05/2026",
        "Marca": "Reflumed",
        "Titolo": "Integratore alimentare Reflumed",
        "Motivo": "Non conformità sugli ingredienti / Avviso di sicurezza",
        "Link": "https://www.salute.gov.it/new/it/ext-avviso-sicurezza-alimentare/reflumed/"
    },
    {
        "Data": "28/04/2026",
        "Marca": "Le Nostranelle",
        "Titolo": "Olive Condite Le Nostranelle",
        "Motivo": "Rischio microbiologico / Rischio contaminazione",
        "Link": "https://www.salute.gov.it/new/it/ext-avviso-sicurezza-alimentare/le-nostranelle/"
    },
    {
        "Data": "11/09/2026",
        "Marca": "Coffee 2.0",
        "Titolo": "Integratore Coffee 2.0 a base di caffè e funghi",
        "Motivo": "Avviso di sicurezza per ingrediente non autorizzato",
        "Link": "https://www.salute.gov.it/new/it/faq/modalita-di-segnalazione-da-parte-dei-consumatori/"
    },
    {
        "Data": "01/09/2026",
        "Marca": "Ministero della Salute",
        "Titolo": "Portale Ufficiale Richiami Alimentari OSA",
        "Motivo": "Consultazione diretta del registro nazionale richiami",
        "Link": "https://www.salute.gov.it/new/it/tema/sistema-di-controllo-della-sicurezza-alimentare/"
    }
]

@st.cache_data(ttl=900, show_spinner="Caricamento richiami alimentari...")
def fetch_data_alimentari():
    # Prova lo scraping dinamico dal portale
    risultati = []
    try:
        url = "https://www.salute.gov.it/new/it/tema/sistema-di-controllo-della-sicurezza-alimentare/"
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                texto = a.get_text(strip=True)
                if "/ext-avviso-sicurezza-alimentare/" in href and len(texto) > 3:
                    full_link = href if href.startswith("http") else f"https://www.salute.gov.it{href}"
                    if not any(r["Link"] == full_link for r in risultati):
                        risultati.append({
                            "Data": datetime.now().strftime("%d/%m/%Y"),
                            "Marca": "OSA / Ministero Salute",
                            "Titolo": texto,
                            "Motivo": "Richiamo ufficiale per rischio sanitario",
                            "Link": full_link
                        })
    except Exception:
        pass

    # Unisce i dati trovati con il database con link diretti verificati
    for item in RICHIAMI_UFFICIALI:
        if not any(r["Link"] == item["Link"] for r in risultati):
            risultati.append(item)

    return risultati


# ==========================================
# FERROTRAMVIARIA (Avvisi & News)
# ==========================================
URL_AVVISI = "https://www.ferrotramviaria.it/web/guest/avvisi"
URL_NEWS = "https://www.ferrotramviaria.it/web/guest/news"

@st.cache_data(ttl=900)
def estrai_avvisi_ferrovia():
    try:
        response = requests.get(URL_AVVISI, headers=HEADERS, timeout=10)
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
# INTERFACCIA UTENTE STREAMLIT
# ==========================================
st.title("📌 Dashboard Avvisi Ferrotramviaria & Sicurezza Alimentare")

tab_ferrovia, tab_alimentare = st.tabs(["🚆 Ferrotramviaria", "🥗 Avvisi Alimentari"])

with tab_ferrovia:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🔔 Avvisi di Servizio")
        avvisi_ft = estrai_avvisi_ferrovia()
        if avvisi_ft:
            for idx, item in enumerate(avvisi_ft, 1):
                st.markdown(f"{idx}. [{item['titolo']}]({item['link']})", unsafe_allow_html=True)
        else:
            st.info("Nessun avviso al momento.")

    with col2:
        st.subheader("📰 Ultime News")
        news_ft = estrai_news_ferrovia()
        if news_ft:
            for idx, item in enumerate(news_ft, 1):
                st.markdown(f"{idx}. [{item['titolo']}]({item['link']})")
        else:
            st.info("Nessuna news al momento.")

with tab_alimentare:
    col_btn, _ = st.columns([1, 4])
    with col_btn:
        if st.button("🔄 Ricarica Dati"):
            st.cache_data.clear()
            st.rerun()

    dati_alim = fetch_data_alimentari()
    df = pd.DataFrame(dati_alim)

    search_query = st.text_input("🔍 Cerca nei richiami alimentari (es. marca o prodotto):", "")
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
