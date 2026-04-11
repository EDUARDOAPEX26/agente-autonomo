import os
import time
from groq import Groq
from dotenv import load_dotenv
load_dotenv()
from core.logger import info, warn, erro

GROQ_KEYS = [k for k in [
    os.getenv("GROQ_API_KEY"),
    os.getenv("GROQ_API_KEY_2"),
    os.getenv("GROQ_API_KEY_3"),
] if k]

groq_key_index = {"i": 0}

if not GROQ_KEYS:
    erro("GROQ", "Nenhuma chave configurada no .env — verifique GROQ_API_KEY")
else:
    info("GROQ", f"{len(GROQ_KEYS)} chave(s) configurada(s)")

def get_groq_cliente():
    if not GROQ_KEYS:
        raise Exception("Nenhuma chave GROQ disponivel — configure GROQ_API_KEY no .env")
    return Groq(api_key=GROQ_KEYS[groq_key_index["i"]])

def proxima_groq_key():
    groq_key_index["i"] = (groq_key_index["i"] + 1) % len(GROQ_KEYS)
    info("GROQ", f"Trocando para chave {groq_key_index['i'] + 1}/{len(GROQ_KEYS)}")

def chamar_groq(msgs, max_tokens=400):
    inicio = time.time()
    cliente = get_groq_cliente()
    r = cliente.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=msgs,
        max_tokens=max_tokens
    )
    duracao = time.time() - inicio
    # ── TELEMETRIA ────────────────────────────────────────────────────────────
    uso = r.usage
    info("GROQ", (
        f"chave {groq_key_index['i']+1} | {duracao:.1f}s | "
        f"prompt={uso.prompt_tokens} completion={uso.completion_tokens} "
        f"total={uso.total_tokens}"
    ))
    return r.choices[0].message.content, uso