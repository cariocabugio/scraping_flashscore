import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv('.env.local')

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(url, key)

def save_match(home_team: str, away_team: str, raw_data: str = None) -> int:
    """Insere uma partida e retorna o ID."""
    res = supabase.table("matches").insert({
        "home_team": home_team,
        "away_team": away_team,
        "raw_data": raw_data
    }).execute()
    return res.data[0]['id']

def get_match_today(home_team: str, away_team: str):
    """
    Busca uma partida com os mesmos times cadastrada hoje.
    Retorna o registro (com raw_data) ou None.
    """
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

def save_probabilities(match_id: int, probs: dict):
    """Salva as probabilidades de uma partida."""
    rows = []
    for market in ['home_win', 'draw', 'away_win']:
        rows.append({
            "match_id": match_id,
            "category": "1x2",
            "market": market,
            "probability": probs[market]
        })
    for market in ['over_0_5', 'over_1_5', 'over_2_5']:
        rows.append({
            "match_id": match_id,
            "category": "over",
            "market": market,
            "probability": probs[market]
        })
    for market in ['corners_8_5', 'corners_9_5', 'corners_10_5']:
        rows.append({
            "match_id": match_id,
            "category": "corners",
            "market": market,
            "probability": probs[market]
        })
    supabase.table("probabilities").insert(rows).execute()

def save_tickets(tickets: list):
    """Salva os bilhetes gerados."""
    rows = []
    for ticket in tickets:
        selections = [{"match": desc, "prob": prob} for desc, prob in ticket['bets']]
        rows.append({
            "combined_prob": ticket['combined_prob'],
            "selections": selections
        })
    if rows:
        supabase.table("tickets").insert(rows).execute()