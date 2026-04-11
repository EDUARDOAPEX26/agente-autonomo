import os
import requests
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def testar_tudo():
    print("--- INICIANDO TESTES EM PYTHON ---")

    # 1. Teste Cerebras
    try:
        client = OpenAI(api_key=os.getenv("CEREBRAS_API_KEY"), base_url="https://api.cerebras.ai/v1")
        res = client.chat.completions.create(model="llama3.1-8b", messages=[{"role": "user", "content": "Oi"}])
        print("✅ Cerebras: OK")
    except Exception as e:
        print(f"❌ Cerebras: Erro ({e})")

    # 2. Teste Tavily
    try:
        t_key = os.getenv("TAVILY_API_KEY")
        resp = requests.post("https://api.tavily.com/search", json={
            "api_key": t_key,
            "query": "IA hoje",
            "max_results": 1
        })
        if resp.status_code == 200:
            print(f"✅ Tavily: OK (Encontrou: {resp.json()['results'][0]['title']})")
        else:
            print(f"❌ Tavily: Erro {resp.status_code}")
    except Exception as e:
        print(f"❌ Tavily: Erro ({e})")

testar_tudo()
