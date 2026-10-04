import re
import logging
import requests
import xml.etree.ElementTree as ET
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ==========================================
# 1. RICHIAMI ALIMENTARI (Feed Ufficiale RSS XML)
# ==========================================

URL_RSS_MINISTERO = "http://www.salute.gov.it/portale/news/RSS_avvisi_richiami_osa.xml"

@st.cache_data(ttl=900, show_spinner="Caricamento richiami alimentari ufficiali...")
def fetch_data_alimentari():
    risultati = []
    
    # 1. Tentativo tramite Feed RSS Ufficiale del Ministero della Salute
    try:
        response = requests.get(URL_RSS_MINISTERO, headers=HEADERS, timeout=12)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            for item in root.findall(".//item"):
                titolo_raw = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                desc = item.find("description").text if item.find("description") is not None else ""

                # Format data
                data_str = pub_date[:16] if pub_date else datetime.now().strftime("%d/%m/%Y")

                # Estrazione Marca e Prodotto dal Titolo
                marca = "Ministero della Salute"
                titolo = titolo_raw
                if " - " in titolo_raw:
                    parti = titolo_raw.split(" - ", 1)
                    marca, titolo = parti[0].strip(), parti[1].strip()
                elif ":" in titolo_raw:
                    parti = titolo_raw.split(":", 1)
                    marca, titolo = parti[0].strip(), parti[1].strip()

                motivo = BeautifulSoup(desc, "html.parser").get_text(strip=True) if desc else "Richiamo per rischio sanitario / alimentare"
                if not motivo or len(motivo) < 5:
                    motivo = "Avviso ufficiale di sicurezza alimentare"

                risultati.append({
                    "Data": data_str,
                    "Marca": marca,
                    "Titolo": titolo,
                    "Motivo": motivo,
                    "Link": link
                })
    except Exception:
        pass

    # 2. Backup di sicurezza su aggregatore se il feed non restituisce dati
    if not risultati:
        try:
            resp = requests.get("https://richiamialimenti.it/", headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    texto = a.get_text(strip=True)
                    if "richiamo" in href or "ritiro" in href or "Richiamo" in texto:
                        if len(texto) > 15:
                            link_comp = href if href.startswith("http") else f"https://richiamialimenti.it{href}"
                            risultati.append({
                                "Data": datetime.now().strftime("%d/%m/%Y"),
                                "Marca": "Richiamo Alimentare",
                                "Titolo": texto,
                                "Motivo": "Richiamo di sicurezza alimentare",
                                "Link": link_comp
                            })
        except Exception:
            pass

    # 3. Fallback di sicurezza con scheda istituzionale
    if not risultati:
        risultati.append({
            "Data": datetime.now().strftime("%d/%m/%Y"),
            "Marca": "Ministero della Salute",
            "Titolo": "Consultazione Portale Ministero della Salute",
            "Motivo": "Accedi al sito istituzionale",
            "Link": "https://www.salute.gov.it/new/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/"
        })

    return risultati


# ==========================================
# 2. FERROTRAMVIARIA (Avvisi & News)
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
# 3. INTERFACCIA UTENTE STREAMLIT
# ==========================================
st.title("📌 Dashboard Avvisi Ferrotramviaria & Sicurezza Alimentare")

tab_ferrovia, tab_alimentare = st.tabs(
    ["Dati Ferrotramviaria", "Avvisi Alimentari"]
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
