from collections import defaultdict
from itertools import product
from functools import reduce

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