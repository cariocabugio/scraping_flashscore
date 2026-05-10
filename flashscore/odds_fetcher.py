"""
Módulo para buscar odds via GraphQL.
Uso:
    from flashscore.odds_fetcher import fetch_all_bookmakers
    odds = fetch_all_bookmakers("vNXlW7ph")
"""

import requests

BOOKMAKERS = {
    "bet365": 16,
    "Betano.br": 574,
    "1xBet": 417,
    "Superbet.br": 933,
}

BASE_URL = "https://global.ds.lsapp.eu/odds/pq_graphql"
HEADERS = {
    "accept": "*/*",
    "referer": "https://www.flashscore.com.br/",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
}

def fetch_odds(event_id: str, bookmaker_id: int, bet_type: str = "HOME_DRAW_AWAY", bet_scope: str = "FULL_TIME") -> dict | None:
    params = {
        "_hash": "ope2",
        "eventId": event_id,
        "bookmakerId": bookmaker_id,
        "betType": bet_type,
        "betScope": bet_scope,
    }
    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return None

def parse_odds_response(data: dict) -> dict[str, float]:
    """Extrai odds 1X2 do JSON de resposta."""
    try:
        odds_block = data["data"]["findPrematchOddsForBookmaker"]
        if not odds_block:
            return {}
        return {
            "home": float(odds_block["home"]["value"]),
            "draw": float(odds_block["draw"]["value"]),
            "away": float(odds_block["away"]["value"]),
        }
    except (KeyError, TypeError, ValueError):
        return {}

def fetch_all_bookmakers(event_id: str) -> dict[str, dict[str, float]]:
    """Retorna um dicionário com as odds de cada casa."""
    result = {}
    for name, bid in BOOKMAKERS.items():
        data = fetch_odds(event_id, bid)
        if data:
            parsed = parse_odds_response(data)
            if parsed:
                result[name] = parsed
    return result