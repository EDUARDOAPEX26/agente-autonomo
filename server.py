import os
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

class Mensagem(BaseModel):
    msg: str

@app.get("/ping")
def ping():
    return {"status": "pong"}

@app.get("/")
def home():
    return {"status": "Agente Online", "porta": os.getenv("PORT", "8080")}

@app.get("/status")
def status():
    try:
        from integrations.groq_client import GROQ_KEYS
        from integrations.tavily_client import tavily_disponivel
        return {
            "status": "online",
            "groq_chaves": len(GROQ_KEYS),
            "tavily": tavily_disponivel(),
        }
    except Exception as e:
        return {"status": "parcial", "erro": str(e)}

@app.post("/chat")
def chat(mensagem: Mensagem):
    try:
        from core.pipeline import executar_pipeline
        resposta, api = executar_pipeline(mensagem.msg)
        return {"resposta": resposta, "api": api}
    except Exception as e:
        return {"erro": str(e)}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)