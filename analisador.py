#!/usr/bin/env python3
"""
Analisador Final  Múltiplos jogos, 3 bilhetes com 1X2, Gols e Escanteios
Uso: python analisador_final.py jogo1.txt jogo2.txt jogo3.txt ...
"""

import os
import sys
import re
import asyncio
from collections import defaultdict
from itertools import product

from dotenv import load_dotenv
from telegram import Bot

load_dotenv('.env.local')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')


# ------------------------------------------------------------
# 1. Parser de arquivo bruto
# ------------------------------------------------------------
def parse_h2h_file(text: str):
    """Retorna {team_name: [lista de jogos]} (mesmo parser de antes)."""
    flat = text.replace('\n', '')
    team_blocks = re.finditer(r'KB÷Últimos jogos:\s*(.+?)¬~KC÷(.*?)(?=~KB÷|~SA÷|~A1÷|$)', flat)
    teams = defaultdict(list)
    for match in team_blocks:
        team_name = match.group(1).strip()
        games_block = match.group(2)
        games = re.finditer(r'(?:~)?KC÷(.*?)(?=~KC÷|~KB÷|$)', games_block)
        for gm in games:
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
            except:
                continue
    return dict(teams)

# ------------------------------------------------------------
# 2. Cálculo de probabilidades (1X2, Overs, Cantos)
# ------------------------------------------------------------
def compute_match_probabilities(home_data, away_data, max_games=10):
    """
    Retorna dict com probs 1X2, gols e escanteios.
    :param home_data: lista de jogos recentes do time da casa
    :param away_data: lista de jogos recentes do time visitante
    """
    # Pega os últimos N jogos
    h = home_data[-max_games:] if len(home_data) >= max_games else home_data
    a = away_data[-max_games:] if len(away_data) >= max_games else away_data
    
    # --- 1X2 usando apenas os jogos em casa do mandante e fora do visitante ---
    home_home = [m for m in h if m['is_home']]
    away_away = [m for m in a if not m['is_home']]  # jogos fora
    
    def _1x2(home_matches, away_matches):
        # Vitória do time da casa (em casa)
        if home_matches:
            home_w = sum(1 for m in home_matches if m['result'] in ('w','wo'))
            home_win = home_w / len(home_matches)
        else:
            home_win = 0.4
        # Vitória do visitante (fora)
        if away_matches:
            away_w = sum(1 for m in away_matches if m['result'] in ('w','wo'))
            away_win = away_w / len(away_matches)
        else:
            away_win = 0.3
        # Empate = média de empates nos dois recortes
        home_d = sum(1 for m in home_matches if m['result'] == 'd') / len(home_matches) if home_matches else 0.25
        away_d = sum(1 for m in away_matches if m['result'] == 'd') / len(away_matches) if away_matches else 0.25
        draw = (home_d + away_d) / 2
        # Normaliza
        total = home_win + draw + away_win
        if total > 0:
            home_win /= total
            draw /= total
            away_win /= total
        return home_win, draw, away_win
    
    home_win, draw, away_win = _1x2(home_home, away_away)
    
    # --- Gols (média dos dois times) ---
    all_goals = [m['goals_for'] + m['goals_against'] for m in h + a]
    total_matches = len(all_goals)
    if total_matches:
        over_0_5 = sum(g > 0.5 for g in all_goals) / total_matches
        over_1_5 = sum(g > 1.5 for g in all_goals) / total_matches
        over_2_5 = sum(g > 2.5 for g in all_goals) / total_matches
    else:
        over_0_5 = 0.95; over_1_5 = 0.8; over_2_5 = 0.55
    
    # --- Escanteios (modelo fixo até termos dados reais) ---
    corners_8_5 = 0.55   # média geral
    corners_9_5 = 0.45
    corners_10_5 = 0.35
    
    return {
        'home_win': home_win,
        'draw': draw,
        'away_win': away_win,
        'over_0_5': over_0_5,
        'over_1_5': over_1_5,
        'over_2_5': over_2_5,
        'corners_8_5': corners_8_5,
        'corners_9_5': corners_9_5,
        'corners_10_5': corners_10_5
    }

# ------------------------------------------------------------
# 3. Gerar todas as seleções de uma partida
# ------------------------------------------------------------
def get_selections(probs, home_team, away_team):
    """
    Transforma o dicionário de probs em uma lista de seleções (nome, prob).
    """
    sel = []
    match_label = f"{home_team} x {away_team}"
    
    # 1X2
    sel.append((f"{match_label}: Vitória {home_team}", probs['home_win']))
    sel.append((f"{match_label}: Empate", probs['draw']))
    sel.append((f"{match_label}: Vitória {away_team}", probs['away_win']))
    
    # Overs gols
    sel.append((f"{match_label}: Over 0.5", probs['over_0_5']))
    sel.append((f"{match_label}: Over 1.5", probs['over_1_5']))
    sel.append((f"{match_label}: Over 2.5", probs['over_2_5']))
    
    # Escanteios (modelo)
    sel.append((f"{match_label}: Cantos +8.5", probs['corners_8_5']))
    sel.append((f"{match_label}: Cantos +9.5", probs['corners_9_5']))
    sel.append((f"{match_label}: Cantos +10.5", probs['corners_10_5']))
    
    return sel

# ------------------------------------------------------------
# 4. Montar os 3 melhores bilhetes (acumuladas)
# ------------------------------------------------------------
def build_top_tickets(all_selections, matches_count, top_n=3):
    """
    all_selections: list of (desc, prob)
    matches_count: int = quantos jogos diferentes temos
    Retorna lista de bilhetes (cada bilhete é uma lista de seleções).
    """
    # Agrupar seleções por partida (assumindo que o início do texto é único para cada jogo)
    # Vamos usar a primeira palavra-chave para agrupar
    by_match = defaultdict(list)
    for desc, prob in all_selections:
        # A descrição começa com "Time1 x Time2: "
        match_key = desc.split(":")[0].strip()
        by_match[match_key].append((desc, prob))
    
    # Para cada partida, ordenar seleções por prob decrescente e manter as melhores
    best_per_match = []
    for match_key, sels in by_match.items():
        sels.sort(key=lambda x: x[1], reverse=True)
        best_per_match.append(sels)  # lista de listas
    
    # Se tivermos vários jogos, combinar uma seleção de cada jogo
    if matches_count == 1:
        # Apenas uma partida: os 3 melhores palpites
        single = best_per_match[0][:top_n]
        return [{'bets': [single[i]], 'combined_prob': single[i][1]} for i in range(top_n)]
    
    # Combinar todas as possíveis combinações (1 de cada jogo) e ordenar por prob combinada
    combos = list(product(*best_per_match))
    # Calcular prob combinada
    scored = []
    for combo in combos:
        combined = 1.0
        for _, p in combo:
            combined *= p
        scored.append((combo, combined))
    scored.sort(key=lambda x: x[1], reverse=True)
    
    # Pegar os top_n, remove duplicatas (mesmo conjunto de seleções)
    seen = set()
    tickets = []
    for combo, prob in scored:
        # Identificador único: frases das seleções ordenadas
        ids = tuple(sorted(desc for desc, _ in combo))
        if ids not in seen:
            seen.add(ids)
            tickets.append({'bets': list(combo), 'combined_prob': prob})
        if len(tickets) >= top_n:
            break
    
    return tickets

# ------------------------------------------------------------
# 5. Formatação e envio Telegram
# ------------------------------------------------------------
def format_ticket(ticket, index):
    lines = [f"🎫 Bilhete {index+1}"]
    for desc, prob in ticket['bets']:
        lines.append(f"• {desc} → {prob*100:.1f}%")
    lines.append(f"🔹 Probabilidade combinada: {ticket['combined_prob']*100:.2f}%")
    return "\n".join(lines)

async def send_telegram(text):
    bot = Bot(token=TELEGRAM_TOKEN)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode='Markdown')

# ------------------------------------------------------------
# 6. Main
# ------------------------------------------------------------
async def main():
    if len(sys.argv) < 2:
        print("Uso: python analisador_final.py arq1.txt arq2.txt ...")
        return
    
    all_selections = []   # lista global de (descricao, prob)
    matches_count = len(sys.argv) - 1
    
    for filepath in sys.argv[1:]:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw = f.read()
        except Exception as e:
            print(f"❌ Erro ao ler {filepath}: {e}")
            continue
        
        data = parse_h2h_file(raw)
        if len(data) < 2:
            print(f"⚠️ {filepath}: não encontrei dois times. Ignorando.")
            continue
        
        home, away = list(data.keys())[:2]
        print(f"✅ {home} x {away}")
        
        probs = compute_match_probabilities(data[home], data[away])
        selections = get_selections(probs, home, away)
        all_selections.extend(selections)
    
    if not all_selections:
        print("Nenhum jogo válido encontrado.")
        return
    
    # Gerar os 3 melhores bilhetes combinados
    tickets = build_top_tickets(all_selections, matches_count, top_n=3)
    
    # Exibir no terminal e enviar Telegram
    final_msg = "🧠 **Análise Flashscore**\n\n"
    for i, ticket in enumerate(tickets):
        msg = format_ticket(ticket, i)
        print(msg)
        print()
        final_msg += msg + "\n\n"
    
    await send_telegram(final_msg.strip())

if __name__ == '__main__':
    asyncio.run(main())