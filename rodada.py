#!/usr/bin/env python3
"""
Gerador de Bilhetes da Rodada – Múltiplos Torneios com Filtros Inteligentes.

Uso:
  python rodada.py <COUNTRY_ID>:<TOURNAMENT_ID> [<COUNTRY_ID>:<TOURNAMENT_ID> ...]
  python rodada.py <TOURNAMENT_ID>                       # assume país 39 (Brasil)

Exemplos:
  python rodada.py 39:vRtLP6rs                           # Série B
  python rodada.py 39:vRtLP6rs 39:lOEwe4o4 81:W6BOzpK2  # Série B + Série A + Bundesliga
"""

import sys
import re
import asyncio
from collections import defaultdict
from itertools import combinations, product
from functools import reduce

import requests
from flashscore.fetcher import fetch_feed, load_raw_h2h, HEADERS
from flashscore.parser import parse_h2h, parse_live_stats
from flashscore.probabilities import compute_probs, get_selections, format_ticket
from flashscore.telegram_sender import send_telegram
import db

TOURNAMENT_URL = "https://global.flashscore.ninja/401/x/feed/t_1_{country_id}_{tournament_id}_-3_pt-br_1"
STATS_URL = "https://global.flashscore.ninja/401/x/feed/df_st_1_{match_id}"
DEFAULT_COUNTRY = "39"   # Brasil
MIN_CONFIDENCE = 0.40    # só inclui seleções com pelo menos 40% de probabilidade

# ------------------------------------------------------------
# Funções auxiliares
# ------------------------------------------------------------
def fetch_tournament_feed(country_id: str, tournament_id: str) -> str | None:
    """Busca o feed de torneio e retorna o texto bruto."""
    url = TOURNAMENT_URL.format(country_id=country_id, tournament_id=tournament_id)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"❌ Erro ao buscar feed do torneio {tournament_id}: {e}")
        return None

def extract_match_ids(raw: str) -> list[str]:
    """Extrai os IDs das partidas – campo AA÷ no feed de torneio."""
    return re.findall(r'AA÷(\w{8})', raw)

async def process_match(match_id: str, min_confidence: float = MIN_CONFIDENCE):
    """Processa uma partida e retorna suas seleções com filtro de confiança."""
    raw = load_raw_h2h(match_id)
    if not raw:
        print(f"⚠️ H2H não encontrado para {match_id}")
        return [], None, None
    data = parse_h2h(raw)
    if len(data) < 2:
        print(f"⚠️ Menos de 2 times para {match_id}")
        return [], None, None
    home, away = list(data.keys())[:2]
    print(f"✅ {home} x {away} ({match_id})")

    # Cache inteligente
    match_entry = db.get_or_create_match(home, away, raw)
    raw = match_entry.get('raw_data', raw)
    data = parse_h2h(raw)

    # Escanteios ao vivo
    home_c = away_c = None
    live_raw = fetch_feed(STATS_URL, match_id)
    if live_raw:
        home_c, away_c = parse_live_stats(live_raw)
        if home_c is not None:
            print(f"📡 Escanteios ao vivo: {home_c} x {away_c}")

    probs = compute_probs(data[home], data[away],
                          live_corners=(home_c, away_c) if home_c is not None else None)
    all_sels = get_selections(probs, home, away)

    # Filtro de confiança mínima
    filtered_sels = [(desc, prob) for desc, prob in all_sels if prob >= min_confidence]
    if not filtered_sels:
        # se nada passou no filtro, usa a melhor seleção
        best = max(all_sels, key=lambda x: x[1])
        filtered_sels = [best]

    # Salva no banco
    try:
        db.save_probabilities(match_entry['id'], probs)
    except Exception as e:
        print(f"⚠️ {e}")

    return filtered_sels, home, away

# ------------------------------------------------------------
# Geração de bilhetes múltiplos
# ------------------------------------------------------------
def build_multi_tickets(all_sels: list, max_pernas: int = 5, top_n: int = 5):
    """Combina seleções de diferentes partidas em bilhetes múltiplos."""
    by_match = defaultdict(list)
    for desc, prob in all_sels:
        mk = desc.split(":")[0].strip()
        by_match[mk].append((desc, prob))

    match_keys = list(by_match.keys())
    if len(match_keys) < 2:
        return []

    for mk in by_match:
        by_match[mk].sort(key=lambda x: x[1], reverse=True)

    all_tickets = []
    for k in range(2, min(max_pernas + 1, len(match_keys) + 1)):
        for combo_matches in combinations(match_keys, k):
            # pega as top 3 seleções de cada partida
            top_sels = [by_match[m][:3] for m in combo_matches]
            for sel_combo in product(*top_sels):
                prob = reduce(lambda x, y: x * y, [s[1] for s in sel_combo])
                all_tickets.append((sel_combo, prob))

    all_tickets.sort(key=lambda x: x[1], reverse=True)
    seen = set()
    unique = []
    for combo, prob in all_tickets:
        ids = tuple(sorted(d for d, _ in combo))
        if ids not in seen:
            seen.add(ids)
            unique.append({'bets': list(combo), 'combined_prob': prob})
        if len(unique) >= top_n:
            break
    return unique

# ------------------------------------------------------------
# Parse dos argumentos
# ------------------------------------------------------------
def parse_args():
    """Interpreta os argumentos da linha de comando como pares (country_id, tournament_id)."""
    tournaments = []
    for arg in sys.argv[1:]:
        if ':' in arg:
            country, tour = arg.split(':', 1)
        else:
            country, tour = DEFAULT_COUNTRY, arg
        tournaments.append((country, tour))
    return tournaments

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
async def main():
    if len(sys.argv) < 2:
        print("Uso: python rodada.py <COUNTRY_ID>:<TOURNAMENT_ID> ...")
        return

    tournaments = parse_args()
    all_sels = []

    for country_id, tour_id in tournaments:
        print(f"\n🔍 Buscando partidas para torneio {tour_id} (país {country_id})...")
        raw = fetch_tournament_feed(country_id, tour_id)
        if not raw:
            print("❌ Feed do torneio vazio. Pulando...")
            continue

        matches_ids = extract_match_ids(raw)
        print(f"📋 {len(matches_ids)} partidas encontradas: {matches_ids}")

        for mid in matches_ids:
            sels, _, _ = await process_match(mid)
            all_sels.extend(sels)

    if not all_sels:
        print("❌ Nenhuma seleção gerada.")
        return

    tickets = build_multi_tickets(all_sels, max_pernas=4, top_n=5)
    if not tickets:
        # Fallback para bilhetes simples (uma perna)
        tickets = [{'bets': [(d, p)], 'combined_prob': p} for d, p in all_sels[:5]]

    final_msg = "🎫 **Ultra Bingo da Rodada**\n\n"
    for i, t in enumerate(tickets):
        msg = format_ticket(t, i)
        print(msg)
        print()
        final_msg += msg + "\n\n"

    if final_msg:
        await send_telegram(final_msg.strip())

if __name__ == '__main__':
    asyncio.run(main())