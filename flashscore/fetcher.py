import re
import requests
from datetime import datetime, timedelta, timezone

API_URL_H2H = "https://global.flashscore.ninja/401/x/feed/df_hh_1_{match_id}"
HEADERS = {"X-Fsign": "SW9D1eZo", "User-Agent": "Mozilla/5.0"}
DEFAULT_COUNTRY = "39"

# ------------------------------------------------------------
# Funções originais (mantidas para compatibilidade)
# ------------------------------------------------------------

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

# ------------------------------------------------------------
# Novas funções – extração de jogos futuros (torreio / classificação)
# ------------------------------------------------------------

def extract_upcoming_from_standings(raw: str, days=1) -> str:
    """
    Extrai IDs de partidas futuras de um feed de classificação.
    Retorna uma string com "AA÷{id}¬" para cada partida dentro do período especificado.
    days: 0 = hoje, 1 = amanhã, 'all' = todas as partidas futuras.
    """
    now = datetime.now(timezone.utc)
    if days == 'all':
        ids = re.findall(r'LMU÷upcoming.*?LME÷(\w{8})', raw)
        return "".join(f"AA÷{mid}¬" for mid in ids)

    start = (now if days == 0 else now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    start_ts, end_ts = int(start.timestamp()), int(end.timestamp()) - 1
    ids = [m.group(1) for m in re.finditer(r'LMU÷upcoming.*?LME÷(\w{8})\s*.*?LMC÷(\d{10})', raw, re.DOTALL)
           if start_ts <= int(m.group(2)) <= end_ts]
    return "".join(f"AA÷{mid}¬" for mid in ids)

def try_fetch_tournament(source: str, days=1) -> str | None:
    """
    Tenta obter os IDs de partidas de um torneio.
    source pode ser:
      - 'url:...'        : URL direta do feed de classificação
      - 'file:...'       : caminho de arquivo local com o feed
      - 'COUNTRY:TOURNAMENT' (ex: '39:vRtLP6rs')
      - apenas TOURNAMENT (assume país padrão 39)
    Retorna string compatível com extract_match_ids() ou None.
    """
    # --- URL fornecida diretamente ---
    if source.startswith("url:"):
        url = source[4:]
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200 and len(resp.text) > 100:
                return extract_upcoming_from_standings(resp.text, days)
        except:
            pass
        return None

    # --- Arquivo local ---
    if source.startswith("file:"):
        path = source[5:]
        try:
            with open(path, encoding='utf-8') as f:
                return extract_upcoming_from_standings(f.read(), days)
        except:
            pass
        return None

    # --- Código COUNTRY:TOURNAMENT ou só TOURNAMENT ---
    if ':' in source:
        country, tour = source.split(':', 1)
    else:
        country, tour = DEFAULT_COUNTRY, source

    # Tenta os dois formatos de URL mais comuns
    urls = [
        f"https://global.flashscore.ninja/401/x/feed/t_1_{country}_{tour}_-3_pt-br_1",
        f"https://global.flashscore.ninja/401/x/feed/to_{country}_{tour}_1",
    ]
    for url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200 and len(resp.text) > 50:
                return extract_upcoming_from_standings(resp.text, days)
        except:
            continue
    return None

def extract_match_ids(raw: str) -> list[str]:
    """Extrai IDs únicos de partidas a partir da string gerada por extract_upcoming_from_standings."""
    return list(set(re.findall(r'AA÷(\w{8})', raw)))