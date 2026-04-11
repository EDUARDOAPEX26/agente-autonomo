# core/principle_registry.py
"""
Fase 20 — Motor de Coerência Cognitiva.
Registro de princípios explícitos e duráveis do usuário.

Diferença em relação ao belief_tracker:
  - Crenças: preferências inferidas da conversa, contagem >= 2 para virar operacional
  - Princípios: regras explicitamente declaradas, confiança alta desde o início (0.8)
                e nunca expiram a menos que o usuário as revise diretamente.

Estrutura de um princípio:
{
    "id":         str,     # hash curto do texto normalizado
    "texto":      str,     # texto do princípio
    "dominio":    str,     # mesmo mapeamento do belief_tracker
    "categoria":  str,     # trabalho | aprendizado | financeiro | relacionamento | outro
    "confianca":  float,   # começa em 0.8 — sobe com reforços, cai com revisão
    "contagem":   int,
    "ativo":      bool,
    "criado_em":  str,
    "ultima_vez": str,
}
"""

import json
import os
import hashlib
import threading
from datetime import datetime
from core.logger import info, debug, warn

PRINCIPIOS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "livro_principios.json"
)

_cache = {"dados": None}
_lock  = threading.Lock()

# ── PADRÕES QUE INDICAM PRINCÍPIO EXPLÍCITO ───────────────────────────────────
# Mais fortes que padrões de crença — o usuário está declarando uma regra
_PADROES_PRINCIPIO = [
    # Regras diretas
    "regra:", "regra minha:", "princípio:", "meu princípio",
    "nunca faço", "nunca vou", "sempre faço", "sempre vou",
    "não aceito", "não tolero", "jamais",
    # Lições aprendidas com custo
    "aprendi da pior forma", "aprendi que nunca", "aprendi que sempre",
    "erro que não repito", "não erro mais",
    # Comprometimentos
    "me comprometo", "me comprometi", "prometi para mim",
    "minha regra de ouro", "meu lema",
    # Declarações de valor
    "o que não abro mão", "o que não negocio",
    "linha que não cruzo", "limite que não ultrapasso",
]

# Palavras que confirmam que é uma declaração de princípio (não hipótese)
_CONFIRMADORES = [
    "sempre", "nunca", "jamais", "todo", "toda", "qualquer",
    "sem exceção", "invariavelmente", "obrigatoriamente",
]

# Categorias por palavras-chave
_CATEGORIAS = {
    "trabalho": [
        "trabalho", "projeto", "código", "deploy", "produção", "cliente",
        "prazo", "entrega", "reunião", "equipe", "time", "colaboração",
    ],
    "aprendizado": [
        "aprender", "estudo", "estudar", "curso", "conhecimento",
        "erro", "acerto", "experiência", "prática", "teste",
    ],
    "financeiro": [
        "dinheiro", "investimento", "gasto", "custo", "receita",
        "lucro", "prejuízo", "dívida", "poupança", "risco financeiro",
    ],
    "relacionamento": [
        "pessoa", "pessoas", "amigo", "família", "parceiro",
        "confiança", "respeito", "honestidade", "lealdade",
    ],
}


def _normalizar(texto: str) -> str:
    return " ".join(texto.lower().strip().split())


def _gerar_id(texto: str) -> str:
    return hashlib.md5(_normalizar(texto).encode()).hexdigest()[:8]


def _detectar_categoria(texto: str) -> str:
    t = texto.lower()
    for categoria, palavras in _CATEGORIAS.items():
        if any(p in t for p in palavras):
            return categoria
    return "outro"


def _detectar_dominio(texto: str) -> str:
    """Reutiliza mapeamento do belief_tracker para consistência."""
    _DOMINIOS = {
        "risco": ["risco", "seguro", "conservador", "cautela", "perda"],
        "crescimento": ["crescimento", "oportunidade", "expandir", "resultado"],
        "velocidade": ["rápido", "urgente", "prazo", "ágil", "velocidade"],
        "qualidade": ["qualidade", "detalhe", "perfeito", "robusto", "testado"],
        "autonomia": ["autonomia", "independente", "controle", "decisão"],
        "custo": ["custo", "barato", "economia", "gratuito", "orçamento"],
    }
    t = texto.lower()
    for dominio, palavras in _DOMINIOS.items():
        if any(p in t for p in palavras):
            return dominio
    return "outro"


# ── PERSISTÊNCIA ─────────────────────────────────────────────────────────────

def _carregar() -> dict:
    if _cache["dados"] is not None:
        return _cache["dados"]
    if not os.path.exists(PRINCIPIOS_PATH):
        _cache["dados"] = {}
        return {}
    try:
        with open(PRINCIPIOS_PATH, "r", encoding="utf-8") as f:
            dados = json.load(f)
            _cache["dados"] = dados if isinstance(dados, dict) else {}
            return _cache["dados"]
    except Exception as e:
        warn("PRINCIPIOS", f"Erro ao carregar: {e}")
        _cache["dados"] = {}
        return {}


def _salvar(dados: dict):
    try:
        with open(PRINCIPIOS_PATH, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("PRINCIPIOS", f"Erro ao salvar: {e}")


# ── DETECÇÃO ─────────────────────────────────────────────────────────────────

def e_principio(texto: str) -> bool:
    """
    Retorna True se o texto contém declaração explícita de princípio.
    Mais restritivo que extração de crença — requer padrão forte.
    """
    if len(texto) < 10:
        return False
    t = " " + texto.lower() + " "
    return any((" " + p + " ") in t or t.startswith(" " + p) for p in _PADROES_PRINCIPIO)


def extrair_principio(texto: str) -> dict | None:
    """
    Extrai dados de um princípio detectado.
    Retorna None se não for princípio.
    """
    if not e_principio(texto):
        return None
    return {
        "texto":     texto[:400],
        "dominio":   _detectar_dominio(texto),
        "categoria": _detectar_categoria(texto),
    }


# ── REGISTRO ─────────────────────────────────────────────────────────────────

def registrar(texto: str, dominio: str = "", categoria: str = ""):
    """
    Registra um princípio explícito.
    Confiança inicial: 0.8 (mais alta que crença — declaração direta).
    """
    with _lock:
        dados = _carregar()
        pid = _gerar_id(texto)

        if pid in dados:
            entrada = dados[pid]
            entrada["contagem"] += 1
            entrada["confianca"] = min(0.98, entrada["confianca"] + 0.05)
            entrada["ultima_vez"] = datetime.now().isoformat()
            info("PRINCIPIOS", f"Princípio reforçado: '{texto[:50]}' | confiança={entrada['confianca']:.2f}")
        else:
            dados[pid] = {
                "id":        pid,
                "texto":     texto[:400],
                "dominio":   dominio or _detectar_dominio(texto),
                "categoria": categoria or _detectar_categoria(texto),
                "confianca": 0.8,
                "contagem":  1,
                "ativo":     True,
                "criado_em": datetime.now().isoformat(),
                "ultima_vez": datetime.now().isoformat(),
            }
            info("PRINCIPIOS", f"Princípio registrado: '{texto[:50]}' | cat={dados[pid]['categoria']}")

        _cache["dados"] = dados
        threading.Thread(target=_salvar, args=(dados,), daemon=True).start()


# ── CONSULTA ─────────────────────────────────────────────────────────────────

def listar_ativos(min_confianca: float = 0.75) -> list[dict]:
    """Retorna princípios operacionais com confiança suficiente."""
    dados = _carregar()
    return [
        p for p in dados.values()
        if p.get("ativo", True) and p.get("confianca", 0) >= min_confianca
    ]


def buscar_por_dominio(dominio: str, min_confianca: float = 0.75) -> list[dict]:
    return [p for p in listar_ativos(min_confianca) if p.get("dominio") == dominio]


def buscar_por_categoria(categoria: str, min_confianca: float = 0.75) -> list[dict]:
    return [p for p in listar_ativos(min_confianca) if p.get("categoria") == categoria]


def revisar(pid: str, motivo: str = ""):
    """Desativa um princípio — usuário o contradisse explicitamente."""
    with _lock:
        dados = _carregar()
        if pid in dados:
            dados[pid]["ativo"] = False
            dados[pid]["confianca"] = max(0.0, dados[pid]["confianca"] - 0.4)
            dados[pid]["ultima_vez"] = datetime.now().isoformat()
            info("PRINCIPIOS", f"Princípio revisado: {pid} | {motivo[:50]}")
            _cache["dados"] = dados
            threading.Thread(target=_salvar, args=(dados,), daemon=True).start()


# ── PONTO DE ENTRADA ─────────────────────────────────────────────────────────

def processar(texto: str):
    """
    Chamado pelo pipeline após cada interação.
    Detecta e registra princípios explícitos. Zero API.
    """
    p = extrair_principio(texto)
    if p:
        registrar(p["texto"], p["dominio"], p["categoria"])