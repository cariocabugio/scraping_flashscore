#!/usr/bin/env python3
"""
Analisador H2H Flashscore - com Escanteios Ao Vivo, Metadados, Cache, Telegram e Supabase
"""

import os
import sys
import re
import asyncio
from collections import defaultdict
from itertools import product
from functools import reduce

import requests
from dotenv import load_dotenv
from telegram import Bot

import db

load_dotenv('.env.local')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

API_URL = "https://global.flashscore.ninja/401/x/feed/df_hh_1_{match_id}"
STATS_URL = "https://global.flashscore.ninja/401/x/feed/df_st_1_{match_id}"
EVENTS_URL = "https://global.flashscore.ninja/401/x/feed/df_ml_1_{match_id}"
DETAIL_URL = "https://global.flashscore.ninja/401/x/feed/dc_1_{match_id}"
HEADERS = {"X-Fsign": "SW9D1eZo", "User-Agent": "Mozilla/5.0"}

def fetch_feed(url_template, match_id):
    try:
        resp = requests.get(url_template.format(match_id=match_id), headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text
    except:
        return None

def load_raw_h2h(source):
    try:
        with open(source, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'SA÷1¬~' in content:
                return content
    except FileNotFoundError:
        pass
    if re.match(r'^[a-zA-Z0-9]{8}$', source):
        return fetch_feed(API_URL, source)
    mid = re.search(r'([a-zA-Z0-9]{8})', source)
    return fetch_feed(API_URL, mid.group(1)) if mid else None

def extract_match_id(source):
    if re.match(r'^[a-zA-Z0-9]{8}$', source):
        return source
    m = re.search(r'([a-zA-Z0-9]{8})', source)
    return m.group(1) if m else None

def parse_h2h(text, max_games=19):
    flat = text.replace('\n', '')
    team_blocks = re.finditer(r'KB÷Últimos jogos:\s*(.+?)¬~KC÷(.*?)(?=~KB÷|~SA÷|~A1÷|$)', flat)
    teams = defaultdict(list)
    for match in team_blocks:
        team_name = match.group(1).strip()
        games_block = match.group(2)
        games = re.finditer(r'(?:~)?KC÷(.*?)(?=~KC÷|~KB÷|$)', games_block)
        count = 0
        for gm in games:
            if count >= max_games:
                break
            fields_str = gm.group(1)
            fields = fields_str.split('¬')
            d = {}
            for f in fields:
                if '÷' in f:
                    k, v = f.split('÷', 1)
                    d[k] = v
            try:
                opp = d.get('KJ', '').lstrip('*').strip()
                is_home = d.get('KS', '') == 'home'
                hg = int(d.get('KU', '0'))
                ag = int(d.get('KT', '0'))
                res = d.get('KN', '')
                gf = hg if is_home else ag
                ga = ag if is_home else hg
                teams[team_name].append({'opponent': opp, 'is_home': is_home, 'goals_for': gf, 'goals_against': ga, 'result': res})
                count += 1
            except:
                continue
    return dict(teams)

def parse_live_time(text):
    """Extrai status e minuto de jogo de um feed de tempo real (ex: dc_1 ou similar)."""
    if not text:
        return None, None
    status_match = re.search(r'DA÷(\d+)', text)
    minute_match = re.search(r'DB÷(\d+)', text)
    status = int(status_match.group(1)) if status_match else None
    minute = int(minute_match.group(1)) if minute_match else None
    return status, minute

def parse_live_stats(text):
    """Retorna escanteios do feed de estatísticas ao vivo (df_st_1)."""
    if not text or 'Escanteios' not in text:
        return (None, None)
    m = re.search(r'Escanteios¬SH÷(\d+)¬SI÷(\d+)', text)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)

def parse_match_events(raw):
    events = []
    for m in re.finditer(r'SC÷(\d+)¬EC÷(\d+)¬PS÷(home|away)(?:¬PE÷([^¬]*))?', raw):
        minute = int(m.group(1))
        code = int(m.group(2))
        team = m.group(3)
        player = m.group(4) if m.group(4) else None
        type_map = {1: 'goal', 3: 'yellow_card', 7: 'red_card', 11: 'penalty_missed', 12: 'substitution', 20: 'corner'}
        events.append({
            'event_type': type_map.get(code, f'unknown_{code}'),
            'event_code': code, 'minute': minute, 'extra_min': 0,
            'team': team, 'section': '1st' if minute <= 45 else '2nd',
            'player': player, 'raw': m.group(0)
        })
    return events

def parse_match_detail(raw):
    """Extrai metadados do feed dc_1."""
    meta = {}
    # Árbitro
    ref_match = re.search(r'MIT÷REF¬MIV÷([^¬]+)', raw)
    if ref_match:
        meta['referee'] = ref_match.group(1)
    # Estádio
    stadium_match = re.search(r'MIT÷VEN¬MIV÷([^¬]+)', raw)
    if stadium_match:
        meta['stadium'] = stadium_match.group(1)
    # Capacidade
    cap_match = re.search(r'MIT÷CAP¬MIV÷([^¬]+)', raw)
    if cap_match:
        try:
            meta['capacity'] = int(cap_match.group(1).replace(' ', ''))
        except:
            pass
    # TV
    tv_match = re.search(r'TA÷([^¬]+)', raw)
    if tv_match:
        meta['tv_channels'] = tv_match.group(1).strip()
    # Available feeds (campo bônus, pode não existir)
    feeds_match = re.search(r'DX÷([^¬]+)', raw)
    if feeds_match:
        meta['available_feeds'] = feeds_match.group(1).strip()
    return meta

def compute_probs(home_data, away_data, live_corners=None, max_games=19):
    h = home_data[-max_games:]
    a = away_data[-max_games:]
    home_home = [m for m in h if m['is_home']]
    away_away = [m for m in a if not m['is_home']]

    def _1x2(hm, am):
        hw = sum(1 for m in hm if m['result'] in ('w','wo')) / len(hm) if hm else 0.35
        aw = sum(1 for m in am if m['result'] in ('w','wo')) / len(am) if am else 0.30
        dh = sum(1 for m in hm if m['result'] == 'd') / len(hm) if hm else 0.25
        da = sum(1 for m in am if m['result'] == 'd') / len(am) if am else 0.25
        draw = (dh + da) / 2
        total = hw + draw + aw
        if total > 0:
            hw /= total; draw /= total; aw /= total
        return hw, draw, aw
    hw, draw, aw = _1x2(home_home, away_away)

    all_goals = [m['goals_for'] + m['goals_against'] for m in h + a]
    total = len(all_goals)
    over_0_5 = sum(g > 0.5 for g in all_goals) / total if total else 0.95
    over_1_5 = sum(g > 1.5 for g in all_goals) / total if total else 0.8
    over_2_5 = sum(g > 2.5 for g in all_goals) / total if total else 0.55

    if live_corners and live_corners[0] is not None:
        tc = live_corners[0] + live_corners[1]
        corners_8_5 = 1.0 if tc > 8.5 else 0.0
        corners_9_5 = 1.0 if tc > 9.5 else 0.0
        corners_10_5 = 1.0 if tc > 10.5 else 0.0
    else:
        corners_8_5, corners_9_5, corners_10_5 = 0.55, 0.45, 0.35

    return {
        'home_win': hw, 'draw': draw, 'away_win': aw,
        'over_0_5': over_0_5, 'over_1_5': over_1_5, 'over_2_5': over_2_5,
        'corners_8_5': corners_8_5, 'corners_9_5': corners_9_5, 'corners_10_5': corners_10_5
    }

def format_match_table(home, away, probs):
    return "\n".join([
        f"📊 *{home} x {away}*",
        f"Vitória {home}: {probs['home_win']*100:.1f}%",
        f"Empate: {probs['draw']*100:.1f}%",
        f"Vitória {away}: {probs['away_win']*100:.1f}%",
        f"Over 0.5: {probs['over_0_5']*100:.1f}%",
        f"Over 1.5: {probs['over_1_5']*100:.1f}%",
        f"Over 2.5: {probs['over_2_5']*100:.1f}%",
        f"Cantos +8.5: {probs['corners_8_5']*100:.1f}%",
        f"Cantos +9.5: {probs['corners_9_5']*100:.1f}%",
        f"Cantos +10.5: {probs['corners_10_5']*100:.1f}%"
    ])

def get_selections(probs, home, away):
    ml = f"{home} x {away}"
    return [
        (f"{ml}: Vitória {home}", probs['home_win']),
        (f"{ml}: Empate", probs['draw']),
        (f"{ml}: Vitória {away}", probs['away_win']),
        (f"{ml}: Over 0.5", probs['over_0_5']),
        (f"{ml}: Over 1.5", probs['over_1_5']),
        (f"{ml}: Over 2.5", probs['over_2_5']),
        (f"{ml}: Cantos +8.5", probs['corners_8_5']),
        (f"{ml}: Cantos +9.5", probs['corners_9_5']),
        (f"{ml}: Cantos +10.5", probs['corners_10_5']),
    ]

def generate_top_tickets(all_sels, top_n=3):
    by_match = defaultdict(list)
    for desc, prob in all_sels:
        mk = desc.split(":")[0].strip()
        by_match[mk].append((desc, prob))
    for mk in by_match:
        by_match[mk].sort(key=lambda x: x[1], reverse=True)
    mks = list(by_match.keys())
    if len(mks) == 1:
        return [{'bets': [(d,p)], 'combined_prob': p} for d,p in by_match[mks[0]][:top_n]]
    combos = list(product(*[by_match[k] for k in mks]))
    scored = [(c, reduce(lambda x,y: x*y, [p for _,p in c])) for c in combos]
    scored.sort(key=lambda x: x[1], reverse=True)
    seen, tickets = set(), []
    for c, prob in scored:
        ids = tuple(sorted(d for d,_ in c))
        if ids not in seen:
            seen.add(ids)
            tickets.append({'bets': list(c), 'combined_prob': prob})
        if len(tickets) >= top_n:
            break
    return tickets



def format_ticket(ticket, index):
    lines = [f"🎫 Bilhete {index+1}"]
    for d,p in ticket['bets']:
        lines.append(f"• {d} → {p*100:.1f}%")
    lines.append(f"🔹 Probabilidade combinada: {ticket['combined_prob']*100:.2f}%")
    return "\n".join(lines)

async def send_telegram(text):
    if not TELEGRAM_CHAT_ID:
        return
    bot = Bot(token=TELEGRAM_TOKEN)
    ids = [c.strip() for c in TELEGRAM_CHAT_ID.split(',') if c.strip()]
    for cid in ids:
        try:
            await bot.send_message(chat_id=cid, text=text, parse_mode='Markdown')
        except Exception as e:
            print(f"⚠️ Telegram {cid}: {e}")

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

        # Cache inteligente: recupera ou cria registro da partida
        match_entry = db.get_or_create_match(home, away, raw)
        raw = match_entry.get('raw_data', raw)
        data = parse_h2h(raw)

        mid = extract_match_id(arg)
        home_c = away_c = None

        # 1. Metadados da partida (dc_1) – exibição limpa
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

        # 2. Escanteios (eventos ou ao vivo) – parser corrigido
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