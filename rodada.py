#!/usr/bin/env python3
"""
Gerador de Bilhetes Ultra Bingo – com Odds Reais.
Uso: python rodada.py [url:|file:|COUNTRY:TOURNAMENT] ... [--days 0|1|all]
"""

import sys
import asyncio

from flashscore.fetcher import (
    fetch_feed, load_raw_h2h, try_fetch_tournament, extract_match_ids
)
from flashscore.parser import parse_h2h, parse_live_stats, parse_match_detail
from flashscore.probabilities import (
    compute_probs, enrich_selections_with_odds, get_selections, build_tickets, format_ultra_ticket
)
from flashscore.telegram_sender import send_telegram
from flashscore.odds_fetcher import fetch_all_bookmakers  # novo
import db

STATS_URL = "https://global.flashscore.ninja/401/x/feed/df_st_1_{match_id}"
DETAIL_URL = "https://global.flashscore.ninja/401/x/feed/dc_1_{match_id}"
CONFIDENCE_RANGE = (0.40, 0.85)

# ------------------------------------------------------------
async def process_match(match_id):
    raw = load_raw_h2h(match_id)
    if not raw:
        return [], None, None
    data = parse_h2h(raw)
    if len(data) < 2:
        return [], None, None
    home, away = list(data.keys())[:2]
    print(f"✅ {home} x {away}")

    match_entry = db.get_or_create_match(home, away, raw)
    raw = match_entry.get('raw_data', raw)
    data = parse_h2h(raw)

    # Metadados da partida
    detail_raw = fetch_feed(DETAIL_URL, match_id)
    if detail_raw:
        meta = parse_match_detail(detail_raw)
        if meta:
            parts = []
            if meta.get('referee'): parts.append(f"Árbitro: {meta['referee']}")
            if meta.get('stadium'): parts.append(f"Estádio: {meta['stadium']}")
            if meta.get('tv_channels'): parts.append(f"TV: {meta['tv_channels']}")
            if parts:
                print("📋 " + " | ".join(parts))
            db.save_match_metadata(match_entry['id'], meta)
            db.save_match_feeds(match_entry['id'], meta.get('available_feeds', ''))

    # Escanteios ao vivo
    home_c = away_c = None
    live_raw = fetch_feed(STATS_URL, match_id)
    if live_raw:
        home_c, away_c = parse_live_stats(live_raw)
        if home_c == 0 and away_c == 0:
            home_c, away_c = None, None

    probs = compute_probs(
        data[home], data[away],
        live_corners=(home_c, away_c) if home_c is not None else None
    )

    # Odds reais
    real_odds = None
    try:
        real_odds = fetch_all_bookmakers(match_id)
        if real_odds:
            print("📈 Odds reais:", ", ".join(
                f"{k}: H={v['home']}, D={v['draw']}, A={v['away']}" for k, v in real_odds.items()
            ))
    except Exception as e:
        print(f"⚠️ Não foi possível obter odds reais: {e}")

    all_sels = get_selections(probs, home, away)
    filtered = [
        (d, p) for d, p in all_sels
        if CONFIDENCE_RANGE[0] <= p <= CONFIDENCE_RANGE[1]
    ]
    if not filtered:
        filtered = [max(all_sels, key=lambda x: x[1])]

    if real_odds:
        enriched = enrich_selections_with_odds(filtered, real_odds)
    else:
        enriched = [(d, p, None) for d, p in filtered]

    try:
        db.save_probabilities(match_entry['id'], probs)
    except Exception:
        pass

    return enriched, home, away

# ------------------------------------------------------------
def parse_args():
    sources, days = [], 1
    i = 1
    while i < len(sys.argv):
        a = sys.argv[i]
        if a == '--days':
            i += 1
            if i < len(sys.argv):
                days = int(sys.argv[i]) if sys.argv[i].isdigit() else sys.argv[i]
        else:
            sources.append(a)
        i += 1
    return sources, days

# ------------------------------------------------------------
async def main():
    if len(sys.argv) < 2:
        print("Uso: python rodada.py [url:|file:|COUNTRY:TOURNAMENT] ... [--days 0|1|all]")
        return

    sources, days = parse_args()
    all_sels = []

    for src in sources:
        raw = try_fetch_tournament(src, days)
        if not raw:
            print(f"⚠️  Nenhuma partida para {src} no período solicitado.")
            continue
        mids = extract_match_ids(raw)
        print(f"📋 {len(mids)} partidas de {src}")
        for mid in mids:
            sels, _, _ = await process_match(mid)
            all_sels.extend(sels)

    if not all_sels:
        print("Nenhuma seleção.")
        return

    # Ajusta a estrutura para build_tickets (espera tuplas de 2 elementos)
    # Se houver odds, substituímos a prob combinada pela melhor odd real
    def extrair_sels(sels):
        tickets_data = []
        for s in sels:
            if len(s) == 3:
                desc, prob, odd = s
                # Usa a odd real se existir e for > 0, senão mantém a prob
                combined = odd if odd and odd > 0 else prob
                tickets_data.append((desc, combined))
            else:
                tickets_data.append(s[:2])
        return tickets_data

    tickets_data = extrair_sels(all_sels)
    tickets = build_tickets(tickets_data)
    if not tickets:
        print("ℹ️  Menos de 2 partidas disponíveis. Gerando bilhetes simples.")
        tickets = [{'bets': [(d, p)], 'combined_prob': p, 'profile': 'Simples'}
                   for d, p in sorted(tickets_data, key=lambda x: x[1], reverse=True)[:3]]

    header = "🎰 *ULTRA BINGO DA RODADA*\n\n"
    final_msg = header
    for i, t in enumerate(tickets):
        # Atualiza a odd estimada para a odd real (se disponível)
        msg = format_ultra_ticket(t, i)
        print(msg)
        print()
        final_msg += msg + "\n\n"

    await send_telegram(final_msg.strip())

if __name__ == '__main__':
    asyncio.run(main())