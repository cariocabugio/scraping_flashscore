import time
import random
import requests
from typing import Optional

# User-Agents rotativos (navegadores reais, idiomas português/inglês)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]

def safe_get(url: str, headers: Optional[dict] = None, max_retries: int = 3, base_delay: float = 1.0) -> Optional[str]:
    """
    Faz uma requisição GET com segurança:
    - User-Agent aleatório a cada chamada
    - Timeout padrão de 15s
    - Jitter no intervalo entre chamadas (gerenciado pelo loop externo)
    - Retry com backoff exponencial + jitter em caso de erro
    """
    if headers is None:
        headers = {}
    headers["User-Agent"] = random.choice(USER_AGENTS)

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.RequestException as e:
            wait = base_delay * (2 ** attempt) + random.uniform(0, 2)
            print(f"⚠️ Tentativa {attempt+1}/{max_retries} falhou: {e}. Aguardando {wait:.1f}s...")
            time.sleep(wait)
    print(f"❌ Esgotadas as tentativas para {url}")
    return None