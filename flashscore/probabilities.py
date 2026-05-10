from collections import defaultdict
from itertools import product
from functools import reduce

# ------------------------------------------------------------
# Funções originais (mantidas para compatibilidade com analisador_final.py)
# ------------------------------------------------------------

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

# ----------- Funções originais de bilhetes (ainda usadas por analisador_final.py) ----------
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
    """Formatação simples (usada por analisador_final.py)."""
    lines = [f"🎫 Bilhete {index+1}"]
    for d,p in ticket['bets']:
        lines.append(f"• {d} → {p*100:.1f}%")
    lines.append(f"🔹 Probabilidade combinada: {ticket['combined_prob']*100:.2f}%")
    return "\n".join(lines)

# ------------------------------------------------------------
# NOVAS funções – Ultra Bingo (usadas por rodada.py)
# ------------------------------------------------------------

def market_type(desc: str) -> str:
    """Classifica a seleção: '1x2', 'over', 'corners' ou 'other'."""
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
    Gera bilhetes usando algoritmo guloso.
    profiles: lista de (nome, max_pernas, {restrições}).
    Restrições suportadas: min_corners, min_1x2.
    Retorna lista de dicts com 'bets', 'combined_prob', 'profile'.
    """
    if profiles is None:
        profiles = [
            ("Conservador", 4, {"min_corners": 0, "min_1x2": 0}),
            ("Moderado", 5, {"min_corners": 2}),
            ("Turbo", 6, {"min_corners": 2, "min_1x2": 1}),
        ]

    by_match = defaultdict(list)
    for desc, prob in all_sels:
        mk = desc.split(":")[0].strip()
        by_match[mk].append((desc, prob))
    for mk in by_match:
        by_match[mk].sort(key=lambda x: x[1], reverse=True)

    match_keys = list(by_match.keys())
    if len(match_keys) < 2:
        return []

    if used_matches is None:
        used_matches = set()

    tickets = []

    for name, max_n, constr in profiles:
        sel = []
        for mk in match_keys:
            if mk in used_matches:
                continue
            for d, p in by_match[mk][:max_sels_per_match]:
                types = [market_type(x) for x,_ in sel] + [market_type(d)]
                ok = True
                if types.count('corners') < constr.get('min_corners', 0):
                    ok = False
                if types.count('1x2') < constr.get('min_1x2', 0):
                    ok = False
                if ok:
                    sel.append((d, p))
                    used_matches.add(mk)
                    break
            if len(sel) >= max_n:
                break

        # Se não atingiu mínimos, complementa (mesmo repetindo times)
        if constr.get('min_corners', 0) > sum(1 for x,_ in sel if 'Cantos' in x):
            for mk in match_keys:
                if sum(1 for x,_ in sel if 'Cantos' in x) >= constr['min_corners']:
                    break
                for d, p in by_match[mk][:max_sels_per_match]:
                    if 'Cantos' in d:
                        sel.append((d, p))
                        used_matches.add(mk)
                        break
        if constr.get('min_1x2', 0) > sum(1 for x,_ in sel if 'Vitória' in x or 'Empate' in x):
            for mk in match_keys:
                if sum(1 for x,_ in sel if 'Vitória' in x or 'Empate' in x) >= constr['min_1x2']:
                    break
                for d, p in by_match[mk][:max_sels_per_match]:
                    if 'Vitória' in d or 'Empate' in d:
                        sel.append((d, p))
                        used_matches.add(mk)
                        break

        if sel:
            prob = reduce(lambda x,y: x*y, [p for _,p in sel])
            tickets.append({'bets': sel, 'combined_prob': prob, 'profile': name})

        if len(tickets) >= len(profiles):
            break

    return tickets

def format_ultra_ticket(ticket, index):
    """Formatação rica (com odd estimada) para o Ultra Bingo."""
    profile = ticket.get('profile', 'Bilhete')
    lines = [f"🎫 *{profile}* #{index+1}"]
    for d,p in ticket['bets']:
        lines.append(f"• {d} → {p*100:.1f}%")
    lines.append(f"🔹 Probabilidade combinada: {ticket['combined_prob']*100:.2f}%")
    odd = 1.0 / ticket['combined_prob'] if ticket['combined_prob'] > 0 else 0
    lines.append(f"💎 Odd justa estimada: {odd:.2f}")
    return "\n".join(lines)