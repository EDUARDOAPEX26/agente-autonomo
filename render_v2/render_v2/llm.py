from integrations.groq_client import chamar_groq

def pensar(msgs):
    try:
        resposta, _ = chamar_groq(msgs, 400)
        return resposta
    except Exception as e:
        return f"erro: {e}"
