#!/usr/bin/env python3
"""
Analisador H2H Flashscore - Automático via API + Supabase
Uso: python analisador_final.py <id_partida1> <id_partida2> ...
   ou python analisador_final.py arquivo_bruto.txt ...
"""

import os
import sys
import re
import asyncio
from collections import defaultdict
from itertools import product

import requests
from dotenv import load_dotenv
from telegram import Bot

import db  # módulo do Supabase

load_dotenv('.env.local')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

API_URL = "https://global.flashscore.ninja/401/x/feed/df_hh_1_{match_id}"
HEADERS = {
    "X-Fsign": "SW9D1eZo",
    "User-Agent": "Mozilla/5.0"
}

# ------------------------------------------------------------
# 1. Coleta automática ou arquivo
# ------------------------------------------------------------
def fetch_h2h_text(match_id):
    """Busca o texto bruto H2H da API."""
    try:
        resp = requests.get(API_URL.format(match_id=match_id), headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"❌ Erro ao buscar ID {match_id}: {e}")
        return None

def load_raw_text(source):
    """
    source pode ser:
    - um ID de partida (ex: SOEkFMVh)
    - um nome de arquivo .txt com os dados brutos
    Retorna o texto ou None.
    """
    # Se for um arquivo existente, lê
    try:
        with open(source, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'SA÷1¬~' in content:
                return content
    except FileNotFoundError:
        pass
    
    # Se parece um ID (sem extensão, letras maiúsculas/minúsculas), tenta API
    if re.match(r'^[a-zA-Z0-9]{8}$', source):
        print(f"🔍 Buscando ID {source} pela API...")
        return fetch_h2h_text(source)
    
    # Última tentativa: trata como URL
    match_id = re.search(r'([a-zA-Z0-9]{8})', source)
    if match_id:
        return fetch_h2h_text(match_id.group(1))
    
    print(f"⚠️ Não foi possível interpretar: {source}")
    return None

# ------------------------------------------------------------
# 2. Parser (mantido, extrai 19 jogos)
# ------------------------------------------------------------
def parse_h2h(text: str, max_games=19):
    """Extrai os últimos max_games de cada time."""
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
                teams[team_name].append({
                    'opponent': opp,
                    'is_home': is_home,
                    'goals_for': gf,
                    'goals_against': ga,
                    'result': res
                })
                count += 1
            except:
                continue
    return dict(teams)

# ------------------------------------------------------------
# 3. Probabilidades (1X2, Overs, Cantos)
# ------------------------------------------------------------
def compute_probs(home_data, away_data, max_games=19):
    h = home_data[-max_games:]
    a = away_data[-max_games:]
    
    # 1X2
    home_home = [m for m in h if m['is_home']]
    away_away = [m for m in a if not m['is_home']]
    
    def _1x2(home_matches, away_matches):
        home_win = sum(1 for m in home_matches if m['result'] in ('w','wo')) / len(home_matches) if home_matches else 0.35
        away_win = sum(1 for m in away_matches if m['result'] in ('w','wo')) / len(away_matches) if away_matches else 0.30
        draw_h = sum(1 for m in home_matches if m['result'] == 'd') / len(home_matches) if home_matches else 0.25
        draw_a = sum(1 for m in away_matches if m['result'] == 'd') / len(away_matches) if away_matches else 0.25
        draw = (draw_h + draw_a) / 2
        total = home_win + draw + away_win
        if total > 0:
            home_win /= total
            draw /= total
            away_win /= total
        return home_win, draw, away_win
    
    home_win, draw, away_win = _1x2(home_home, away_away)
    
    # Overs (todos os jogos)
    all_goals = [m['goals_for'] + m['goals_against'] for m in h + a]
    total = len(all_goals)
    over_0_5 = sum(g > 0.5 for g in all_goals) / total if total else 0.95
    over_1_5 = sum(g > 1.5 for g in all_goals) / total if total else 0.8
    over_2_5 = sum(g > 2.5 for g in all_goals) / total if total else 0.55
    
    # Cantos (modelo fixo)
    return {
        'home_win': home_win,
        'draw': draw,
        'away_win': away_win,
        'over_0_5': over_0_5,
        'over_1_5': over_1_5,
        'over_2_5': over_2_5,
        'corners_8_5': 0.55,
        'corners_9_5': 0.45,
        'corners_10_5': 0.35
    }

# ------------------------------------------------------------
# 4. Tabela por partida e seleções
# ------------------------------------------------------------
def format_match_table(home, away, probs):
    lines = [f"📊 *{home} x {away}*"]
    lines.append(f"Vitória {home}: {probs['home_win']*100:.1f}%")
    lines.append(f"Empate: {probs['draw']*100:.1f}%")
    lines.append(f"Vitória {away}: {probs['away_win']*100:.1f}%")
    lines.append(f"Over 0.5: {probs['over_0_5']*100:.1f}%")
    lines.append(f"Over 1.5: {probs['over_1_5']*100:.1f}%")
    lines.append(f"Over 2.5: {probs['over_2_5']*100:.1f}%")
    lines.append(f"Cantos +8.5: {probs['corners_8_5']*100:.1f}%")
    lines.append(f"Cantos +9.5: {probs['corners_9_5']*100:.1f}%")
    lines.append(f"Cantos +10.5: {probs['corners_10_5']*100:.1f}%")
    return "\n".join(lines)

def get_selections(probs, home, away):
    match_label = f"{home} x {away}"
    sels = []
    sels.append((f"{match_label}: Vitória {home}", probs['home_win']))
    sels.append((f"{match_label}: Empate", probs['draw']))
    sels.append((f"{match_label}: Vitória {away}", probs['away_win']))
    sels.append((f"{match_label}: Over 0.5", probs['over_0_5']))
    sels.append((f"{match_label}: Over 1.5", probs['over_1_5']))
    sels.append((f"{match_label}: Over 2.5", probs['over_2_5']))
    sels.append((f"{match_label}: Cantos +8.5", probs['corners_8_5']))
    sels.append((f"{match_label}: Cantos +9.5", probs['corners_9_5']))
    sels.append((f"{match_label}: Cantos +10.5", probs['corners_10_5']))
    return sels

# ------------------------------------------------------------
# 5. Geração dos bilhetes (simples ou múltiplos)
# ------------------------------------------------------------
def generate_top_tickets(all_sels, top_n=3):
    by_match = defaultdict(list)
    for desc, prob in all_sels:
        match_key = desc.split(":")[0].strip()
        by_match[match_key].append((desc, prob))
    
    # Ordena seleções de cada partida
    for match_key in by_match:
        by_match[match_key].sort(key=lambda x: x[1], reverse=True)
    
    match_keys = list(by_match.keys())
    
    if len(match_keys) == 1:
        # Apenas uma partida → 3 apostas simples
        single = by_match[match_keys[0]][:top_n]
        tickets = []
        for i, (desc, prob) in enumerate(single):
            tickets.append({'bets': [(desc, prob)], 'combined_prob': prob})
        return tickets
    
    # Múltiplas partidas: combinar 1 seleção de cada
    combos = list(product(*[by_match[k] for k in match_keys]))
    scored = []
    for combo in combos:
        combined = 1.0
        for _, p in combo:
            combined *= p
        scored.append((combo, combined))
    scored.sort(key=lambda x: x[1], reverse=True)
    
    seen = set()
    tickets = []
    for combo, prob in scored:
        ids = tuple(sorted(desc for desc, _ in combo))
        if ids not in seen:
            seen.add(ids)
            tickets.append({'bets': list(combo), 'combined_prob': prob})
        if len(tickets) >= top_n:
            break
    return tickets

# ------------------------------------------------------------
# 6. Formatação e envio Telegram
# ------------------------------------------------------------
def format_ticket(ticket, index):
    lines = [f"🎫 Bilhete {index+1}"]
    for desc, prob in ticket['bets']:
        lines.append(f"• {desc} → {prob*100:.1f}%")
    lines.append(f"🔹 Probabilidade combinada: {ticket['combined_prob']*100:.2f}%")
    return "\n".join(lines)

async def send_telegram(text):
    bot = Bot(token=TELEGRAM_TOKEN)
    # Suporte a múltiplos chat IDs separados por vírgula
    ids = [cid.strip() for cid in TELEGRAM_CHAT_ID.split(',') if cid.strip()]
    for cid in ids:
        try:
            await bot.send_message(chat_id=cid, text=text, parse_mode='Markdown')
        except Exception as e:
            print(f"⚠️ Erro ao enviar para {cid}: {e}")

# ------------------------------------------------------------
# 7. Main (com chamadas ao banco)
# ------------------------------------------------------------
async def main():
    if len(sys.argv) < 2:
        print("Uso: python analisador_final.py <id_ou_arquivo> ...")
        return
    
    all_sels = []
    tables = []
    
    for arg in sys.argv[1:]:
        raw = load_raw_text(arg)
        if not raw:
            continue
        
        data = parse_h2h(raw, max_games=19)
        if len(data) < 2:
            print(f"⚠️ {arg}: menos de 2 times encontrados.")
            continue
        
        home, away = list(data.keys())[:2]
        print(f"✅ {home} x {away}")
        
        probs = compute_probs(data[home], data[away])
        tables.append(format_match_table(home, away, probs))
        sels = get_selections(probs, home, away)
        all_sels.extend(sels)
        
        # ✅ Chamada 1: salvar partida e probabilidades no Supabase
        try:
            match_id = db.save_match(home, away, raw)
            db.save_probabilities(match_id, probs)
        except Exception as e:
            print(f"⚠️ Erro ao salvar no banco: {e}")
    
    if not tables:
        print("Nenhum jogo válido.")
        return
    
    # Exibe tabelas individuais
    full_output = "\n\n".join(tables)
    print(full_output)
    await send_telegram(full_output)
    
    # Gera e exibe bilhetes
    tickets = generate_top_tickets(all_sels)
    ticket_msg = ""
    for i, ticket in enumerate(tickets):
        msg = format_ticket(ticket, i)
        print(msg)
        print()
        ticket_msg += msg + "\n\n"
    
    if ticket_msg:
        await send_telegram(ticket_msg.strip())
        
        # ✅ Chamada 2: salvar os bilhetes gerados
        try:
            db.save_tickets(tickets)
        except Exception as e:
            print(f"⚠️ Erro ao salvar bilhetes no banco: {e}")

if __name__ == '__main__':
    asyncio.run(main())