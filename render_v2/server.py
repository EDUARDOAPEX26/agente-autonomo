from fastapi import FastAPI
from llm import pensar

app = FastAPI()

@app.get("/")
def home():
    return {"status": "ok"}

@app.post("/think")
def think(req: dict):
    texto = req.get("text", "")

    resposta = pensar([
        {"role": "user", "content": texto}
    ])

    return {"response": resposta}
