import re
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
import requests
import bs4
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

# --- Configurazione Pagina Streamlit ---
st.set_page_config(page_title="Dashboard Avvisi & News", page_icon="📢", layout="wide")

CURRENT_YEAR = datetime.now().year
logging.getLogger("urllib3").setLevel(logging.ERROR)

URL_JSON = "https://www.salute.gov.it/new/page-data/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/page-data.json"
URL_RSS = "https://www.salute.gov.it/portale/news/rssRichiami.jsp?tipo=richiami"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.salute.gov.it/new/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/",
}


def _parse_json_data(json_data):
    risultati = []

    def esplora(node):
        if isinstance(node, dict):
            data_raw = node.get("dataPubblicazione") or node.get("field_data_pubblicazione")
            marca = node.get("field_marca")
            title = node.get("title")

            motivo = None
            motivo_obj = node.get("relationships", {}).get("field_motivo_segnalazione")
            if isinstance(motivo_obj, dict):
                motivo = motivo_obj.get("name")

            link = None
            path = node.get("path")
            if isinstance(path, dict):
                alias = path.get("alias")
                if alias:
                    link = "https://www.salute.gov.it/new/it" + alias

            if data_raw and title and link:
                try:
                    dt = datetime.strptime(data_raw, "%d/%m/%Y")
                    if dt.year == CURRENT_YEAR:
                        risultati.append({
                            "Data": data_raw,
                            "dt_obj": dt,
                            "Marca": marca or "",
                            "Titolo": title,
                            "Motivo": motivo or "",
                            "Link": link,
                        })
                except ValueError:
                    pass

            for value in node.values():
                esplora(value)

        elif isinstance(node, list):
            for item in node:
                esplora(item)

    esplora(json_data)

    visti = set()
    unici = []
    for item in risultati:
        if item["Link"] not in visti:
            visti.add(item["Link"])
            unici.append(item)

    unici.sort(key=lambda x: x["dt_obj"], reverse=True)
    return unici


def _parse_rss_data(xml_content):
    root = ET.fromstring(xml_content.strip())
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

        if dt.year != CURRENT_YEAR:
            continue

        marca = ""
        if " - " in titolo:
            marca, titolo = titolo.split(" - ", 1)

        out.append({
            "Data": dt.strftime("%d/%m/%Y"),
            "dt_obj": dt,
            "Marca": marca,
            "Titolo": titolo,
            "Motivo": item.findtext("description", default="").strip(),
            "Link": link,
        })

    visti = set()
    unici = []
    for item in out:
        if item["Link"] not in visti:
            visti.add(item["Link"])
            unici.append(item)

    unici.sort(key=lambda x: x["dt_obj"], reverse=True)
    return unici


@st.cache_data(ttl=3600, show_spinner="Scarico i richiami dal Ministero...")
def fetch_data_alimentari():
    session = requests.Session()
    session.headers.update(HEADERS)

    # Step 1: Pre-warm cookie di sessione WAF
    try:
        session.get("https://www.salute.gov.it/new/it/", timeout=10)
    except Exception:
        pass

    # Step 2: Tentativo recupero JSON
    try:
        res = session.get(URL_JSON, timeout=15)
        res.raise_for_status()

        # Verifica se la risposta è JSON prima di parsare
        raw_start = res.content.lstrip()[:10]
        if raw_start.startswith(b"{") or raw_start.startswith(b"["):
            dati = _parse_json_data(res.json())
            if dati:
                return dati
    except Exception:
        pass  # Fallback a RSS se il JSON fallisce o restituisce una pagina HTML WAF

    # Step 3: Fallback a RSS XML
    try:
        res_rss = session.get(URL_RSS, timeout=15)
        res_rss.raise_for_status()
        raw_rss = res_rss.content.lstrip()[:20]
        if raw_rss.startswith(b"<?xml") or raw_rss.startswith(b"<rss"):
            return _parse_rss_data(res_rss.content)
    except Exception as e:
        st.error(f"Impossibile recuperare i dati sia da JSON che da RSS: {e}")

    return []
