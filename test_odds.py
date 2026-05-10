#!/usr/bin/env python3
import sys, requests, re, json

def fetch_env_from_url(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        match = re.search(r'window\.environment\s*=\s*(\{.*?\});', resp.text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        print("JSON de ambiente não encontrado.")
        return None
    except Exception as e:
        print(f"Erro: {e}")
        return None

def main():
    if len(sys.argv) < 2:
        print("Uso: python test_odds.py <ID_PARTIDA ou URL_COMPLETA>")
        return
    arg = sys.argv[1]
    if arg.startswith("http"):
        url = arg
    else:
        # Monta a URL completa (isso é um chute, melhor usar a URL real)
        url = f"https://www.flashscore.com.br/jogo/{arg}/"
    env = fetch_env_from_url(url)
    if not env: return
    odds = env.get("odds")
    if not odds:
        print("Campo 'odds' não encontrado.")
        return
    # Mostra as odds da bet365 (16) para 1X2
    try:
        home = odds["1x2"]["ft"]["16"]["home"]
        draw = odds["1x2"]["ft"]["16"]["draw"]
        away = odds["1x2"]["ft"]["16"]["away"]
        print(f"bet365 1X2: {home} / {draw} / {away}")
    except KeyError:
        print("Estrutura diferente. Mostrando chaves disponíveis:")
        print(json.dumps(odds, indent=2)[:2000])

if __name__ == '__main__':
    main()