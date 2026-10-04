import re
import logging
import requests
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
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ==========================================
# 1. RICHIAMI ALIMENTARI (Estrazione diretta)
# ==========================================

def _estrai_richiami_realtime():
    """Estrae l'elenco completo dei richiami alimentari ufficiali in Italia."""
    risultati = []
    
    # 1. Scraping dal portale italiano aggregatore di richiami ufficiali
    url_richiami = "https://richiamialimenti.it/"
    try:
        resp = requests.get(url_richiami, headers=HEADERS, timeout=12)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Trova tutti i link e gli articoli contenenti richiami
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                testo = a_tag.get_text(strip=True)
                
                # Se è una scheda di richiamo
                if ("richiamo-" in href or "ritiro-" in href or "/avviso-" in href or "Richiamo" in testo) and len(testo) > 15:
                    link_completo = href if href.startswith("http") else f"https://richiamialimenti.it{href.lstrip('/')}"
                    
                    # Estrazione Marca e Prodotto dal testo del link o titolo
                    marca = "Ministero Salute / OSA"
                    titolo = testo
                    
                    if "Marchio:" in testo:
                        parti = testo.split("Marchio:", 1)
                        titolo = parti[0].replace("Richiamo", "").strip()
                        marca = parti[1].strip()
                    elif ":" in testo:
                        parti = testo.split(":", 1)
                        marca = parti[0].strip()
                        titolo = parti[1].strip()
                    elif " - " in testo:
                        parti = testo.split(" - ", 1)
                        marca = parti[0].strip()
                        titolo = parti[1].strip()

                    # Cerca eventuale data nel formato GG/MM/AAAA
                    match_data = re.search(r"\b\d{2}/\d{2}/\d{4}\b", testo)
                    data_str = match_data.group(0) if match_data else datetime.now().strftime("%d/%m/%Y")

                    if not any(r["Link"] == link_completo for r in risultati):
                        risultati.append({
                            "Data": data_str,
                            "Marca": marca,
                            "Titolo": titolo,
                            "Motivo": "Rischio sanitario / Microbiologico / Allergeni",
                            "Link": link_completo
                        })
    except Exception:
        pass

    return risultati


@st.cache_data(ttl=900, show_spinner="Caricamento tutti i richiami alimentari...")
def fetch_data_alimentari():
    dati = _estrai_richiami_realtime()
    
    # Se per qualche motivo lo scraping da 0 elementi, restituiamo un elenco informativo
    if not dati:
        return [{
            "Data": datetime.now().strftime("%d/%m/%Y"),
            "Marca": "Ministero della Salute",
            "Titolo": "Sito Ufficiale Richiami Alimentari",
            "Motivo": "Consultazione diretta delle schede di richiamo",
            "Link": "https://www.salute.gov.it/new/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/"
        }]
    
    return dati


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
