"""
Nucleo Vivo Bridge v38.6
- v38.3: SovereignWill singleton
- v38.5: melhorias seletivas do v38.4 (Gemini)
- v38.6: _resumo_identidade inclui status_atual do identidade_agente.json
         encoding corrigido
"""
import json
import os
from core.logger import info, warn

try:
    from .sovereign_will import SovereignWill, sovereign_will as _sw_global
except ImportError:
    try:
        from sovereign_will import SovereignWill, sovereign_will as _sw_global
    except Exception:
        SovereignWill = None
        _sw_global = None

_PALAVRAS_SELF = [
    "livro", "livros", "tematico", "tematicos", "bloco", "blocos",
    "resumo", "pipeline", "fase", "fases", "versao", "versão",
    "que voce tem", "você tem", "suas memorias", "sua memoria",
    "como voce funciona", "como você funciona", "seu sistema",
    "quais sao", "quais são", "constituicao", "constituição",
    "status", "estado", "operacional",
    "quem é você", "quem e voce", "quem sou eu",
    "eduardo", "criador",
]

_PALAVRAS_MENTORES = [
    "mentor", "mentores", "einstein", "feynman", "tesla", "turing",
    "darwin", "drucker", "jung", "curie", "da vinci", "von neumann",
    "estratégia", "estrategia", "raciocínio", "raciocinio",
    "diretriz", "diretrizes",
]

_STOP_WORDS = {
    "o", "a", "os", "as", "um", "uma", "de", "do", "da", "que",
    "se", "por", "para", "com", "como", "qual", "quais", "me",
    "te", "nos", "e", "ou", "em", "no", "na", "eu", "você", "voce",
}

MAX_ENTRADAS = 5
MAX_CHARS_ENTRADA = 200


def _score_relevancia(query: str, entrada: dict) -> float:
    palavras_q = {
        w.strip("?!.,;:")
        for w in query.lower().split()
        if len(w) >= 3 and w not in _STOP_WORDS
    }
    if not palavras_q:
        return 0.0
    texto = (entrada.get("pergunta", "") + " " + entrada.get("resposta", "")).lower()
    matches = sum(1 for w in palavras_q if w in texto)
    return matches / len(palavras_q)


class NucleoVivoBridge:
    def __init__(self):
        # singleton — não cria instância duplicada
        self.sovereign_will = _sw_global if _sw_global is not None else (SovereignWill() if SovereignWill else None)
        self.versao = "v38.6"

        # detecção de raiz robusta
        raiz_candidata = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if os.path.exists(os.path.join(raiz_candidata, "identidade_agente.json")):
            self.raiz = raiz_candidata
        else:
            self.raiz = os.path.abspath(os.path.join(raiz_candidata, ".."))

        info("NUCLEO_VIVO_BRIDGE", f"Bridge {self.versao} ativado | raiz_real={self.raiz}")

    def _carregar_json(self, nome_arquivo: str) -> dict:
        caminho = os.path.join(self.raiz, nome_arquivo)
        try:
            if not os.path.exists(caminho):
                warn("NUCLEO_VIVO_BRIDGE", f"Não encontrado: {caminho}")
                return {}
            with open(caminho, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            warn("NUCLEO_VIVO_BRIDGE", f"Erro lendo {nome_arquivo}: {e}")
            return {}

    def _entradas_relevantes(self, query: str, livro: dict, max_n: int = MAX_ENTRADAS) -> list:
        entradas = livro.get("entradas", [])
        if not entradas:
            return []
        scored = [(_score_relevancia(query, e), e) for e in entradas]
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [e for score, e in scored[:max_n] if score > 0.1]
        if not top:
            top = entradas[-3:]
        return top

    def _formatar_entradas(self, entradas: list) -> str:
        linhas = []
        for e in entradas:
            p = e.get("pergunta", "")[:MAX_CHARS_ENTRADA]
            r = e.get("resposta", "")[:MAX_CHARS_ENTRADA]
            linhas.append(f"P: {p}\nR: {r}")
        return "\n---\n".join(linhas)

    def _resumo_identidade(self, identidade: dict) -> str:
        versao = identidade.get("versao", "")
        linhas = [f"Versão: {versao}"]

        for item in identidade.get("essencia", [])[:4]:
            linhas.append(f"- {str(item)[:100]}")

        # v38.6 — inclui status_atual
        status = identidade.get("status_atual", {})
        if status:
            linhas.append("Status atual:")
            for k, v in status.items():
                linhas.append(f"  {k}: {v}")

        return "\n".join(linhas)

    def _detectar_topico(self, query: str) -> str:
        q = query.lower()
        if any(p in q for p in _PALAVRAS_MENTORES):
            return "mentores"
        if any(p in q for p in _PALAVRAS_SELF):
            return "self"
        return "self"

    def process_query(self, query: str, contexto=None):
        if contexto is None:
            contexto = {}

        topico = self._detectar_topico(query)

        if topico == "mentores":
            dados = self._carregar_json("livro_mentores.json")
            mentores = dados.get("mentores", [])
            lista = "\n".join(
                f"- {m['nome']}: {m.get('principio_mestre','')[:100]}"
                for m in mentores
            )
            instrucao = (
                f"[MENTORES DISPONÍVEIS]\n{lista}\n\n"
                f"Use esses mentores reais ao responder. NÃO invente outros."
            )
            info("NUCLEO_VIVO_BRIDGE", f"Mentores injetados: {len(mentores)} ({len(instrucao)} chars)")

        else:
            livro_geral = self._carregar_json("livro_geral.json")
            identidade = self._carregar_json("identidade_agente.json")
            entradas = self._entradas_relevantes(query, livro_geral)
            texto_entradas = self._formatar_entradas(entradas)
            texto_identidade = self._resumo_identidade(identidade)
            instrucao = (
                f"[MEMÓRIA DO SISTEMA — {len(entradas)} entradas relevantes]\n"
                f"{texto_entradas}\n\n"
                f"[IDENTIDADE]\n{texto_identidade}\n\n"
                f"Use esses dados para responder sobre o sistema. NÃO invente informações."
            )
            info("NUCLEO_VIVO_BRIDGE", f"Injeção seletiva: {len(entradas)} entradas ({len(instrucao)} chars)")

        return {
            "instrucao_memoria_forte": instrucao,
            "bridge_version": self.versao,
            "topico": topico,
            "raiz_detectada": self.raiz,
        }


# Instância global
nucleo_vivo_bridge = NucleoVivoBridge()