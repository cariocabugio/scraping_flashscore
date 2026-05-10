#!/usr/bin/env python3
import sys
import asyncio
from flashscore.fetcher import load_raw_h2h, extract_match_id, fetch_feed
from flashscore.parser import parse_h2h, parse_live_stats, parse_match_events, parse_match_detail
from flashscore.probabilities import (
    compute_probs, get_selections, format_match_table,
    build_tickets, format_ultra_ticket
)
from flashscore.telegram_sender import send_telegram
from flashscore.odds_fetcher import fetch_all_bookmakers  # novo
import db

STATS_URL = "https://global.flashscore.ninja/401/x/feed/df_st_1_{match_id}"
EVENTS_URL = "https://global.flashscore.ninja/401/x/feed/df_ml_1_{match_id}"
DETAIL_URL = "https://global.flashscore.ninja/401/x/feed/dc_1_{match_id}"
CONFIDENCE_RANGE = (0.40, 0.85)

async def main():
    if len(sys.argv) < 2:
        print("Uso: python analisador_final.py <id_ou_arquivo> ...")
        return
    all_sels, tables = [], []
    for arg in sys.argv[1:]:
        raw = load_raw_h2h(arg)
        if not raw: continue
        data = parse_h2h(raw)
        if len(data) < 2: continue
        home, away = list(data.keys())[:2]
        print(f"✅ {home} x {away}")

        match_entry = db.get_or_create_match(home, away, raw)
        raw = match_entry.get('raw_data', raw)
        data = parse_h2h(raw)

        mid = extract_match_id(arg)
        home_c = away_c = None

        # Metadados
        if mid:
            detail_raw = fetch_feed(DETAIL_URL, mid)
            if detail_raw:
                meta = parse_match_detail(detail_raw)
                parts = []
                if meta.get('referee'): parts.append(f"Árbitro: {meta['referee']}")
                if meta.get('stadium'): parts.append(f"Estádio: {meta['stadium']}" + (f" ({meta['capacity']})" if meta.get('capacity') else ""))
                if meta.get('tv_channels'): parts.append(f"TV: {meta['tv_channels']}")
                if parts:
                    print("📋 " + " | ".join(parts))
                if 'available_feeds' in meta and 'OD' in meta['available_feeds']:
                    print("🎲 Feeds de odds disponíveis (OD) – podemos tentar capturar odds mais tarde.")
                db.save_match_metadata(match_entry['id'], meta)
                db.save_match_feeds(match_entry['id'], meta.get('available_feeds', ''))

        # Escanteios (eventos ou ao vivo)
        if mid:
            ev_raw = fetch_feed(EVENTS_URL, mid)
            if ev_raw and 'EC÷' in ev_raw:
                events = parse_match_events(ev_raw)
                db.save_match_events(match_entry['id'], events)
                corners_dict = db.get_corners_for_match(match_entry['id'])
                home_c = corners_dict['home']
                away_c = corners_dict['away']
                print(f"📡 Escanteios via eventos: {home_c} x {away_c}")
            else:
                live_raw = fetch_feed(STATS_URL, mid)
                if live_raw:
                    home_c, away_c = parse_live_stats(live_raw)
                    if home_c is not None and not (home_c == 0 and away_c == 0):
                        print(f"📡 Escanteios ao vivo: {home_c} x {away_c}")
                    else:
                        print("⚠️ Feed ao vivo sem escanteios.")
                else:
                    print("ℹ️  Jogo sem feed ao vivo/eventos. Usando modelo fixo para cantos.")
        else:
            print("ℹ️  ID não identificado; modelo fixo para cantos.")

        probs = compute_probs(data[home], data[away],
                              live_corners=(home_c, away_c) if home_c is not None else None)

        # ---------- Odds Reais ----------
        real_odds = None
        try:
            odds_dict = fetch_all_bookmakers(mid) if mid else None
            if odds_dict:
                parts = []
                for book, markets in odds_dict.items():
                    if isinstance(markets, dict):
                        parts.append(f"{book}: H={markets.get('home','?')}, D={markets.get('draw','?')}, A={markets.get('away','?')}")
                if parts:
                    print("📈 Odds reais:", " | ".join(parts))
                best_home = min((m.get('home', 999) for m in odds_dict.values() if isinstance(m, dict)), default=None)
                best_draw = min((m.get('draw', 999) for m in odds_dict.values() if isinstance(m, dict)), default=None)
                best_away = min((m.get('away', 999) for m in odds_dict.values() if isinstance(m, dict)), default=None)
                real_odds = {'home': best_home, 'draw': best_draw, 'away': best_away}
        except Exception as e:
            print(f"⚠️ Não foi possível obter odds reais: {e}")

        tables.append(format_match_table(home, away, probs))
        sels = get_selections(probs, home, away)
        # Adiciona odds reais se disponíveis
        if real_odds:
            sels = [(d, p, real_odds.get(d.split(':')[1].strip().lower(), 0.0)) for d, p in sels]
        else:
            sels = [(d, p, 0.0) for d, p in sels]
        all_sels.extend(sels)
        try:
            db.save_probabilities(match_entry['id'], probs)
        except Exception as e: print(f"⚠️ {e}")

    if not tables: return
    full = "\n\n".join(tables)
    print(full)
    await send_telegram(full)

    # Gera bilhetes (usa apenas desc e prob)
    def adapt(sel_list):
        return [(d, p) for d, p, _ in sel_list]

    tickets = build_tickets(adapt(all_sels))
    if not tickets and all_sels:
        tickets = [{'bets': [(d, p)], 'combined_prob': p, 'profile': 'Simples'}
                   for d, p, _ in sorted(all_sels, key=lambda x: x[1], reverse=True)[:3]]
    tmsg = ""
    for i, t in enumerate(tickets):
        msg = format_ultra_ticket(t, i)
        print(msg); print()
        tmsg += msg + "\n\n"
    if tmsg:
        await send_telegram(tmsg.strip())
        try: db.save_tickets(tickets)
        except Exception as e: print(f"⚠️ {e}")

if __name__ == '__main__':
    asyncio.run(main())