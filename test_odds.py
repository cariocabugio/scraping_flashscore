#!/usr/bin/env python3
"""
Teste do feed de odds.
Uso: python test_odds.py <ID_PARTIDA>
"""

import sys
import re
import requests

API_URL = "https://global.flashscore.ninja/401/x/feed/df_od_1_{match_id}_1"
HEADERS = {
    "X-Fsign": "SW9D1eZo",
    "User-Agent": "Mozilla/5.0"
}

def fetch_odds(match_id):
    try:
        resp = requests.get(API_URL.format(match_id=match_id), headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"❌ Erro ao buscar odds: {e}")
        return None

def parse_odds(raw):
    """Extrai odds do feed bruto e imprime as principais."""
    # Cada mercado é precedido por um código (ex: TO÷...)
    # Vamos capturar os mercados comuns: 1X2, Over/Under, Cantos
    markets = re.findall(r'(?:~)?(TO÷[^¬]+)¬(.+?)(?=~TO÷|~A1÷|$)', raw, re.DOTALL)
    for header, body in markets:
        market_name = header.replace('TO÷', '')
        print(f"\n📊 {market_name}")
        # Extrai cotações individuais (ex: OC÷bet365:1.85)
        odds = re.findall(r'OC÷([^:]+):([0-9.]+)', body)
        for bookmaker, odd in odds[:3]:  # mostra até 3 casas
            print(f"  {bookmaker}: {odd}")

def main():
    if len(sys.argv) < 2:
        print("Uso: python test_odds.py <ID_PARTIDA>")
        return
    mid = sys.argv[1]
    print(f"🔍 Buscando odds para {mid}...")
    raw = fetch_odds(mid)
    if raw:
        parse_odds(raw)

if __name__ == '__main__':
    main()