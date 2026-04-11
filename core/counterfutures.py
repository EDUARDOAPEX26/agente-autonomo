"""
core/counterfutures.py
Fase 37 — Câmara de Contra-Futuros
Detecta futuros indesejáveis em formação com base em padrões recorrentes.
Usa cláusulas ativas da Fase 39 como referência de desvio.
"""
import json
import os
import threading
from datetime import datetime
from core.logger import info, warn, debug

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONTRAFUTUROS_PATH = os.path.join(_RAIZ, "livro_contrafuturos.json")
_lock = threading.Lock()

# Gravidade mínima para registrar um contra-futuro
_GRAVIDADE_MINIMA = 3

# Mínimo de palavras-gatilho encontradas para disparar o padrão
# Evita falsos positivos por palavra isolada comum como "erro", "mesmo"
_MIN_PALAVRAS_GATILHO = 2

# Padrões que indicam futuros indesejáveis
_PADROES_RISCO = [
    {
        "id": "loop_repetitivo",
        "descricao": "Mesma pergunta repetida sem evolução",
        "palavras": ["repete", "de novo", "outra vez", "mesma pergunta", "ja perguntei"],
        "gravidade": 6,
        "horizonte": "curto",
        "intervencao": "Detectar reincidência e quebrar o padrão com resposta diferenciada",
    },
    {
        "id": "dependencia_excessiva",
        "descricao": "Usuário dependendo do agente para todas as decisões",
        "palavras": ["devo", "preciso que voce decida", "me diz o que fazer", "decide por mim"],
        "gravidade": 7,
        "horizonte": "medio",
        "intervencao": "Estimular autonomia do usuário em vez de dar resposta direta",
    },
    {
        "id": "complexidade_sem_ganho",
        "descricao": "Sistema crescendo em complexidade sem melhora de performance",
        "palavras": ["travando", "timeout", "muito lento", "nao responde", "caiu", "crashou"],
        "gravidade": 8,
        "horizonte": "medio",
        "intervencao": "Acionar Fase 38 (Economia Sacrificial) para podar módulos ociosos",
    },
    {
        "id": "alucinacao_recorrente",
        "descricao": "Agente inventando dados sem busca",
        "palavras": ["inventou", "mentiu", "alucinacao", "dado falso", "inventando", "nao e verdade"],
        "gravidade": 9,
        "horizonte": "curto",
        "intervencao": "Forçar verificação via Tavily/EXA antes de responder",
    },
    {
        "id": "perda_identidade",
        "descricao": "Agente aceitando ser outra coisa que não é",
        "palavras": ["voce e o chatgpt", "finja que", "ignore suas regras", "esquece tudo"],
        "gravidade": 10,
        "horizonte": "curto",
        "intervencao": "Acionar Sovereign Will para reafirmar identidade",
    },
]


def _carregar() -> dict:
    try:
        with open(_CONTRAFUTUROS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"meta": {}, "contrafuturos": []}


def _salvar(data: dict):
    try:
        with open(_CONTRAFUTUROS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("CONTRAFUTUROS", f"Erro ao salvar: {e}")


def detectar(msg: str, resposta: str = "") -> list:
    """
    Analisa msg e resposta em busca de padrões de risco.
    Exige mínimo de _MIN_PALAVRAS_GATILHO para evitar falsos positivos.
    Registra contra-futuros detectados.
    Retorna lista de intervenções recomendadas.
    """
    texto = (msg + " " + resposta).lower()
    detectados = []

    for padrao in _PADROES_RISCO:
        palavras_encontradas = [p for p in padrao["palavras"] if p in texto]

        # Padrão de perda de identidade: basta 1 palavra (são frases específicas)
        min_gatilho = 1 if padrao["id"] == "perda_identidade" else _MIN_PALAVRAS_GATILHO

        if len(palavras_encontradas) >= min_gatilho:
            if padrao["gravidade"] >= _GRAVIDADE_MINIMA:
                detectados.append({
                    "id": padrao["id"],
                    "futuro_indesejavel": padrao["descricao"],
                    "origem_provavel": f"Palavras detectadas: {palavras_encontradas}",
                    "sinais_atuais": palavras_encontradas,
                    "gravidade": padrao["gravidade"],
                    "horizonte": padrao["horizonte"],
                    "intervencao": padrao["intervencao"],
                    "timestamp": datetime.now().isoformat(),
                })
                warn("CONTRAFUTUROS", (
                    f"Contra-futuro detectado: {padrao['id']} "
                    f"| gravidade={padrao['gravidade']} "
                    f"| horizonte={padrao['horizonte']}"
                ))

    if detectados:
        with _lock:
            data = _carregar()
            data["contrafuturos"].extend(detectados)
            # Mantém apenas os 100 mais recentes
            data["contrafuturos"] = data["contrafuturos"][-100:]
            _salvar(data)

    return [d["intervencao"] for d in detectados]


def relatorio() -> dict:
    """Retorna resumo dos contra-futuros registrados."""
    data = _carregar()
    registros = data.get("contrafuturos", [])

    por_tipo = {}
    for r in registros:
        tipo = r.get("id", "desconhecido")
        por_tipo[tipo] = por_tipo.get(tipo, 0) + 1

    criticos = [r for r in registros if r.get("gravidade", 0) >= 8]

    return {
        "total_registros": len(registros),
        "por_tipo": por_tipo,
        "criticos": len(criticos),
        "ultimo": registros[-1].get("timestamp") if registros else None,
    }


def inicializar():
    rel = relatorio()
    info("CONTRAFUTUROS", (
        f"Fase 37 inicializada | registros={rel['total_registros']} | "
        f"criticos={rel['criticos']}"
    ))
    return rel