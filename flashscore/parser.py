import re
from collections import defaultdict

def parse_h2h(text: str, max_games=19):
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

def parse_live_stats(text: str):
    """Retorna escanteios do feed de estatísticas ao vivo (df_st_1)."""
    if not text or 'Escanteios' not in text:
        return (None, None)
    m = re.search(r'Escanteios¬SH÷(\d+)¬SI÷(\d+)', text)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (None, None)

def parse_match_events(raw: str):
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

def parse_match_detail(raw: str):
    meta = {}
    ref_match = re.search(r'MIT÷REF¬MIV÷([^¬]+)', raw)
    if ref_match:
        meta['referee'] = ref_match.group(1)
    stadium_match = re.search(r'MIT÷VEN¬MIV÷([^¬]+)', raw)
    if stadium_match:
        meta['stadium'] = stadium_match.group(1)
    cap_match = re.search(r'MIT÷CAP¬MIV÷([^¬]+)', raw)
    if cap_match:
        try:
            meta['capacity'] = int(cap_match.group(1).replace(' ', ''))
        except:
            pass
    tv_match = re.search(r'TA÷([^¬]+)', raw)
    if tv_match:
        meta['tv_channels'] = tv_match.group(1).strip()
    feeds_match = re.search(r'DX÷([^¬]+)', raw)
    if feeds_match:
        meta['available_feeds'] = feeds_match.group(1).strip()
    return meta

def parse_live_time(raw: str):
    if not raw:
        return None, None
    status_match = re.search(r'DA÷(\d+)', raw)
    minute_match = re.search(r'DB÷(\d+)', raw)
    status = int(status_match.group(1)) if status_match else None
    minute = int(minute_match.group(1)) if minute_match else None
    return status, minute