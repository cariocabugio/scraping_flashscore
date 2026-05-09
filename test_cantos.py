#!/usr/bin/env python3
"""
Teste de extração de escanteios ao vivo.
Uso: python test_cantos.py <ID_PARTIDA>
"""

import sys
import re
import requests

API_URL = "https://global.flashscore.ninja/401/x/feed/df_st_1_{match_id}"
HEADERS = {
    "X-Fsign": "SW9D1eZo",
    "User-Agent": "Mozilla/5.0"
}

def fetch_live_stats(match_id):
    try:
        resp = requests.get(API_URL.format(match_id=match_id), headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"❌ Erro ao buscar dados ao vivo: {e}")
        return None

def main():
    if len(sys.argv) < 2:
        print("Uso: python test_cantos.py <ID_PARTIDA>")
        return

    match_id = sys.argv[1]
    print(f"🔍 Buscando estatísticas ao vivo para partida {match_id}...")
    raw = fetch_live_stats(match_id)
    if not raw:
        return

    # Extrair escanteios
    match = re.search(r'Escanteios¬SH÷(\d+)¬SI÷(\d+)', raw)
    if match:
        home = int(match.group(1))
        away = int(match.group(2))
        total = home + away
        print(f"⚽ Escanteios - Casa: {home}, Fora: {away}, Total: {total}")
        print(f"   Over 8.5 → {'✅' if total > 8.5 else '❌'}")
        print(f"   Over 9.5 → {'✅' if total > 9.5 else '❌'}")
        print(f"   Over 10.5 → {'✅' if total > 10.5 else '❌'}")
    else:
        print("⚠️ Feed recebido, mas não contém dados de escanteios (partida pode não ter começado).")

if __name__ == '__main__':
    main()