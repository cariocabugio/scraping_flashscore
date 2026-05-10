import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv('.env.local')

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(url, key)

def save_match(home_team: str, away_team: str, raw_data: str = None) -> int:
    res = supabase.table("matches").insert({
        "home_team": home_team,
        "away_team": away_team,
        "raw_data": raw_data
    }).execute()
    return res.data[0]['id']

def get_match_today(home_team: str, away_team: str):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    res = supabase.table("matches") \
        .select("*") \
        .eq("home_team", home_team) \
        .eq("away_team", away_team) \
        .gte("created_at", today_start) \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()
    if res.data and len(res.data) > 0:
        return res.data[0]
    return None

def get_or_create_match(home_team: str, away_team: str, raw_data: str = None):
    """Retorna um registro existente de hoje ou cria um novo e retorna o dict."""
    match = get_match_today(home_team, away_team)
    if not match:
        match_id = save_match(home_team, away_team, raw_data)
        match = {'id': match_id, 'raw_data': raw_data}
    return match

def save_probabilities(match_id: int, probs: dict):
    rows = []
    for market in ['home_win', 'draw', 'away_win']:
        rows.append({"match_id": match_id, "category": "1x2", "market": market, "probability": probs[market]})
    for market in ['over_0_5', 'over_1_5', 'over_2_5']:
        rows.append({"match_id": match_id, "category": "over", "market": market, "probability": probs[market]})
    for market in ['corners_8_5', 'corners_9_5', 'corners_10_5']:
        rows.append({"match_id": match_id, "category": "corners", "market": market, "probability": probs[market]})
    supabase.table("probabilities").insert(rows).execute()

def save_tickets(tickets: list):
    rows = []
    for ticket in tickets:
        selections = [{"match": desc, "prob": prob} for desc, prob in ticket['bets']]
        rows.append({"combined_prob": ticket['combined_prob'], "selections": selections})
    if rows:
        supabase.table("tickets").insert(rows).execute()

# ----- Eventos -----
def save_match_events(match_id: int, events: list):
    rows = []
    for ev in events:
        rows.append({
            "match_id": match_id,
            "event_type": ev['event_type'],
            "event_code": ev['event_code'],
            "minute": ev['minute'],
            "extra_min": ev.get('extra_min', 0),
            "team": ev['team'],
            "player": ev.get('player'),
            "section": ev.get('section', ''),
            "raw_data": ev.get('raw', '')
        })
    if rows:
        supabase.table("match_events").insert(rows).execute()

def get_corners_for_match(match_id: int) -> dict:
    res = supabase.table("match_events") \
        .select("team") \
        .eq("match_id", match_id) \
        .eq("event_type", "corner") \
        .execute()
    home = sum(1 for r in res.data if r['team'] == 'home')
    away = sum(1 for r in res.data if r['team'] == 'away')
    return {'home': home, 'away': away}

# ----- Metadados da partida (dc_1) -----
def save_match_metadata(match_id: int, metadata: dict):
    supabase.table("match_metadata").insert({
        "match_id": match_id,
        "referee": metadata.get("referee"),
        "stadium": metadata.get("stadium"),
        "capacity": metadata.get("capacity"),
        "tv_channels": metadata.get("tv_channels"),
        "available_feeds": metadata.get("available_feeds")
    }).execute()

def get_match_metadata(match_id: int):
    res = supabase.table("match_metadata") \
        .select("*") \
        .eq("match_id", match_id) \
        .limit(1) \
        .execute()
    return res.data[0] if res.data else None

def save_ticket_with_selections(ticket_type: str, estimated_odd: float, selections: list, combined_prob: float):
    """
    Insere um bilhete e suas seleções associadas.
    selections é uma lista de dicts: [{'match_id': id, 'market': 'over_1_5', 'probability': 0.72}, ...]
    """
    # Insere o ticket
    res = supabase.table("tickets").insert({
        "combined_prob": combined_prob,
        "selections": selections,   # mantém compatibilidade com o campo JSON existente
        "ticket_type": ticket_type,
        "estimated_odd": estimated_odd
    }).execute()
    ticket_id = res.data[0]['id']

    # Insere cada seleção na nova tabela
    for sel in selections:
        supabase.table("ticket_selections").insert({
            "ticket_id": ticket_id,
            "match_id": sel.get('match_id'),
            "market": sel.get('market'),
            "probability": sel.get('probability')
        }).execute()