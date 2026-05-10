#!/usr/bin/env python3
"""
Gerador de Bilhetes Ultra Bingo – 3 bilhetes com partidas únicas.
Uso: python rodada.py [url:|file:|COUNTRY:TOURNAMENT] ... [--days 0|1|all]
"""

import sys, re, asyncio
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from functools import reduce
import requests
from flashscore.fetcher import fetch_feed, load_raw_h2h, HEADERS
from flashscore.parser import parse_h2h, parse_live_stats
from flashscore.probabilities import compute_probs, get_selections
from flashscore.telegram_sender import send_telegram
import db

DEFAULT_COUNTRY = "39"
STATS_URL = "https://global.flashscore.ninja/401/x/feed/df_st_1_{match_id}"
CONFIDENCE_RANGE = (0.40, 0.85)
MAX_SELS_PER_MATCH = 6

def extract_upcoming_from_standings(raw, days=1):
    now = datetime.now(timezone.utc)
    if days == 'all':
        return "".join(f"AA÷{mid}¬" for mid in re.findall(r'LMU÷upcoming.*?LME÷(\w{8})', raw))
    start = (now if days == 0 else now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    start_ts, end_ts = int(start.timestamp()), int(end.timestamp()) - 1
    ids = [m.group(1) for m in re.finditer(r'LMU÷upcoming.*?LME÷(\w{8})\s*.*?LMC÷(\d{10})', raw, re.DOTALL)
           if start_ts <= int(m.group(2)) <= end_ts]
    return "".join(f"AA÷{mid}¬" for mid in ids)

def try_fetch_tournament(source, days=1):
    if source.startswith("url:"):
        url = source[4:]
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.ok and len(resp.text) > 100:
                return extract_upcoming_from_standings(resp.text, days)
        except: pass
        return None
    if source.startswith("file:"):
        path = source[5:]
        try:
            with open(path, encoding='utf-8') as f:
                return extract_upcoming_from_standings(f.read(), days)
        except: pass
        return None
    country, tour = (source.split(':', 1) if ':' in source else (DEFAULT_COUNTRY, source))
    for url in (f"https://global.flashscore.ninja/401/x/feed/t_1_{country}_{tour}_-3_pt-br_1",
                f"https://global.flashscore.ninja/401/x/feed/to_{country}_{tour}_1"):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.ok and len(resp.text) > 50:
                return extract_upcoming_from_standings(resp.text, days)
        except: continue
    return None

def extract_match_ids(raw):
    return list(set(re.findall(r'AA÷(\w{8})', raw)))

async def process_match(match_id):
    raw = load_raw_h2h(match_id)
    if not raw: return [], None, None
    data = parse_h2h(raw)
    if len(data) < 2: return [], None, None
    home, away = list(data.keys())[:2]
    print(f"✅ {home} x {away}")
    match_entry = db.get_or_create_match(home, away, raw)
    raw = match_entry.get('raw_data', raw)
    data = parse_h2h(raw)
    home_c = away_c = None
    live_raw = fetch_feed(STATS_URL, match_id)
    if live_raw:
        home_c, away_c = parse_live_stats(live_raw)
        if home_c == 0 and away_c == 0:
            home_c, away_c = None, None
    probs = compute_probs(data[home], data[away],
                          live_corners=(home_c, away_c) if home_c is not None else None)
    all_sels = get_selections(probs, home, away)
    filtered = [(d,p) for d,p in all_sels if CONFIDENCE_RANGE[0] <= p <= CONFIDENCE_RANGE[1]]
    if not filtered:
        filtered = [max(all_sels, key=lambda x: x[1])]
    try: db.save_probabilities(match_entry['id'], probs)
    except: pass
    return filtered, home, away

def market_type(desc):
    if 'Vitória' in desc or 'Empate' in desc: return '1x2'
    if 'Over' in desc: return 'over'
    if 'Cantos' in desc: return 'corners'
    return 'other'

def build_three_tickets(all_sels):
    """Gera 3 bilhetes únicos (Conservador, Moderado, Turbo) com partidas diferentes."""
    by_match = defaultdict(list)
    for desc, prob in all_sels:
        mk = desc.split(":")[0].strip()
        by_match[mk].append((desc, prob))
    for mk in by_match:
        by_match[mk].sort(key=lambda x: x[1], reverse=True)

    match_keys = list(by_match.keys())
    if len(match_keys) < 2: return []

    profiles = [
        ("Conservador", 4, {"min_corners": 0, "min_1x2": 0}),
        ("Moderado", 5, {"min_corners": 2}),
        ("Turbo", 6, {"min_corners": 2, "min_1x2": 1}),
    ]

    tickets = []
    used = set()

    for name, max_n, constr in profiles:
        sel = []
        for mk in match_keys:
            if mk in used: continue
            for d, p in by_match[mk][:MAX_SELS_PER_MATCH]:
                types = [market_type(x) for x,_ in sel] + [market_type(d)]
                ok = True
                if types.count('corners') < constr.get('min_corners',0): ok = False
                if types.count('1x2') < constr.get('min_1x2',0): ok = False
                if ok:
                    sel.append((d,p))
                    used.add(mk)
                    break
            if len(sel) >= max_n:
                break

        # Se não atingiu o mínimo de cantos/1x2, tenta complementar com as partidas já usadas (sacrifício controlado)
        if constr.get('min_corners',0) > sum(1 for x,_ in sel if 'Cantos' in x):
            for mk in match_keys:
                if sum(1 for x,_ in sel if 'Cantos' in x) >= constr['min_corners']: break
                for d, p in by_match[mk][:MAX_SELS_PER_MATCH]:
                    if 'Cantos' in d:
                        sel.append((d,p))
                        used.add(mk)
                        break
        if constr.get('min_1x2',0) > sum(1 for x,_ in sel if 'Vitória' in x or 'Empate' in x):
            for mk in match_keys:
                if sum(1 for x,_ in sel if 'Vitória' in x or 'Empate' in x) >= constr['min_1x2']: break
                for d, p in by_match[mk][:MAX_SELS_PER_MATCH]:
                    if 'Vitória' in d or 'Empate' in d:
                        sel.append((d,p))
                        used.add(mk)
                        break

        if sel:
            prob = reduce(lambda x,y: x*y, [p for _,p in sel])
            tickets.append({'bets': sel, 'combined_prob': prob, 'profile': name})
        if len(tickets) >= 3: break

    return tickets

def format_ticket(ticket, index):
    profile = ticket.get('profile', 'Bilhete')
    lines = [f"🎫 *{profile}* #{index+1}"]
    for d,p in ticket['bets']:
        lines.append(f"• {d} → {p*100:.1f}%")
    lines.append(f"🔹 Probabilidade combinada: {ticket['combined_prob']*100:.2f}%")
    odd = 1.0 / ticket['combined_prob'] if ticket['combined_prob'] > 0 else 0
    lines.append(f"💎 Odd justa estimada: {odd:.2f}")
    return "\n".join(lines)

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

async def main():
    if len(sys.argv) < 2:
        print("Uso: python rodada.py [url:|file:|COUNTRY:TOURNAMENT] ... [--days 0|1|all]")
        return
    sources, days = parse_args()
    all_sels = []
    for src in sources:
        raw = try_fetch_tournament(src, days)
        if not raw: continue
        mids = extract_match_ids(raw)
        print(f"📋 {len(mids)} partidas de {src}")
        for mid in mids:
            sels, _, _ = await process_match(mid)
            all_sels.extend(sels)
    if not all_sels:
        print("Nenhuma seleção."); return
    tickets = build_three_tickets(all_sels)
    if not tickets:
        print("Nenhum bilhete."); return
    header = "🎰 *ULTRA BINGO DA RODADA*\n\n"
    final_msg = header
    for i, t in enumerate(tickets):
        msg = format_ticket(t, i)
        print(msg); print()
        final_msg += msg + "\n\n"
    await send_telegram(final_msg.strip())

if __name__ == '__main__':
    asyncio.run(main())