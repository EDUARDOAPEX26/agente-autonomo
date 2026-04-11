import os
import time
from dotenv import load_dotenv
load_dotenv()

from core.logger import info, warn

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
google_cliente = None

if GOOGLE_API_KEY:
    from google import genai
    google_cliente = genai.Client(api_key=GOOGLE_API_KEY)
    info("GOOGLE", "Cliente configurado")
else:
    warn("GOOGLE", "GOOGLE_API_KEY não configurada — fallback Google desativado")

def chamar_google(msgs):
    if not google_cliente:
        raise Exception("Google não configurado")
    inicio = time.time()
    texto = "\n".join([f"{m['role']}: {m['content']}" for m in msgs])
    r = google_cliente.models.generate_content(
        model="gemini-2.0-flash",
        contents=texto
    )
    info("GOOGLE", f"Respondeu em {time.time()-inicio:.1f}s")
    return r.text