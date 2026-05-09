import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv('.env.local')

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")   # use a secreta para escrita
supabase: Client = create_client(url, key)

# Teste rápido
res = supabase.table("matches").select("*").execute()
print("Conexão OK. Matches no banco:", len(res.data))