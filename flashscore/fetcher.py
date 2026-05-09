import re
import requests

API_URL_H2H = "https://global.flashscore.ninja/401/x/feed/df_hh_1_{match_id}"
HEADERS = {"X-Fsign": "SW9D1eZo", "User-Agent": "Mozilla/5.0"}

def fetch_feed(url_template: str, match_id: str):
    try:
        resp = requests.get(url_template.format(match_id=match_id), headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text
    except:
        return None

def load_raw_h2h(source: str):
    # Tenta arquivo local
    try:
        with open(source, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'SA÷1¬~' in content:
                return content
    except FileNotFoundError:
        pass
    # ID puro
    if re.match(r'^[a-zA-Z0-9]{8}$', source):
        return fetch_feed(API_URL_H2H, source)
    # Extrai de URL
    mid = re.search(r'([a-zA-Z0-9]{8})', source)
    if mid:
        return fetch_feed(API_URL_H2H, mid.group(1))
    return None

def extract_match_id(source: str):
    if re.match(r'^[a-zA-Z0-9]{8}$', source):
        return source
    m = re.search(r'([a-zA-Z0-9]{8})', source)
    return m.group(1) if m else None