import json
import threading
from datetime import datetime

MEMORIA_FILE         = "memoria_chat.json"
SYNC_A_CADA          = 5
MAX_LIVROS           = 3
_memoria_global      = None
conversas_desde_sync = {"n": 0}

def get_memoria():
    return _memoria_global

def inicializar_memoria(carregar_github_fn):
    global _memoria_global
    dados = carregar_github_fn()
    if dados:
        try:
            with open(MEMORIA_FILE, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
        except: pass
        _memoria_global = dados
        return dados
    try:
        with open(MEMORIA_FILE, "r", encoding="utf-8") as f:
            conteudo = f.read().strip()
            _memoria_global = json.loads(conteudo) if conteudo and conteudo != "{}" else {"resumo": "", "aprendizados": [], "total_conversas": 0}
    except:
        _memoria_global = {"resumo": "", "aprendizados": [], "total_conversas": 0}
    return _memoria_global

def salvar_memoria(memoria, salvar_github_fn):
    global _memoria_global
    _memoria_global = memoria
    try:
        with open(MEMORIA_FILE, "w", encoding="utf-8") as f:
            json.dump(memoria, f, ensure_ascii=False, indent=2)
    except Exception as e:
        from core.logger import erro
        erro("MEMORY", f"Erro ao salvar local: {e}")
    conversas_desde_sync["n"] += 1
    if conversas_desde_sync["n"] >= SYNC_A_CADA:
        conversas_desde_sync["n"] = 0
        threading.Thread(target=salvar_github_fn, args=(memoria,), daemon=True).start()

def extrair_fatos(aprendizados):
    fatos = ["- O usuario se chama Eduardo Conceicao, mora em Atibaia-SP e e o criador deste agente."]
    for a in aprendizados:
        p = a.get("pergunta", a.get("tarefa", "")).lower()
        r = a.get("resposta", a.get("resultado", "")).lower()
        if any(x in p or x in r for x in ["sou ", "meu nome", "me chamo", "criei", "criador", "eduardo"]):
            texto = a.get("pergunta", p)
            if texto and texto not in [f.replace("- O usuario disse: '", "").rstrip("'") for f in fatos]:
                fatos.append(f"- O usuario disse: '{texto[:100]}'")
    return "\n".join(fatos)

# ── MULTI-LIVRO ───────────────────────────────────────────────────────────────

def detectar_assuntos(pergunta):
    from core.books import LIVROS
    p = pergunta.lower()
    encontrados = []
    for assunto, palavras in LIVROS.items():
        if any(w in p for w in palavras):
            encontrados.append(assunto)
        if len(encontrados) >= MAX_LIVROS:
            break
    return encontrados if encontrados else ["geral"]

def contexto_multi_livro(assuntos, pergunta_atual=""):
    from core.books import contexto_livro
    if not assuntos:
        return ""
    textos = []
    for assunto in assuntos[:MAX_LIVROS]:
        ctx = contexto_livro(assunto, pergunta_atual=pergunta_atual)
        if ctx:
            # Marca origem semantica de cada livro
            textos.append(f"[LIVRO: {assunto.upper()}]\n{ctx}")
    # Separa livros com divisor semantico claro
    return "\n\n---\n\n".join(textos)

# ── FASE 10: SUMÁRIO DE GOVERNANÇA ────────────────────────────────────────────

def sumario_governanca(assuntos: list) -> str:
    from core.books import carregar_livro
    linhas = []
    for assunto in assuntos[:MAX_LIVROS]:
        livro = carregar_livro(assunto)
        ambiguas   = [e for e in livro.get("entradas", []) if e.get("status") == "ambiguo"]
        promovidas = [e for e in livro.get("entradas", []) if e.get("status") == "promovido"]
        total_contradicoes = len(livro.get("contradicoes", []))
        if ambiguas or promovidas or total_contradicoes:
            linhas.append(f"\n[GOVERNANCA — {assunto.upper()}]")
            if promovidas:
                linhas.append(f"  Entradas protegidas (promovidas): {len(promovidas)}")
            if ambiguas:
                linhas.append(f"  Contradicoes pendentes de revisao: {len(ambiguas)}")
                for a in ambiguas[:3]:
                    linhas.append(f"    - '{a.get('pergunta','')[:80]}'")
            if total_contradicoes:
                linhas.append(f"  Total de contradicoes detectadas (historico): {total_contradicoes}")
    return "\n".join(linhas) if linhas else ""

def listar_contradicoes_pendentes(assunto: str) -> list:
    from core.books import carregar_livro
    livro = carregar_livro(assunto)
    return [e for e in livro.get("entradas", []) if e.get("status") == "ambiguo"]

def resolver_contradicao_manual(assunto: str, pergunta_parcial: str, manter: str) -> bool:
    from core.books import carregar_livro, salvar_livro_github
    from core.logger import info, warn
    livro    = carregar_livro(assunto)
    ambiguas = [e for e in livro["entradas"] if e.get("status") == "ambiguo"
                and pergunta_parcial.lower() in e.get("pergunta", "").lower()]
    if not ambiguas:
        warn("MEMORY", f"Nenhuma entrada ambigua encontrada para '{pergunta_parcial}' em '{assunto}'")
        return False
    ambiguas_ord     = sorted(ambiguas, key=lambda e: e.get("data", ""))
    entrada_anterior = ambiguas_ord[0]
    entrada_nova     = ambiguas_ord[-1]
    manter_entrada   = entrada_nova if manter == "nova" else entrada_anterior
    arquivar_entrada = entrada_anterior if manter == "nova" else entrada_nova
    for e in livro["entradas"]:
        if e.get("pergunta") == manter_entrada.get("pergunta") and e.get("data") == manter_entrada.get("data"):
            e["status"] = "normal"
        elif e.get("pergunta") == arquivar_entrada.get("pergunta") and e.get("data") == arquivar_entrada.get("data"):
            e["status"] = "arquivado"
    for c in livro.get("contradicoes", []):
        if pergunta_parcial.lower() in c.get("pergunta_comum", "").lower() and c.get("resolucao") == "ambiguo":
            c["resolucao"]      = f"manual_{manter}"
            c["data_resolucao"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            break
    from core.books import _cache_livros
    _cache_livros[assunto] = livro
    threading.Thread(target=salvar_livro_github, args=(livro,), daemon=True).start()
    info("MEMORY", f"Contradicao resolvida manualmente (manter='{manter}') em '{assunto}': '{pergunta_parcial[:60]}'")
    return True

# ── GATING LÓGICO ─────────────────────────────────────────────────────────────

def _tem_memoria_relevante(livros_ctx: str) -> bool:
    """True se o contexto dos livros tem conteudo real — nao so cabecalho vazio."""
    if not livros_ctx:
        return False
    return "[" in livros_ctx and ("|" in livros_ctx or "RESUMO" in livros_ctx or "ENTRADA" in livros_ctx)

# ── CONTEXTO GERAL ────────────────────────────────────────────────────────────

def contexto_memoria(memoria, assunto=None, pergunta_atual=""):
    from core.logger import info
    texto       = ""
    tem_memoria = False

    # Detecta assuntos relevantes
    if assunto:
        assuntos = detectar_assuntos(assunto) if len(assunto.split()) > 1 else [assunto]
    else:
        assuntos = []

    # ── BLOCO 1: FATOS DO USUARIO (sempre presente) ───────────────────────────
    if memoria["aprendizados"]:
        fatos = extrair_fatos(memoria["aprendizados"])
        if fatos:
            texto += f"[FONTE: FATOS_USUARIO]\n{fatos}\n\n"

    # ── BLOCO 2: MEMORIA DOS LIVROS (prioridade maxima) ───────────────────────
    if assuntos and assuntos != ["geral"]:
        if len(assuntos) > 1:
            info("LIVRO", f"Multi-livro: carregando {assuntos}")

        livros_ctx = contexto_multi_livro(assuntos, pergunta_atual=pergunta_atual)

        if livros_ctx:
            tem_memoria = _tem_memoria_relevante(livros_ctx)
            texto += (
                "[MEMORIA DOS LIVROS — PRIORIDADE MAXIMA]\n"
                f"{livros_ctx}\n\n"
            )

        gov = sumario_governanca(assuntos)
        if gov:
            texto += gov + "\n\n"

    elif assunto:
        from core.books import contexto_livro
        livro_ctx = contexto_livro(assunto, pergunta_atual=pergunta_atual)
        if livro_ctx:
            tem_memoria = _tem_memoria_relevante(livro_ctx)
            texto += (
                f"[MEMORIA DOS LIVROS — PRIORIDADE MAXIMA]\n"
                f"[LIVRO: {assunto.upper()}]\n"
                f"{livro_ctx}\n\n"
            )
        gov = sumario_governanca([assunto])
        if gov:
            texto += gov + "\n\n"

    # ── BLOCO 3: ULTIMAS CONVERSAS (apenas se nao ha memoria forte) ───────────
    # Nao injeta conversas recentes quando ha memoria de livro — evita poluicao
    if not tem_memoria and memoria["aprendizados"]:
        texto += "[FONTE: CONVERSAS_RECENTES]\nULTIMAS CONVERSAS GERAIS:\n"
        for a in memoria["aprendizados"][-5:]:
            pergunta = a.get("pergunta", a.get("tarefa", ""))
            resposta = a.get("resposta", a.get("resultado", ""))
            origem   = a.get("origem", "local")
            texto += f"[{a['data']}][{origem}] {pergunta[:100]} | {resposta[:100]}\n"

    # ── BLOCO 4: REGRA CRITICA — injetada NO TOPO quando ha memoria forte ─────
    if tem_memoria:
        regra = (
            "[MODO MEMORIA OBRIGATORIA ATIVO]\n"
            "REGRA CRITICA — PRIORIDADE MAXIMA:\n"
            "- Voce TEM dados reais nos livros acima em [MEMORIA DOS LIVROS].\n"
            "- Use SOMENTE esses dados para responder sobre este assunto.\n"
            "- E PROIBIDO usar conhecimento geral quando ha [MEMORIA DOS LIVROS] disponivel.\n"
            "- Se os dados forem insuficientes, use conhecimento geral ou dados externos recebidos no contexto\n\n"
        )
        texto = regra + texto

    return texto[-15000:], tem_memoria

# ── RESUMIR ───────────────────────────────────────────────────────────────────

def resumir_conversa(pergunta, resposta, memoria, assunto=None, classificacao=None):
    from core.books import atualizar_livro, detectar_assunto, registrar_licao
    from core.logger import info

    memoria["total_conversas"] += 1
    memoria["aprendizados"].append({
        "data":     datetime.now().strftime("%d/%m/%Y %H:%M"),
        "pergunta": pergunta[:200],
        "resposta": resposta[:200],
        "origem":   "conversa_local",
    })
    if len(memoria["aprendizados"]) > 20:
        memoria["aprendizados"] = memoria["aprendizados"][-20:]

    assunto_real = assunto or detectar_assunto(pergunta)
    relevancia   = classificacao.get("relevancia", "BAIXA") if classificacao else "BAIXA"
    tipo         = classificacao.get("tipo", "DESCARTAVEL") if classificacao else "DESCARTAVEL"

    if tipo == "LICAO":
        threading.Thread(
            target=registrar_licao,
            args=(pergunta, resposta),
            kwargs={"classificacao": classificacao},
            daemon=True
        ).start()
        info("MEMORY", "Tipo LICAO — enviado para livro_licoes")
        return memoria

    if relevancia in ("ALTA", "MEDIA"):
        threading.Thread(
            target=atualizar_livro,
            args=(assunto_real, pergunta, resposta),
            kwargs={"classificacao": classificacao},
            daemon=True
        ).start()
        info("MEMORY", f"Relevancia {relevancia} — salvo em livro '{assunto_real}' (com verificacao Fase 10)")
    else:
        info("MEMORY", "Relevancia BAIXA — descartado do livro")

    return memoria