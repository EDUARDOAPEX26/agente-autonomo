# ── CORE BOOKS — estavel + busca web com EXA ─────────────────────────────────
# Atualizado Fase 41-A: information_validator integrado

import json
import os
import threading
from datetime import datetime

from core.logger import info, warn, erro

# ── EXA + TAVILY ──────────────────────────────────────────────────────────────

try:
    from integrations.exa_client import buscar_exa
    EXA_OK = True
except ImportError:
    EXA_OK = False
    warn("LIVRO", "exa_client nao encontrado")

try:
    from integrations.tavily_client import buscar_online as tavily_buscar
    TAVILY_OK = True
except ImportError:
    TAVILY_OK = False

# ── CONFIG ────────────────────────────────────────────────────────────────────

LIVROS = {
    "codigo":  ["codigo", "python", "erro", "bug", "script"],
    "memoria": ["memoria", "salvar", "carregar", "json"],
    "railway": ["railway", "nuvem", "deploy", "cpu"],
}

_cache_livros  = {}
_sync_contador = {}

# ── DETECTAR ASSUNTO ──────────────────────────────────────────────────────────

PALAVRAS_VOLATEIS = [
    "preco", "preço", "cotacao", "cotação", "valor", "dolar", "dollar",
    "bitcoin", "ethereum", "cripto", "bolsa", "ibovespa", "selic",
    "temperatura", "clima", "tempo agora", "graus",
    "resultado", "placar", "jogo", "partida", "gol",
    "hoje", "agora", "neste momento",
]

EXCECOES_TECNICOS = [
    "erro ", "error ", "http ", "status ", "codigo ", "código ",
    "fase ", "versao ", "versão ", "loop ", "funcao ", "função ",
]


def _e_fato_volatil(pergunta: str, resposta: str) -> bool:
    texto = (pergunta + " " + resposta).lower()
    if any(e in texto for e in EXCECOES_TECNICOS):
        return False
    return any(p in texto for p in PALAVRAS_VOLATEIS)


def detectar_assunto(pergunta):
    p = pergunta.lower()
    for assunto, palavras in LIVROS.items():
        if any(w in p for w in palavras):
            return assunto
    return "geral"

# ── LIVRO BASE ────────────────────────────────────────────────────────────────

def _livro_vazio(assunto):
    return {
        "assunto": assunto,
        "entradas": [],
        "total_entradas": 0,
        "ultima_atualizacao": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }

# ── CARREGAR ──────────────────────────────────────────────────────────────────

def carregar_livro(assunto):
    if assunto in _cache_livros:
        return _cache_livros[assunto]
    caminho = f"livro_{assunto}.json"
    if os.path.exists(caminho):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                livro = json.load(f)
                _cache_livros[assunto] = livro
                return livro
        except Exception as e:
            erro("LIVRO", f"Erro ao carregar {assunto}: {e}")
    livro = _livro_vazio(assunto)
    _cache_livros[assunto] = livro
    return livro

# ── SALVAR ────────────────────────────────────────────────────────────────────

def salvar_livro_github(livro):
    try:
        caminho = f"livro_{livro['assunto']}.json"
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(livro, f, indent=2, ensure_ascii=False)
        info("LIVRO", f"{livro['assunto']} salvo localmente")
    except Exception as e:
        erro("LIVRO", f"Erro ao salvar: {e}")

# ── ATUALIZAR ─────────────────────────────────────────────────────────────────

def atualizar_livro(assunto, pergunta, resposta, classificacao=None):
    if _e_fato_volatil(pergunta, resposta):
        warn("LIVRO", f"Fato volátil — não salvo em '{assunto}': {pergunta[:60]}")
        return

    livro = carregar_livro(assunto)
    entrada = {
        "data":     datetime.now().strftime("%d/%m/%Y %H:%M"),
        "pergunta": pergunta[:200],
        "resposta": resposta[:200],
    }

    # Fase 41-A — enriquece entrada com tipo e TTL
    try:
        from core.information_validator import classificar_informacao, enriquecer_entrada_livro
        class_info = classificar_informacao(pergunta, resposta)
        entrada = enriquecer_entrada_livro(entrada, class_info)
    except Exception:
        pass
    # fim Fase 41-A

    livro["entradas"].append(entrada)
    livro["total_entradas"] += 1
    livro["ultima_atualizacao"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    _cache_livros[assunto] = livro
    threading.Thread(target=salvar_livro_github, args=(livro,), daemon=True).start()

# ── CONTEXTO DE LIVRO ─────────────────────────────────────────────────────────

def contexto_livro(assunto, pergunta_atual=""):
    livro = carregar_livro(assunto)
    if not livro["entradas"]:
        return ""

    # Fase 41-A — filtra entradas expiradas antes de injetar no contexto
    try:
        from core.information_validator import filtrar_entradas_expiradas
        entradas_validas = filtrar_entradas_expiradas(livro["entradas"])
    except Exception:
        entradas_validas = livro["entradas"]
    # fim Fase 41-A

    texto = f"\nMEMORIA ({assunto}):\n"
    for e in entradas_validas[-5:]:
        texto += f"{e['pergunta']} -> {e['resposta']}\n"
    return texto

# ── BUSCA WEB COM EXA (prioridade) + TAVILY (fallback) ───────────────────────

def buscar_na_web(pergunta: str, num_resultados: int = 6) -> list:
    if EXA_OK:
        try:
            resultado = buscar_exa(pergunta, num_results=num_resultados)
            if resultado:
                info("LIVRO", f"EXA retornou resultado para: {pergunta[:50]}")
                return [{"title": "", "url": "", "text": resultado, "fonte": "exa"}]
        except Exception as e:
            erro("LIVRO", f"EXA falhou: {e}")
    if TAVILY_OK:
        try:
            info("LIVRO", "Usando Tavily como fallback")
            res = tavily_buscar(pergunta)
            if res:
                return [{"title": "", "url": "", "text": res, "fonte": "tavily"}]
        except Exception as e:
            erro("LIVRO", f"Tavily falhou: {e}")
    return []


def contexto_busca_web(pergunta: str, max_chars: int = 8000) -> str:
    resultados = buscar_na_web(pergunta)
    if not resultados:
        return ""
    texto = "\n\nFONTES DA WEB:\n"
    total = 0
    for i, r in enumerate(resultados[:4]):
        conteudo = r.get("text", "")[:2000]
        trecho   = f"[{i+1}] {conteudo}\n\n"
        if total + len(trecho) > max_chars:
            break
        texto += trecho
        total += len(trecho)
    return texto.strip()

# ── COMPATIBILIDADE ───────────────────────────────────────────────────────────

def contexto_licoes(*args, **kwargs):
    return ""


_MENTORES_CACHE = {"dados": None, "mtime": None}
_MENTORES_PATH  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "livro_mentores.json")


def _carregar_mentores() -> dict:
    try:
        mtime = os.path.getmtime(_MENTORES_PATH)
        if _MENTORES_CACHE["dados"] is None or _MENTORES_CACHE["mtime"] != mtime:
            with open(_MENTORES_PATH, "r", encoding="utf-8") as f:
                _MENTORES_CACHE["dados"] = json.load(f)
            _MENTORES_CACHE["mtime"] = mtime
        return _MENTORES_CACHE["dados"]
    except Exception as e:
        warn("MENTORES", f"Nao foi possivel carregar livro_mentores.json: {e}")
        return {}


def contexto_mentores(tom: str = "TECNICO", pergunta: str = "") -> str:
    try:
        dados = _carregar_mentores()
        if not dados:
            return ""
        mentores_lista  = {m["id"]: m for m in dados.get("mentores", [])}
        mapeamento_tom  = dados.get("mapeamento_tom", {})
        ids_por_tom = mapeamento_tom.get(tom.upper(), mapeamento_tom.get("TECNICO", []))
        p = pergunta.lower()
        scores = {}
        for mid in ids_por_tom:
            m = mentores_lista.get(mid)
            if not m:
                continue
            score = 1
            for gatilho in m.get("gatilhos", []):
                if gatilho in p:
                    score += 2
            scores[mid] = score
        selecionados = sorted(scores, key=lambda x: scores[x], reverse=True)[:2]
        if not selecionados:
            return ""
        linhas = ["\nESTRATEGIAS DE RACIOCINIO ATIVAS (use como guia de pensamento, nao cite):"]
        for mid in selecionados:
            m = mentores_lista[mid]
            diretriz    = m.get("diretriz_raciocinio", "")
            metodologia = m.get("metodologia_chave", "")
            if diretriz:
                linhas.append(f"- {diretriz}")
            if metodologia:
                linhas.append(f"  metodo: {metodologia}")
        info("MENTORES", f"TOM={tom} | estrategias: {selecionados}")
        return "\n".join(linhas) + "\n"
    except Exception as e:
        erro("MENTORES", f"Erro em contexto_mentores: {e}")
        return ""


def registrar_licao(pergunta: str, resposta_errada: str, classificacao=None):
    try:
        warn("LICAO", f"Licao registrada (fallback): {pergunta[:60]}")
    except Exception:
        pass