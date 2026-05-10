from collections import defaultdict
from itertools import product
from functools import reduce

# ------------------------------------------------------------
# 1. Cálculo de probabilidades com peso por recência
# ------------------------------------------------------------
def compute_probs(home_data, away_data, live_corners=None, max_games=19, decay=0.9):
    h = home_data[-max_games:]
    a = away_data[-max_games:]

    # Pesos por recência (índice 0 = mais antigo, -1 = mais recente)
    weights_h = [decay ** (len(h) - 1 - i) for i in range(len(h))]
    weights_a = [decay ** (len(a) - 1 - i) for i in range(len(a))]

    # Separa jogos em casa do mandante e fora do visitante (com pesos)
    home_home = [(m, w) for m, w in zip(h, weights_h) if m['is_home']]
    away_away = [(m, w) for m, w in zip(a, weights_a) if not m['is_home']]

    def _1x2(matches_with_weights):
        if not matches_with_weights:
            return 0.35, 0.30, 0.30
        total_w = sum(w for _, w in matches_with_weights)
        hw = sum(w for m, w in matches_with_weights if m['result'] in ('w','wo')) / total_w
        draw = sum(w for m, w in matches_with_weights if m['result'] == 'd') / total_w
        aw = sum(w for m, w in matches_with_weights if m['result'] == 'l') / total_w
        total = hw + draw + aw
        if total > 0:
            hw /= total; draw /= total; aw /= total
        return hw, draw, aw

    hw, draw, aw = _1x2(home_home + away_away)

    # Gols também ponderados
    all_weighted_goals = []
    total_weight = 0.0
    for m, w in zip(h, weights_h):
        all_weighted_goals.append((m['goals_for'] + m['goals_against']) * w)
        total_weight += w
    for m, w in zip(a, weights_a):
        all_weighted_goals.append((m['goals_for'] + m['goals_against']) * w)
        total_weight += w

    if total_weight > 0:
        avg_goals = sum(all_weighted_goals) / total_weight
    else:
        avg_goals = 2.5

    over_0_5 = min(0.95, max(0.60, avg_goals / 3.0))
    over_1_5 = min(0.85, max(0.40, avg_goals / 2.5))
    over_2_5 = min(0.70, max(0.20, avg_goals / 2.0))

    # Cantos
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

# ------------------------------------------------------------
# 2. Geração de seleções (mantida)
# ------------------------------------------------------------
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

# ------------------------------------------------------------
# 3. Enriquecimento com odds reais
# ------------------------------------------------------------
def enrich_selections_with_odds(selections, real_odds_dict):
    """
    real_odds_dict: ex.: {'bet365': {'home': 3.3, 'draw': 3.8, 'away': 2.01}, ...}
    Retorna [(desc, prob, odd), ...] com a menor odd disponível para o mercado.
    """
    enriched = []
    for desc, prob in selections:
        if 'Vitória' in desc:
            mercado = 'home' if 'Vitória' in desc and 'Empate' not in desc else 'draw' if 'Empate' in desc else 'away'
        elif 'Over' in desc:
            # Odds de Over/Under não estão implementadas no momento (retornamos None)
            enriched.append((desc, prob, None))
            continue
        elif 'Cantos' in desc:
            enriched.append((desc, prob, None))
            continue
        else:
            enriched.append((desc, prob, None))
            continue

        # Encontra a menor odd entre as casas
        best_odd = None
        for house, odds in real_odds_dict.items():
            if mercado in odds:
                if best_odd is None or float(odds[mercado]) < best_odd:
                    best_odd = float(odds[mercado])
        enriched.append((desc, prob, best_odd))
    return enriched

# ------------------------------------------------------------
# 4. Construção de bilhetes (com EV)
# ------------------------------------------------------------
def market_type(desc: str) -> str:
    if 'Vitória' in desc or 'Empate' in desc:
        return '1x2'
    if 'Over' in desc:
        return 'over'
    if 'Cantos' in desc:
        return 'corners'
    return 'other'

def build_tickets(all_sels: list,
                  profiles: list = None,
                  max_sels_per_match: int = 6,
                  used_matches: set = None) -> list:
    """
    all_sels: lista de tuplas (desc, prob) ou (desc, prob, odd).
    profiles: perfis de bilhete.
    Retorna lista de bilhetes com 'bets', 'combined_prob', 'profile', 'combined_odd', 'ev'.
    """
    if profiles is None:
        profiles = [
            ("Conservador", 4, {"min_corners": 0, "min_1x2": 0}),
            ("Moderado", 5, {"min_corners": 2}),
            ("Turbo", 6, {"min_corners": 2, "min_1x2": 1}),
        ]

    # Agrupa por partida
    by_match = defaultdict(list)
    for item in all_sels:
        desc = item[0]
        prob = item[1]
        odd = item[2] if len(item) > 2 else None
        mk = desc.split(":")[0].strip()
        # Calcula EV se houver odd
        ev = (prob * odd - 1) if odd else None
        by_match[mk].append((desc, prob, odd, ev))

    # Ordena seleções de cada partida pelo maior EV (ou maior prob se não houver EV)
    for mk in by_match:
        by_match[mk].sort(key=lambda x: x[3] if x[3] is not None else x[1], reverse=True)

    match_keys = list(by_match.keys())
    if len(match_keys) < 2:
        return []

    if used_matches is None:
        used_matches = set()

    tickets = []

    for name, max_n, constr in profiles:
        sel = []
        current_odds = []
        for mk in match_keys:
            if mk in used_matches:
                continue
            for desc, prob, odd, ev in by_match[mk][:max_sels_per_match]:
                types = [market_type(x) for x,_,_,_ in sel] + [market_type(desc)]
                ok = True
                if types.count('corners') < constr.get('min_corners', 0):
                    ok = False
                if types.count('1x2') < constr.get('min_1x2', 0):
                    ok = False
                if ok:
                    sel.append((desc, prob, odd, ev))
                    used_matches.add(mk)
                    break
            if len(sel) >= max_n:
                break

        # Complementa se não atingiu mínimos
        if constr.get('min_corners', 0) > sum(1 for x,_,_,_ in sel if 'Cantos' in x):
            for mk in match_keys:
                if sum(1 for x,_,_,_ in sel if 'Cantos' in x) >= constr['min_corners']:
                    break
                for desc, prob, odd, ev in by_match[mk][:max_sels_per_match]:
                    if 'Cantos' in desc:
                        sel.append((desc, prob, odd, ev))
                        used_matches.add(mk)
                        break
        if constr.get('min_1x2', 0) > sum(1 for x,_,_,_ in sel if 'Vitória' in x or 'Empate' in x):
            for mk in match_keys:
                if sum(1 for x,_,_,_ in sel if 'Vitória' in x or 'Empate' in x) >= constr['min_1x2']:
                    break
                for desc, prob, odd, ev in by_match[mk][:max_sels_per_match]:
                    if 'Vitória' in desc or 'Empate' in desc:
                        sel.append((desc, prob, odd, ev))
                        used_matches.add(mk)
                        break

        if sel:
            combined_prob = reduce(lambda x,y: x*y, [p for _,p,_,_ in sel])
            # Odd combinada (produto das odds, se todas disponíveis)
            odds_list = [o for _,_,o,_ in sel if o is not None]
            combined_odd = reduce(lambda x,y: x*y, odds_list) if len(odds_list) == len(sel) else None
            # EV total: (combined_prob * combined_odd) - 1 se ambas existirem
            ev_total = (combined_prob * combined_odd - 1) if combined_odd else None
            tickets.append({
                'bets': [(desc, prob, odd) for desc, prob, odd, _ in sel],
                'combined_prob': combined_prob,
                'profile': name,
                'combined_odd': combined_odd,
                'ev': ev_total
            })

        if len(tickets) >= len(profiles):
            break

    # Ordena os bilhetes pelo EV total (se disponível), senão pela probabilidade combinada
    tickets.sort(key=lambda t: t['ev'] if t['ev'] is not None else t['combined_prob'], reverse=True)
    return tickets

# ------------------------------------------------------------
# 5. Formatação
# ------------------------------------------------------------
def format_ultra_ticket(ticket, index):
    profile = ticket.get('profile', 'Bilhete')
    lines = [f"🎫 *{profile}* #{index+1}"]
    for item in ticket['bets']:
        desc, prob, odd = item if len(item) == 3 else (item[0], item[1], None)
        line = f"• {desc} → {prob*100:.1f}%"
        if odd:
            line += f" (Odd: {odd:.2f})"
        lines.append(line)
    lines.append(f"🔹 Probabilidade combinada: {ticket['combined_prob']*100:.2f}%")
    if ticket.get('combined_odd'):
        lines.append(f"💎 Odd combinada real: {ticket['combined_odd']:.2f}")
        lines.append(f"📈 EV esperado: {ticket['ev']*100:.2f}%")
    else:
        odd_est = 1.0 / ticket['combined_prob'] if ticket['combined_prob'] > 0 else 0
        lines.append(f"💎 Odd justa estimada: {odd_est:.2f}")
    return "\n".join(lines)

## ----------- Funções legadas (compatibilidade) ----------
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