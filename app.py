import re
import random
import logging
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
from zoneinfo import ZoneInfo

# ==========================================
# 0. CONFIGURAZIONE PAGINA & LOGGING
# ==========================================
st.set_page_config(
    page_title="Dashboard", 
    page_icon="📢", 
    layout="wide"
)

logging.getLogger("urllib3").setLevel(logging.ERROR)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

def fetch_url(url):
    """Richiesta HTTP per recuperare i contenuti HTML dell'app o dei siti esterni."""
    try:
        resp = requests.get(url, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=10)
        if resp.status_code == 200:
            return resp
    except Exception:
        pass
    return None

# ==========================================
# 1. FERROTRAMVIARIA (Avvisi & News)
# ==========================================
URL_AVVISI = "https://www.ferrotramviaria.it/web/guest/avvisi"
URL_NEWS = "https://www.ferrotramviaria.it/web/guest/news"

KEYWORDS_SCIOPERO = ["sciopero", "agitazione sindacale", "agitazioni sindacali", "astensione dal lavoro"]

def contiene_parole_chiave(testo, parole_chiave):
    testo_lower = testo.lower()
    return any(k.lower() in testo_lower for k in parole_chiave)

def evidenzia_parole_chiave(testo, parole_chiave):
    pattern = r"(" + "|".join([re.escape(k) for k in parole_chiave]) + r")"
    return re.sub(pattern, r'<span style="color:red; font-weight:bold;">\1</span>', testo, flags=re.IGNORECASE)

@st.cache_data(ttl=900)
def estrai_avvisi_ferrovia():
    resp = fetch_url(URL_AVVISI)
    if not resp:
        return []
    
    soup = BeautifulSoup(resp.text, "html.parser")
    avvisi = []
    for div in soup.select("div.notice"):
        link_tag = div.find("a", href=True)
        title_tag = div.find("p", class_="title")
        if link_tag and title_tag:
            link = link_tag["href"]
            titolo_raw = title_tag.get_text(strip=True)
            if not link.startswith("http"):
                link = "https://www.ferrotramviaria.it" + link

            titolo_html = evidenzia_parole_chiave(titolo_raw, KEYWORDS_SCIOPERO)
            is_sciopero = contiene_parole_chiave(titolo_raw, KEYWORDS_SCIOPERO)
            
            avvisi.append({
                "titolo_raw": titolo_raw, 
                "titolo": titolo_html, 
                "link": link,
                "is_sciopero": is_sciopero
            })
    return avvisi

@st.cache_data(ttl=900)
def estrai_news_ferrovia():
    resp = fetch_url(URL_NEWS)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    news = []
    for article in soup.find_all("div", class_="article"):
        title_tag = article.find("div", class_="article-title")
        title_raw = title_tag.get_text(strip=True) if title_tag else "–"
        link_tag = article.find("a", class_="nav-link", href=True)
        link = link_tag["href"] if link_tag else "#"
        if link.startswith("/"):
            link = "https://www.ferrotramviaria.it" + link
            
        titolo_html = evidenzia_parole_chiave(title_raw, KEYWORDS_SCIOPERO)
        is_sciopero = contiene_parole_chiave(title_raw, KEYWORDS_SCIOPERO)
        
        news.append({
            "titolo_raw": title_raw,
            "titolo": titolo_html, 
            "link": link,
            "is_sciopero": is_sciopero
        })
    return news

# ==========================================
# 2. FUNZIONE PER DATI REALTIME JSON & FORMATTAZIONE DATE
# ==========================================
@st.cache_data(ttl=30)
def fetch_realtime_data(cod_sito):
    url = f"https://eticket.ferrovienordbarese.it/b2c/json/realtime/dati?codSito={cod_sito}&type=T"
    try:
        resp = requests.get(url, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None

def format_datetime_value(val):
    if isinstance(val, str) and val.isdigit() and len(val) == 14:
        try:
            dt = datetime.strptime(val, "%Y%m%d%H%M%S")
            return dt.strftime("%H:%M:%S")
        except ValueError:
            pass
    return val

def process_dataframe(df):
    if df is not None and not df.empty:
        for col in df.columns:
            df[col] = df[col].apply(format_datetime_value)
            
            if 'ritardo' in col.lower():
                def clean_delay(val):
                    if val is None or str(val).lower() == 'none' or pd.isna(val):
                        return "0 min"
                    try:
                        num = float(val)
                        if num == 0:
                            return "In orario"
                        else:
                            return f"+{int(num)} min"
                    except ValueError:
                        return val
                df[col] = df[col].apply(clean_delay)
    return df

def highlight_soppressa(row):
    cols_lower = [c.lower() for c in row.index]
    if 'soppressa' in cols_lower:
        val = str(row.iloc[cols_lower.index('soppressa')]).strip().upper()
        if val and val != 'N' and val != 'FALSE':
            return ['background-color: rgba(255, 0, 0, 0.3)'] * len(row)
    return [''] * len(row)

def format_realtime_table(json_data, titolo_sezione):
    st.subheader(titolo_sezione)
    if not json_data:
        st.info("Nessun dato disponibile o errore di connessione al server.")
        return

    try:
        partenze = json_data.get("partenze", json_data.get("prospettoPartenze", []))
        arrivi = json_data.get("arrivi", json_data.get("prospettoArrivi", []))

        tab_p, tab_a = st.tabs(["Partenze", "Arrivi"])

        def clean_and_display_df(raw_data, type_str):
            if not raw_data:
                st.info(f"Nessun dato sugli {type_str.lower()} disponibile.")
                return
            
            df = pd.DataFrame(raw_data)
            time_key = 'partenza' if type_str == 'Partenze' else 'arrivo'
            col_time = next((c for c in df.columns if time_key in c.lower() or 'ora' in c.lower()), df.columns[0])
            
            df['_sort_dt'] = pd.to_datetime(df[col_time].astype(str), format='%Y%m%d%H%M%S', errors='coerce')
            df = df.sort_values(by='_sort_dt', ascending=True).drop(columns=['_sort_dt'])
            
            df = process_dataframe(df)
            
            # Mappatura e selezione colonne essenziali per la massima compattezza su smartphone
            cols_lower = {c.lower(): c for c in df.columns}
            selected_mapping = {}
            
            for c_low, c_orig in cols_lower.items():
                if 'destinazione' in c_low or 'nomedestinazione' in c_low:
                    selected_mapping[c_orig] = 'Destinazione'
                elif time_key in c_low:
                    selected_mapping[c_orig] = 'Orario'
                elif 'ritardo' in c_low:
                    selected_mapping[c_orig] = 'Ritardo'
                elif 'binario' in c_low:
                    selected_mapping[c_orig] = 'Binario'
                elif 'soppressa' in c_low:
                    selected_mapping[c_orig] = 'Soppressa'
                elif c_low == 'numero':
                    selected_mapping[c_orig] = 'Treno'

            if selected_mapping:
                df_compact = df[list(selected_mapping.keys())].rename(columns=selected_mapping)
            else:
                df_compact = df

            styled_df = df_compact.style.apply(highlight_soppressa, axis=1)
            st.dataframe(styled_df, use_container_width=True, hide_index=True)

        with tab_p:
            clean_and_display_df(partenze, "Partenze")

        with tab_a:
            clean_and_display_df(arrivi, "Arrivi")

    except Exception as e:
        st.warning("Impossibile formattare i dati tabulari automaticamente. Ecco i dati grezzi:")
        st.json(json_data)

# ==========================================
# 3. INTERFACCIA STREAMLIT
# ==========================================
st.title("📌 Dashboard")

tab_ferrovia, tab_realtime, tab_alimentare, tab_tracking = st.tabs(
    ["🚆 Ferrotramviaria", "🕒 Realtime Treni", "🥗 Avvisi Alimentari", "📦 Tracking Pacchi"]
)

# --- TAB 1: FERROTRAMVIARIA ---
with tab_ferrovia:
    col_head, col_refresh_ft = st.columns([4, 1])
    with col_refresh_ft:
        if st.button("🚆 Aggiorna", use_container_width=True):
            estrai_avvisi_ferrovia.clear()
            estrai_news_ferrovia.clear()
            st.rerun()

    avvisi_ft = estrai_avvisi_ferrovia()
    news_ft = estrai_news_ferrovia()

    elementi_sciopero = [
        item for item in avvisi_ft + news_ft if item.get("is_sciopero")
    ]

    if elementi_sciopero:
        st.toast("⚠️ Trovati avvisi o news di particolare rilevanza!", icon="⚠️")
        
        with st.popover("⚠️ ATTENZIONE: Avvisi sciopero!", use_container_width=True):
            st.warning(f"Sono stati rilevati **{len(elementi_sciopero)}** avvisi o news rilevanti:")
            for item in elementi_sciopero:
                st.markdown(f"• [{item['titolo_raw']}]({item['link']})")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔔 Avvisi di Servizio")
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
        if news_ft:
            for idx, item in enumerate(news_ft, 1):
                st.markdown(
                    f"{idx}. [{item['titolo']}]({item['link']})", 
                    unsafe_allow_html=True
                )
        else:
            st.info("Nessuna news disponibile al momento.")

# --- TAB 2: REALTIME TRENI ---
with tab_realtime:
    col_rt_head, col_rt_btn = st.columns([4, 1])
    with col_rt_btn:
        if st.button("🔄 Aggiorna Treni", use_container_width=True):
            fetch_realtime_data.clear()
            st.rerun()

    st.markdown("### Tabellone in Tempo Reale")
    
    stazione_scelta = st.selectbox(
        "Seleziona Stazione", 
        options=["Stazione Ruvo (S01160)", "Stazione Europa (S01136)"],
        index=0,
        key="stazione_selezionata"
    )

    @st.fragment(run_every=60)
    def render_realtime_board():
        ora_italiana = datetime.now(ZoneInfo("Europe/Rome")).strftime("%H:%M:%S")
        st.caption(f"Ultimo aggiornamento automatico: {ora_italiana}")
        
        selected = st.session_state.get("stazione_selezionata", "")
        if "Ruvo" in selected:
            data_json = fetch_realtime_data("S01160")
            format_realtime_table(data_json, "Treni in Tempo Reale - Stazione Ruvo")
        else:
            data_json = fetch_realtime_data("S01136")
            format_realtime_table(data_json, "Treni in Tempo Reale - Stazione Europa")

    render_realtime_board()

# --- TAB 3: RICHIAMI ALIMENTARI (WEB APP KOYEB) ---
with tab_alimentare:
    app_url = "https://wrong-aurie-alimenti190-497b0369.koyeb.app/"
    
    col_title, col_btn = st.columns([4, 1])
    with col_btn:
        if st.button("🥗 Aggiorna", use_container_width=True):
            st.rerun()

    res = fetch_url(app_url)
    
    if res and res.text:
        custom_css = """
        <style>
            body, p, div, span, td, th, table {
                color: #ffffff !important;
            }
            table, tr, td {
                background-color: #121212 !important;
            }
            th {
                background-color: #e0e0e0 !important;
                color: #000000 !important;
            }
            a {
                color: #4da6ff !important;
                font-weight: bold !important;
            }
            input, select, textarea {
                color: #000000 !important;
                background-color: #ffffff !important;
            }
        </style>
        """
        html_modificato = custom_css + res.text
        components.html(html_modificato, height=800, scrolling=True)
    else:
        components.iframe(src=app_url, height=800, scrolling=True)

# --- TAB 4: TRACKING PACCHI (LOCALSTORAGE PERSISTENTE) ---
with tab_tracking:
    st.subheader("📦 Gestione Tracking Spedizioni (Persistente in Locale)")

    tracking_html = """
    <div style="font-family: sans-serif; color: #white; padding: 5px;">
        <div style="display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap;">
            <input type="text" id="paccoName" placeholder="Nome / Corriere" style="padding: 8px; border-radius: 4px; border: 1px solid #444; background: #222; color: white; flex: 1; min-width: 150px;">
            <input type="text" id="paccoLink" placeholder="Link di Tracking (URL)" style="padding: 8px; border-radius: 4px; border: 1px solid #444; background: #222; color: white; flex: 2; min-width: 200px;">
            <input type="text" id="paccoStato" placeholder="Stato (es. In transito)" style="padding: 8px; border-radius: 4px; border: 1px solid #444; background: #222; color: white; flex: 1; min-width: 150px;">
            <button onclick="addPacco()" style="padding: 8px 15px; background: #ff4b4b; color: white; border: none; border-radius: 4px; font-weight: bold; cursor: pointer;">➕ Aggiungi</button>
        </div>
        <div id="paccoList"></div>
    </div>

    <script>
        function getPacchi() {
            try {
                return JSON.parse(localStorage.getItem('miei_pacchi_privati') || '[]');
            } catch(e) {
                return [];
            }
        }
        function savePacchi(pacchi) {
            localStorage.setItem('miei_pacchi_privati', JSON.stringify(pacchi));
            renderPacchi();
        }
        function addPacco() {
            let name = document.getElementById('paccoName').value.trim();
            let link = document.getElementById('paccoLink').value.trim();
            let stato = document.getElementById('paccoStato').value.trim() || 'In lavorazione';
            if(!name || !link) {
                alert('Inserisci almeno il nome e il link di tracking!');
                return;
            }
            let pacchi = getPacchi();
            pacchi.push({name, link, stato});
            savePacchi(pacchi);
            document.getElementById('paccoName').value = '';
            document.getElementById('paccoLink').value = '';
            document.getElementById('paccoStato').value = '';
        }
        function deletePacco(index) {
            let pacchi = getPacchi();
            pacchi.splice(index, 1);
            savePacchi(pacchi);
        }
        function renderPacchi() {
            let pacchi = getPacchi();
            let html = '<table style="width:100%; border-collapse: collapse; margin-top: 10px; color: white; background-color: #121212;">';
            html += '<tr style="background-color: #262730;"><th style="border:1px solid #444; padding:10px; text-align:left;">Corriere / Nome</th><th style="border:1px solid #444; padding:10px; text-align:left;">Link Tracking</th><th style="border:1px solid #444; padding:10px; text-align:left;">Stato</th><th style="border:1px solid #444; padding:10px; text-align:center;">Azioni</th></tr>';
            
            if(pacchi.length === 0) {
                html += '<tr><td colspan="4" style="padding: 15px; text-align: center; color: #888;">Nessuna spedizione salvata nel browser.</td></tr>';
            } else {
                pacchi.forEach((p, i) => {
                    html += `<tr>` +
                        `<td style="border:1px solid #444; padding:10px;"><b>${p.name}</b></td>` +
                        `<td style="border:1px solid #444; padding:10px;"><a href="${p.link}" target="_blank" style="color: #4da6ff; text-decoration: underline;">Apri Tracking ↗</a></td>` +
                        `<td style="border:1px solid #444; padding:10px;"><i>${p.stato}</i></td>` +
                        `<td style="border:1px solid #444; padding:10px; text-align:center;"><button onclick="deletePacco(${i})" style="background: transparent; border: none; cursor: pointer; font-size: 16px;" title="Elimina">🗑️</button></td>` +
                        `</tr>`;
                });
            }
            html += '</table>';
            document.getElementById('paccoList').innerHTML = html;
        }
        renderPacchi();
    </script>
    """
    components.html(tracking_html, height=400, scrolling=True)
