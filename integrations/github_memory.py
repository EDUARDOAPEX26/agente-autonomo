"""
integrations/github_memory.py
Memória persistente via GitHub — Fase 41
FIX: LIVROS_PERSISTENTES expandido de 10 para 18 livros
FIX v2: Pendrive-primeiro — boot lê do pendrive, GitHub só como fallback
"""
import os
import json
import gzip
import base64
import requests
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from core.logger import info, warn, erro

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO  = "EDUARDOAPEX26/agente-autonomo"
GITHUB_DIR   = "memoria"
HEADERS      = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LIVROS_PERSISTENTES = [
    "identidade_agente.json",
    "constituicao_viva.json",
    "livro_principios.json",
    "livro_crencas.json",
    "livro_geral.json",
    "livro_memoria.json",
    "livro_mentores.json",
    "livro_legado.json",
    "livro_codigo.json",
    "livro_render.json",
    "livro_raciocinio.json",
    "livro_parlamento.json",
    "livro_friccao.json",
    "livro_dissonancia.json",
    "livro_debates_parliament.json",
    "livro_trajetoria.json",
    "livro_metamorfose_v3.json",
    "livro_experimentos.json",
    "memoria_chat.json",  # FIX: histórico de conversa — bridge lê daqui
]

_cache_sha = {}

# [LOG]: livros legados bloqueados — nunca restaurados mesmo se existirem no pendrive/GitHub
_LIVROS_BLOQUEADOS = {
    "livro_railway.json",  # Railway descontinuado — substituído por livro_render.json
}

# ─── LIVROS GRANDES — truncados na RAM, completos no pendrive ────────────────
_LIVROS_GRANDES = {
    "livro_raciocinio.json":         20,
    "livro_trajetoria.json":         10,
    "livro_debates_parliament.json": 10,
    "livro_friccao.json":            15,
    "livro_dissonancia.json":        10,
    "livro_metamorfose_v3.json":     5,
    "livro_experimentos.json":       10,
    "livro_geral.json":              10,
    "livro_mentores.json":           5,
    "livro_render.json":             5,
    "livro_codigo.json":             10,
    "memoria_chat.json":             20,  # FIX: últimas 20 conversas na RAM
}

# ─── PENDRIVE ─────────────────────────────────────────────────────────────────

def _pendrive_base() -> Path | None:
    """Retorna o caminho base do pendrive se disponível."""
    try:
        from core.forja_memory import _caminho_ativo
        base = _caminho_ativo()
        if base and Path(base).parent.exists():
            return Path(base)
    except Exception:
        pass
    return None


def _path_pendrive_livro(nome_arquivo: str) -> Path | None:
    """Retorna o path completo do livro no pendrive."""
    base = _pendrive_base()
    if not base:
        return None
    # Tenta versão comprimida primeiro
    path_gz = base / "livros_completos" / (nome_arquivo + ".gz")
    if path_gz.exists():
        return path_gz
    # Tenta versão normal
    path = base / "livros_completos" / nome_arquivo
    if path.exists():
        return path
    return None


def _ler_do_pendrive(nome_arquivo: str):
    """Lê livro do pendrive. Retorna dados ou None."""
    path = _path_pendrive_livro(nome_arquivo)
    if not path:
        return None
    try:
        if path.suffix == ".gz":
            with gzip.open(str(path), "rb") as f:
                return json.loads(f.read().decode("utf-8"))
        else:
            with open(str(path), "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        warn("GITHUB_MEM", f"Erro ao ler pendrive {nome_arquivo}: {e}")
        return None


def _restaurar_do_pendrive(nome_arquivo: str, caminho_local: str) -> bool:
    """
    Tenta restaurar livro do pendrive para o disco local.
    Retorna True se conseguiu, False se deve ir ao GitHub.
    """
    dados = _ler_do_pendrive(nome_arquivo)
    if dados is None:
        return False

    # Trunca para RAM se for livro grande
    dados_ram = _truncar_livro(nome_arquivo, dados)
    conteudo_ram = json.dumps(dados_ram, ensure_ascii=False, indent=2)

    try:
        with open(caminho_local, "w", encoding="utf-8") as f:
            f.write(conteudo_ram)
        info("GITHUB_MEM", f"Restaurado do PENDRIVE: {nome_arquivo} ({len(conteudo_ram)} chars)")
        return True
    except Exception as e:
        erro("GITHUB_MEM", f"Erro ao salvar local {nome_arquivo}: {e}")
        return False


def _salvar_completo_pendrive(nome_arquivo: str, dados) -> bool:
    """Salva livro completo no pendrive comprimido."""
    try:
        base = _pendrive_base()
        if not base:
            warn("GITHUB_MEM", f"_salvar_completo_pendrive: pendrive não disponível — {nome_arquivo} não salvo")
            return False
        path = base / "livros_completos" / nome_arquivo
        path.parent.mkdir(parents=True, exist_ok=True)
        conteudo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        if len(conteudo) > 10000:
            path_gz = Path(str(path) + ".gz")
            with gzip.open(str(path_gz), "wb", compresslevel=6) as f:
                f.write(conteudo)
            info("GITHUB_MEM", f"_salvar_completo_pendrive: {nome_arquivo}.gz ({len(conteudo)} bytes)")
        else:
            with open(str(path), "w", encoding="utf-8") as f:
                f.write(conteudo.decode("utf-8"))
            info("GITHUB_MEM", f"_salvar_completo_pendrive: {nome_arquivo} ({len(conteudo)} bytes)")
        return True
    except Exception as e:
        erro("GITHUB_MEM", f"_salvar_completo_pendrive FALHOU {nome_arquivo}: {e}")
        return False


def _truncar_livro(nome_arquivo: str, dados):
    """Trunca livro grande para últimas N entradas — completo fica no pendrive."""
    if nome_arquivo not in _LIVROS_GRANDES:
        return dados
    n = _LIVROS_GRANDES[nome_arquivo]
    if isinstance(dados, list) and len(dados) > n:
        info("GITHUB_MEM", f"Truncando {nome_arquivo}: {len(dados)} -> {n} entradas")
        return dados[-n:]
    if isinstance(dados, dict):
        for chave, valor in dados.items():
            if isinstance(valor, list) and len(valor) > n:
                dados[chave] = valor[-n:]
    return dados


# ─── GITHUB ───────────────────────────────────────────────────────────────────

def _url(nome_arquivo: str) -> str:
    return f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_DIR}/{nome_arquivo}"


def _get_sha(nome_arquivo: str) -> str:
    if nome_arquivo in _cache_sha:
        return _cache_sha[nome_arquivo]
    try:
        r = requests.get(_url(nome_arquivo), headers=HEADERS, timeout=8)
        if r.status_code == 200:
            sha = r.json().get("sha", "")
            _cache_sha[nome_arquivo] = sha
            return sha
    except Exception:
        pass
    return ""


def publicar_livro(nome_arquivo: str) -> bool:
    if not GITHUB_TOKEN:
        warn("GITHUB_MEM", "Token não configurado")
        return False

    caminho = os.path.join(_RAIZ, nome_arquivo)
    if not os.path.exists(caminho):
        warn("GITHUB_MEM", f"Arquivo não encontrado: {nome_arquivo}")
        return False

    try:
        with open(caminho, "r", encoding="utf-8") as f:
            conteudo = f.read()
        conteudo_b64 = base64.b64encode(conteudo.encode("utf-8")).decode("utf-8")
        sha = _get_sha(nome_arquivo)
        payload = {"message": f"memoria: update {nome_arquivo}", "content": conteudo_b64}
        if sha:
            payload["sha"] = sha
        r = requests.put(_url(nome_arquivo), headers=HEADERS, json=payload, timeout=15)
        if r.status_code in (200, 201):
            _cache_sha[nome_arquivo] = r.json().get("content", {}).get("sha", sha)
            info("GITHUB_MEM", f"Publicado: {nome_arquivo}")
            return True
        else:
            erro("GITHUB_MEM", f"Erro ao publicar {nome_arquivo}: {r.status_code}")
            return False
    except Exception as e:
        erro("GITHUB_MEM", f"Exceção ao publicar {nome_arquivo}: {e}")
        return False


def carregar_livro(nome_arquivo: str) -> dict | list | None:
    if not GITHUB_TOKEN:
        return None
    try:
        r = requests.get(_url(nome_arquivo), headers=HEADERS, timeout=8)
        if r.status_code == 200:
            conteudo = base64.b64decode(r.json()["content"]).decode("utf-8")
            dados = json.loads(conteudo)
            _cache_sha[nome_arquivo] = r.json().get("sha", "")
            info("GITHUB_MEM", f"Carregado do GitHub: {nome_arquivo}")
            return dados
        warn("GITHUB_MEM", f"Não encontrado no GitHub: {nome_arquivo}")
        return None
    except Exception as e:
        erro("GITHUB_MEM", f"Erro ao carregar {nome_arquivo}: {e}")
        return None


def _sincronizar_crencas_forja() -> bool:
    """
    Copia crenças do ForjaMemory (pendrive) para livro_crencas.json na raiz.
    Garante que GitHub e pendrive tenham as crenças reais — não o arquivo vazio.
    """
    try:
        from core.forja_memory import _caminho_ativo, _ler_json
        from pathlib import Path
        base = Path(_caminho_ativo())
        crencas = _ler_json(base / "quente" / "crencas.json")
        if not crencas:
            return False
        caminho = os.path.join(_RAIZ, "livro_crencas.json")
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(crencas, f, ensure_ascii=False, indent=2)
        info("GITHUB_MEM", f"livro_crencas.json atualizado do ForjaMemory ({len(crencas)} crenças)")
        return True
    except Exception as e:
        warn("GITHUB_MEM", f"Erro ao sincronizar crenças ForjaMemory: {e}")
        return False


def sincronizar_todos() -> dict:
    """Publica todos os livros no GitHub E atualiza pendrive."""
    # [FIX]: sincroniza crenças do ForjaMemory antes de publicar
    _sincronizar_crencas_forja()
    resultado = {"ok": [], "erro": []}
    for livro in LIVROS_PERSISTENTES:
        if publicar_livro(livro):
            resultado["ok"].append(livro)
            # Atualiza pendrive com versão mais recente após publicar
            caminho = os.path.join(_RAIZ, livro)
            if os.path.exists(caminho):
                try:
                    with open(caminho, "r", encoding="utf-8") as f:
                        dados = json.load(f)
                    _salvar_completo_pendrive(livro, dados)
                except Exception as e:
                    warn("GITHUB_MEM", f"Erro ao salvar pendrive {livro}: {e}")
        else:
            resultado["erro"].append(livro)
    info("GITHUB_MEM", f"Sincronização: {len(resultado['ok'])} ok | {len(resultado['erro'])} erro")
    return resultado


def restaurar_todos() -> dict:
    """
    Restaura livros para o disco local.
    
    PRIORIDADE:
    1. Pendrive (local, instantâneo, zero API)
    2. GitHub (fallback, só se pendrive falhar)
    
    Livros grandes: salva completo no pendrive, trunca na RAM.
    """
    resultado = {"ok": [], "erro": [], "ignorado": [], "pendrive": [], "github": []}
    pendrive_disponivel = _pendrive_base() is not None

    if pendrive_disponivel:
        info("GITHUB_MEM", "Pendrive detectado — restaurando do pendrive primeiro")
    else:
        info("GITHUB_MEM", "Pendrive não disponível — restaurando do GitHub")

    for livro in LIVROS_PERSISTENTES:
        caminho = os.path.join(_RAIZ, livro)

        # ── BLOQUEADOS — nunca restaurar ────────────────────────────────────
        if livro in _LIVROS_BLOQUEADOS:
            resultado["ignorado"].append(livro)
            continue

        # ── PRIORIDADE 1: Pendrive ──────────────────────────────────────────
        if pendrive_disponivel and _restaurar_do_pendrive(livro, caminho):
            resultado["ok"].append(livro)
            resultado["pendrive"].append(livro)
            continue

        # ── PRIORIDADE 2: GitHub (fallback) ────────────────────────────────
        dados = carregar_livro(livro)
        if dados is None:
            resultado["erro"].append(livro)
            continue

        # Salva completo no pendrive para próximo boot
        if pendrive_disponivel and livro in _LIVROS_GRANDES:
            _salvar_completo_pendrive(livro, dados)

        # Trunca para RAM
        dados_ram = _truncar_livro(livro, dados)
        conteudo_ram = json.dumps(dados_ram, ensure_ascii=False, indent=2)

        try:
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(conteudo_ram)
            resultado["ok"].append(livro)
            resultado["github"].append(livro)
            info("GITHUB_MEM", f"Restaurado do GitHub: {livro} ({len(conteudo_ram)} chars)")
        except Exception as e:
            erro("GITHUB_MEM", f"Erro ao restaurar {livro}: {e}")
            resultado["erro"].append(livro)

    info("GITHUB_MEM", (
        f"Restauração: {len(resultado['ok'])} ok "
        f"| pendrive={len(resultado['pendrive'])} "
        f"| github={len(resultado['github'])} "
        f"| erro={len(resultado['erro'])}"
    ))
    return resultado


def publicar_livro_atualizado(nome_arquivo: str):
    publicar_livro(nome_arquivo)