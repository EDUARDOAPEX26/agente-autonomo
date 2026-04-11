"""
integrations/github_memory.py
Memória persistente via GitHub — Fase 41
Publica livros temáticos no GitHub e carrega só o necessário por sessão.
Resolve a amnésia entre sessões sem gastar tokens com contexto desnecessário.
"""
import os
import json
import base64
import requests
from dotenv import load_dotenv
load_dotenv()
from core.logger import info, warn, erro

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO  = "EDUARDOAPEX26/agente-autonomo"
GITHUB_DIR   = "memoria"
HEADERS      = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Livros que participam da memória persistente
LIVROS_PERSISTENTES = [
    "livro_geral.json",
    "livro_mentores.json",
    "livro_crencas.json",
    "livro_principios.json",
    "livro_memoria.json",
    "livro_render.json",
    "livro_codigo.json",
    "livro_legado.json",
    "constituicao_viva.json",
    "identidade_agente.json",
]

_cache_sha = {}  # sha de cada arquivo para evitar re-upload desnecessário


def _url(nome_arquivo: str) -> str:
    return f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_DIR}/{nome_arquivo}"


def _get_sha(nome_arquivo: str) -> str:
    """Pega o SHA atual do arquivo no GitHub."""
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
    """Publica um livro local no GitHub."""
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

        payload = {
            "message": f"memoria: update {nome_arquivo}",
            "content": conteudo_b64,
        }
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
    """Carrega um livro do GitHub. Retorna o conteúdo ou None se falhar."""
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


def sincronizar_todos() -> dict:
    """Publica todos os livros persistentes no GitHub. Roda uma vez por sessão."""
    resultado = {"ok": [], "erro": []}
    for livro in LIVROS_PERSISTENTES:
        if publicar_livro(livro):
            resultado["ok"].append(livro)
        else:
            resultado["erro"].append(livro)
    info("GITHUB_MEM", f"Sincronização: {len(resultado['ok'])} ok | {len(resultado['erro'])} erro")
    return resultado


def restaurar_todos() -> dict:
    """
    Restaura livros do GitHub para o disco local.
    Usa quando o agente inicia e os arquivos locais estão vazios/desatualizados.
    """
    resultado = {"ok": [], "erro": [], "ignorado": []}
    for livro in LIVROS_PERSISTENTES:
        caminho = os.path.join(_RAIZ, livro)
        tamanho_local = os.path.getsize(caminho) if os.path.exists(caminho) else 0

        dados = carregar_livro(livro)
        if dados is None:
            resultado["erro"].append(livro)
            continue

        conteudo_remoto = json.dumps(dados, ensure_ascii=False, indent=2)

        # Sempre sobrescreve — GitHub é a fonte de verdade
        try:
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(conteudo_remoto)
            resultado["ok"].append(livro)
            info("GITHUB_MEM", f"Restaurado: {livro} ({len(conteudo_remoto)} chars)")
        except Exception as e:
            erro("GITHUB_MEM", f"Erro ao restaurar {livro}: {e}")
            resultado["erro"].append(livro)

    info("GITHUB_MEM", f"Restauração: {len(resultado['ok'])} restaurados | {len(resultado['ignorado'])} ignorados")
    return resultado


def publicar_livro_atualizado(nome_arquivo: str):
    """
    Chamado automaticamente após cada sessão quando um livro é modificado.
    Pode ser integrado no shutdown do main.py.
    """
    publicar_livro(nome_arquivo)