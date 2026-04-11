# core/gravity_detector.py
"""
Fase 24 — Núcleo de Gravidade.

Detecta o vetor profundo do usuário — aquilo para onde ele está sendo puxado
ao longo do tempo, mesmo quando fala de assuntos diferentes.

Diferença de tema vs gravidade:
  tema     = o que a pessoa fala (automação, dinheiro, rotina, IA)
  gravidade = para onde ela está sendo puxada (construir independência, dominar um sistema)

A gravidade emerge do padrão de assuntos ao longo do tempo.
Um único assunto não define gravidade — o vetor entre vários define.

Estrutura de uma entrada gravitacional:
{
    "tema":       str,   # tema detectado na interação
    "dominio":    str,   # domínio semântico (controle | crescimento | liberdade | ...)
    "timestamp":  str,
    "peso":       float, # 0.0–1.0 — intensidade do sinal
}

O campo gravitacional é calculado agregando entradas por domínio.
"""

import json
import os
import threading
from datetime import datetime, timedelta
from core.logger import info, warn, debug

GRAVIDADE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "livro_gravidade.json"
)

_cache = {"dados": None}
_lock  = threading.Lock()

# ── DOMÍNIOS GRAVITACIONAIS ───────────────────────────────────────────────────
# Mais profundos que temas — são vetores de existência
_DOMINIOS_GRAVIDADE = {
    "controle": [
        "autonomia", "independente", "independência", "controle", "dominar",
        "sem depender", "por conta própria", "meu sistema", "minhas regras",
        "sem supervisão", "sozinho", "livre",
    ],
    "crescimento": [
        "crescer", "evoluir", "expandir", "escalar", "resultado",
        "próximo nível", "fase", "subir", "avançar", "progredir",
        "melhorar", "desenvolver", "aprender",
    ],
    "potencia": [
        "potência", "poder", "força", "eficiência", "produtividade",
        "menos esforço", "mais resultado", "alavanca", "multiplicar",
        "otimizar", "automatizar", "sistema",
    ],
    "construcao": [
        "construir", "criar", "fazer", "projeto", "produto",
        "lançar", "implementar", "colocar no ar", "entregar",
        "publicar", "subir", "deploy", "produção",
    ],
    "clareza": [
        "entender", "compreender", "clareza", "visão", "saber",
        "descobrir", "definir", "decidir", "escolher", "direção",
        "foco", "prioridade", "o que importa",
    ],
    "estabilidade": [
        "estável", "consistente", "confiável", "robusto", "duradouro",
        "sustentável", "sem quebrar", "sem falhar", "sempre funciona",
        "base sólida", "fundação",
    ],
    "transformacao": [
        "transformar", "mudar", "virar", "novo", "diferente",
        "quebrar padrão", "sair de", "deixar de", "começar a",
        "outro nível", "ruptura", "metamorfose",
    ],
}

# ── SINAIS DE INTENSIDADE ─────────────────────────────────────────────────────
# Palavras que aumentam o peso do sinal
_INTENSIFICADORES = [
    "muito", "sempre", "nunca", "jamais", "preciso", "necessito",
    "urgente", "fundamental", "essencial", "crítico", "principal",
    "mais importante", "o que mais", "acima de tudo",
]

_JANELA_DIAS = 30   # analisa últimos 30 dias
_MIN_SINAIS  = 3    # mínimo de sinais para calcular gravidade


# ── PERSISTÊNCIA ─────────────────────────────────────────────────────────────

def _carregar() -> list:
    if _cache["dados"] is not None:
        return _cache["dados"]
    if not os.path.exists(GRAVIDADE_PATH):
        _cache["dados"] = []
        return []
    try:
        with open(GRAVIDADE_PATH, "r", encoding="utf-8") as f:
            _cache["dados"] = json.load(f)
            return _cache["dados"]
    except Exception:
        _cache["dados"] = []
        return []


def _salvar(dados: list):
    try:
        with open(GRAVIDADE_PATH, "w", encoding="utf-8") as f:
            json.dump(dados[-1000:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("GRAVIDADE", f"Erro ao salvar: {e}")


# ── DETECÇÃO ─────────────────────────────────────────────────────────────────

def _detectar_dominio(texto: str) -> list[tuple]:
    """
    Detecta domínios gravitacionais no texto.
    Retorna lista de (dominio, peso) ordenada por peso.
    """
    t = texto.lower()
    resultados = []

    for dominio, palavras in _DOMINIOS_GRAVIDADE.items():
        hits = sum(1 for p in palavras if p in t)
        if hits > 0:
            # Peso base + bônus por intensificadores
            intensidade = sum(1 for i in _INTENSIFICADORES if i in t)
            peso = min(1.0, (hits * 0.3) + (intensidade * 0.1))
            resultados.append((dominio, round(peso, 2)))

    return sorted(resultados, key=lambda x: x[1], reverse=True)


def registrar(msg: str, resposta: str = ""):
    """
    Registra sinais gravitacionais de uma interação.
    Chamado pelo pipeline após cada interação.
    """
    texto = msg + " " + resposta
    dominios = _detectar_dominio(texto)

    if not dominios:
        return

    with _lock:
        dados = _carregar()
        agora = datetime.now().isoformat()

        for dominio, peso in dominios[:3]:  # top 3 domínios por interação
            dados.append({
                "dominio":   dominio,
                "peso":      peso,
                "trecho":    msg[:100],
                "timestamp": agora,
            })
            debug("GRAVIDADE", f"Sinal: {dominio} | peso={peso}")

        _cache["dados"] = dados
        threading.Thread(target=_salvar, args=(dados,), daemon=True).start()


# ── CAMPO GRAVITACIONAL ───────────────────────────────────────────────────────

def calcular_campo() -> dict:
    """
    Calcula o campo gravitacional atual — agregação dos sinais recentes.
    Retorna dict com domínio → força acumulada, ordenado por força.

    Retorna {} se não há dados suficientes.
    """
    dados = _carregar()
    corte = datetime.now() - timedelta(days=_JANELA_DIAS)

    recentes = [
        e for e in dados
        if _ts(e.get("timestamp", "")) >= corte
    ]

    if len(recentes) < _MIN_SINAIS:
        return {}

    campo = {}
    for e in recentes:
        d = e.get("dominio", "")
        p = e.get("peso", 0.1)
        campo[d] = campo.get(d, 0.0) + p

    # Normaliza para 0-1
    total = sum(campo.values())
    if total > 0:
        campo = {k: round(v / total, 3) for k, v in campo.items()}

    return dict(sorted(campo.items(), key=lambda x: x[1], reverse=True))


def vetor_principal() -> str | None:
    """
    Retorna o domínio gravitacional dominante.
    None se dados insuficientes.
    """
    campo = calcular_campo()
    if not campo:
        return None
    return next(iter(campo))


def descricao_vetor() -> str:
    """
    Retorna descrição legível do vetor de existência do usuário.
    Usada pelo pipeline para personalizar contexto.
    """
    campo = calcular_campo()
    if not campo:
        return ""

    _DESCRICOES = {
        "controle":     "construir autonomia e independência de sistemas externos",
        "crescimento":  "evoluir e alcançar próximos níveis consistentemente",
        "potencia":     "aumentar eficiência e transformar esforço em resultado",
        "construcao":   "criar e entregar produtos e sistemas concretos",
        "clareza":      "entender, definir direção e tomar decisões com foco",
        "estabilidade": "construir bases sólidas e confiáveis que durem",
        "transformacao": "romper padrões antigos e mudar de forma real",
    }

    top = list(campo.items())[:2]
    partes = [_DESCRICOES.get(d, d) for d, _ in top]

    if len(partes) == 1:
        return f"Vetor: {partes[0]}"
    return f"Vetor: {partes[0]} + {partes[1]}"


def _ts(iso: str) -> datetime:
    try:
        return datetime.fromisoformat(iso)
    except Exception:
        return datetime.min


# ── RESUMO ────────────────────────────────────────────────────────────────────

def resumo() -> dict:
    """Retorna resumo do campo gravitacional para diagnóstico."""
    dados  = _carregar()
    campo  = calcular_campo()
    vetor  = vetor_principal()
    desc   = descricao_vetor()

    corte   = datetime.now() - timedelta(days=_JANELA_DIAS)
    recentes = [e for e in dados if _ts(e.get("timestamp", "")) >= corte]

    return {
        "sinais_30d":   len(recentes),
        "campo":        campo,
        "vetor":        vetor,
        "descricao":    desc,
    }