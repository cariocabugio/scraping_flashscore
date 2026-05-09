#!/usr/bin/env python3
import sys
import asyncio
from flashscore.fetcher import load_raw_h2h, extract_match_id, fetch_feed
from flashscore.parser import parse_h2h, parse_live_stats, parse_match_events, parse_match_detail
from flashscore.probabilities import compute_probs, get_selections, format_match_table, generate_top_tickets, format_ticket
from flashscore.telegram_sender import send_telegram
import db

STATS_URL = "https://global.flashscore.ninja/401/x/feed/df_st_1_{match_id}"
EVENTS_URL = "https://global.flashscore.ninja/401/x/feed/df_ml_1_{match_id}"
DETAIL_URL = "https://global.flashscore.ninja/401/x/feed/dc_1_{match_id}"

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
                    if home_c is not None:
                        print(f"📡 Escanteios ao vivo: {home_c} x {away_c}")
                    else:
                        print("⚠️ Feed ao vivo sem escanteios.")
                else:
                    print("ℹ️  Jogo sem feed ao vivo/eventos. Usando modelo fixo para cantos.")
        else:
            print("ℹ️  ID não identificado; modelo fixo para cantos.")

        probs = compute_probs(data[home], data[away],
                              live_corners=(home_c, away_c) if home_c is not None else None)
        tables.append(format_match_table(home, away, probs))
        sels = get_selections(probs, home, away)
        all_sels.extend(sels)
        try:
            db.save_probabilities(match_entry['id'], probs)
        except Exception as e: print(f"⚠️ {e}")

    if not tables: return
    full = "\n\n".join(tables)
    print(full)
    await send_telegram(full)

    tickets = generate_top_tickets(all_sels)
    tmsg = ""
    for i, t in enumerate(tickets):
        msg = format_ticket(t, i)
        print(msg); print()
        tmsg += msg + "\n\n"
    if tmsg:
        await send_telegram(tmsg.strip())
        try: db.save_tickets(tickets)
        except Exception as e: print(f"⚠️ {e}")

if __name__ == '__main__':
    asyncio.run(main())