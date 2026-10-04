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
        "Chrome/128.0.0.0 Safari/537.36"
    )
}

URL_MINISTERO = "https://www.salute.gov.it/new/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/"

# ==========================================
# RICHIAMI ALIMENTARI (Rendering Completo)
# ==========================================

def _fetch_jina_full():
    """Scarica il dom completo già renderizzato con tutti i link ai richiami."""
    risultati = []
    jina_url = f"https://r.jina.ai/{URL_MINISTERO}"
    
    response = requests.get(jina_url, headers={"X-With-Generated-Alt": "true"}, timeout=25)
    if response.status_code == 200:
        lines = response.text.split("\n")
        for line in lines:
            # Trova i link delle schede dei richiami
            matches = re.findall(r'\[([^\]]+)\]\((https?://www\.salute\.gov\.it[^\)]+)\)', line)
            for titolo_raw, link in matches:
                if any(k in link for k in ["ext-avviso-sicurezza-alimentare", "richiama", "avviso"]):
                    match_data = re.search(r"\b\d{2}/\d{2}/\d{4}\b", titolo_raw)
                    data_str = match_data.group(0) if match_data else datetime.now().strftime("%d/%m/%Y")
                    
                    marca = "Ministero Salute"
                    titolo = titolo_raw
                    if " - " in titolo_raw:
                        parti = titolo_raw.split(" - ", 1)
                        marca, titolo = parti[0].strip(), parti[1].strip()

                    if not any(r["Link"] == link for r in risultati):
                        risultati.append({
                            "Data": data_str,
                            "Marca": marca,
                            "Titolo": titolo,
                            "Motivo": "Richiamo per rischio sanitario / alimentare",
                            "Link": link
                        })
    return risultati


def _fetch_aggregator_backup():
    """Aggregatore di backup per garantire la lista completa se il Ministero va in timeout."""
    risultati = []
    try:
        resp = requests.get("https://richiamialimenti.it/", headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                texto = a.get_text(strip=True)
                if "/richiamo-" in href or "/avviso-" in href or "Richiamo" in texto:
                    if len(texto) > 10:
                        risultati.append({
                            "Data": datetime.now().strftime("%d/%m/%Y"),
                            "Marca": "Richiamo Alimentare",
                            "Titolo": texto,
                            "Motivo": "Richiamo prodotto alimentari",
                            "Link": href if href.startswith("http") else f"https://richiamialimenti.it{href}"
                        })
    except Exception:
        pass
    return risultati


@st.cache_data(ttl=1800, show_spinner="Caricamento di tutti i richiami alimentari...")
def fetch_data_alimentari():
    # Tentativo 1: Renderizzato con Jina (Ministero della Salute completo)
    try:
        data = _fetch_jina_full()
        if len(data) > 1:
            return data
    except Exception:
        pass

    # Tentativo 2: Backup da aggregatore ufficiale
    try:
        data_bg = _fetch_aggregator_backup()
        if len(data_bg) > 1:
            return data_bg
    except Exception:
        pass

    # Fallback sicuro
    return [{
        "Data": datetime.now().strftime("%d/%m/%Y"),
        "Marca": "Ministero della Salute",
        "Titolo": "Consulta il portale del Ministero per la lista completa aggiornata",
        "Motivo": "Consultazione diretta",
        "Link": URL_MINISTERO
    }]


# ==========================================
# FERROTRAMVIARIA
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
                if not link.startswith("http"):
                    link = "https://www.ferrotramviaria.it" + link
                titolo = re.sub(r"(sciopero)", r'<span style="color:red; font-weight:bold;">\1</span>', title_tag.get_text(strip=True), flags=re.IGNORECASE)
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
            link_tag = article.find("a", class_="nav-link", href=True)
            if title_tag and link_tag:
                link = link_tag["href"]
                if link.startswith("/"):
                    link = "https://www.ferrotramviaria.it" + link
                news.append({"titolo": title_tag.get_text(strip=True), "link": link})
        return news
    except Exception:
        return []


# ==========================================
# STREAMLIT UI
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
            df["Marca"].astype(str).str.contains(search_query, case=False, na=False)
            | df["Titolo"].astype(str).str.contains(search_query, case=False, na=False)
            | df["Motivo"].astype(str).str.contains(search_query, case=False, na=False)
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
