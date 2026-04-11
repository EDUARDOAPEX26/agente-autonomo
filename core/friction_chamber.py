"""
core/friction_chamber.py
Fase 23 — Câmara de Fricção.

Detecta padrões de tensão repetida no comportamento do usuário.
Não julga — mede onde a potência está vazando.

Fricção = quando o usuário quer X mas consistentemente produz não-X.

Exemplos detectados:
  - quer velocidade, mas toda semana tem débito técnico acumulado
  - quer autonomia, mas volta com a mesma dúvida
  - quer evolução, mas repete o mesmo padrão improdutivo

Regra dos 3 ciclos: se o mesmo padrão aparecer 3x, o pipeline muda de modo.
"""

import json
import os
import threading
from collections import defaultdict
from datetime import datetime
from core.logger import info, warn, debug

FRICCAO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "livro_friccao.json"
)

_cache = {"dados": None}
_lock  = threading.Lock()

# ── PADRÕES DE FRICÇÃO ────────────────────────────────────────────────────────
# Cada padrão tem: sinal_desejo + sinal_comportamento_oposto + nome + descricao
_PADROES = [
    {
        "id":       "velocidade_vs_complexidade",
        "desejo":   ["rápido", "urgente", "prazo", "agora", "logo"],
        "oposto":   ["débito", "refatorar", "complexo", "reescrever", "acumulou"],
        "nome":     "Velocidade vs Complexidade",
        "descricao": "Quer velocidade mas acumula complexidade que depois trava",
    },
    {
        "id":       "autonomia_vs_dependencia",
        "desejo":   ["autonomia", "independente", "sozinho", "sem ajuda", "por conta"],
        "oposto":   ["mesma dúvida", "mesmo problema", "de novo", "não sei", "preciso de"],
        "nome":     "Autonomia vs Dependência",
        "descricao": "Quer autonomia mas retorna com os mesmos pontos de travamento",
    },
    {
        "id":       "evolucao_vs_preservacao",
        "desejo":   ["evoluir", "crescer", "mudar", "melhorar", "próxima fase"],
        "oposto":   ["mesmo padrão", "como antes", "voltou", "ainda está", "não mudou"],
        "nome":     "Evolução vs Preservação",
        "descricao": "Quer evolução mas preserva estruturas que impedem mudança",
    },
    {
        "id":       "ousadia_vs_cautela",
        "desejo":   ["arriscar", "tentar", "inovar", "novo", "diferente", "ousado"],
        "oposto":   ["não funciona", "voltou atrás", "reverteu", "muito cedo", "não era hora"],
        "nome":     "Ousadia vs Cautela Excessiva",
        "descricao": "Quer ousadia mas pune o risco antes dele se desenvolver",
    },
    {
        "id":       "decisao_vs_analise",
        "desejo":   ["decidir", "definir", "escolher", "bater martelo", "fechar"],
        "oposto":   ["mas e se", "por outro lado", "depende", "ainda analisando", "mais uma opção"],
        "nome":     "Decisão vs Análise Infinita",
        "descricao": "Quer decidir mas continua analisando sem chegar a conclusão",
    },
]

# ── PERSISTÊNCIA ─────────────────────────────────────────────────────────────

def _carregar() -> dict:
    if _cache["dados"] is not None:
        return _cache["dados"]
    if not os.path.exists(FRICCAO_PATH):
        _cache["dados"] = {}
        return {}
    try:
        with open(FRICCAO_PATH, "r", encoding="utf-8") as f:
            _cache["dados"] = json.load(f)
            return _cache["dados"]
    except Exception:
        _cache["dados"] = {}
        return {}


def _salvar(dados: dict):
    try:
        with open(FRICCAO_PATH, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("FRICCAO", f"Erro ao salvar: {e}")


# ── DETECÇÃO ─────────────────────────────────────────────────────────────────

def _detectar_padrao(texto: str) -> list:
    """
    Detecta padrões de fricção em um texto.
    Retorna lista de IDs dos padrões detectados.
    """
    t = texto.lower()
    detectados = []

    for padrao in _PADROES:
        tem_desejo  = any(p in t for p in padrao["desejo"])
        tem_oposto  = any(p in t for p in padrao["oposto"])
        if tem_desejo and tem_oposto:
            detectados.append(padrao["id"])
            debug("FRICCAO", f"Fricção detectada: {padrao['nome']}")

    return detectados


def registrar(msg: str, resposta: str = ""):
    """
    Analisa a interação em busca de padrões de fricção.
    Registra e retorna lista de fricções detectadas.
    """
    texto_completo = msg + " " + resposta
    detectados = _detectar_padrao(texto_completo)

    if not detectados:
        return []

    with _lock:
        dados = _carregar()
        agora = datetime.now().isoformat()

        for pid in detectados:
            if pid not in dados:
                dados[pid] = {
                    "id":         pid,
                    "contagem":   0,
                    "ultima_vez": agora,
                    "historico":  [],
                }

            dados[pid]["contagem"] += 1
            dados[pid]["ultima_vez"] = agora
            dados[pid]["historico"].append({
                "timestamp": agora,
                "trecho":    msg[:100],
            })
            # Mantém só os últimos 20
            dados[pid]["historico"] = dados[pid]["historico"][-20:]

            info("FRICCAO", (
                f"Padrão '{pid}' | contagem={dados[pid]['contagem']}"
            ))

        _cache["dados"] = dados
        threading.Thread(target=_salvar, args=(dados,), daemon=True).start()

    return detectados


# ── REGRA DOS 3 CICLOS ────────────────────────────────────────────────────────

def padroes_criticos(limiar: int = 3) -> list:
    """
    Retorna padrões que atingiram o limiar de repetição.
    Esses padrões indicam que o modo de resposta deve mudar.
    """
    dados = _carregar()
    criticos = []

    for pid, entrada in dados.items():
        if entrada.get("contagem", 0) >= limiar:
            padrao_info = next((p for p in _PADROES if p["id"] == pid), None)
            if padrao_info:
                criticos.append({
                    **padrao_info,
                    "contagem":   entrada["contagem"],
                    "ultima_vez": entrada.get("ultima_vez", ""),
                })

    return sorted(criticos, key=lambda x: x["contagem"], reverse=True)


def modo_resposta(msg: str) -> str:
    """
    Retorna o modo de resposta recomendado baseado nos padrões críticos.

    Modos:
      "normal"     — sem padrão crítico detectado
      "compressao" — comprime para uma sentença brutal, sem análise
      "confronto"  — confronta a incoerência central diretamente
      "acao"       — exige microação irreversivelmente pequena
    """
    criticos = padroes_criticos()
    if not criticos:
        return "normal"

    # Detecta fricção na mensagem atual
    detectados_agora = _detectar_padrao(msg)
    if not detectados_agora:
        return "normal"

    # Verifica se a fricção atual é um padrão crítico
    ids_criticos = {c["id"] for c in criticos}
    if not any(d in ids_criticos for d in detectados_agora):
        return "normal"

    # Escolhe modo baseado na contagem mais alta
    maior = criticos[0]
    contagem = maior["contagem"]

    if contagem >= 6:
        return "compressao"   # 6+ repetições: resposta brutal e curta
    elif contagem >= 4:
        return "confronto"    # 4-5: confronta diretamente
    else:
        return "acao"         # 3: exige ação pequena e concreta


def gerar_observacao(padroes: list) -> str:
    """
    Gera observação não invasiva sobre fricção detectada.
    Tom: curiosidade, não julgamento.
    """
    if not padroes:
        return ""

    p = padroes[0]
    contagem = p.get("contagem", 0)

    if contagem >= 6:
        return f"🔥 Nota: '{p['nome']}' apareceu {contagem}x. {p['descricao']}. Talvez valha uma pausa para examinar isso."
    elif contagem >= 3:
        return f"💡 Padrão recorrente: {p['descricao']}."

    return ""



def exportar_para_transmutacao() -> list:
    """
    Exporta padroes de friccao para o transmutation_engine.
    Ponte entre Fase 23 (Camara de Friccao) e Fase 25 (Motor de Transmutacao).
    """
    dados = _carregar()
    saida = []
    for pid, entrada in dados.items():
        saida.append({
            "id":         pid,
            "contagem":   entrada.get("contagem", 0),
            "ultima_vez": entrada.get("ultima_vez", ""),
            "historico":  entrada.get("historico", []),
        })
    return saida


def resumo() -> dict:
    """Retorna resumo dos padrões de fricção registrados."""
    dados = _carregar()
    return {
        "total_padroes": len(dados),
        "criticos":      len(padroes_criticos()),
        "padroes":       [
            {
                "id":       pid,
                "contagem": e.get("contagem", 0),
                "nome":     next((p["nome"] for p in _PADROES if p["id"] == pid), pid),
            }
            for pid, e in dados.items()
        ],
    }