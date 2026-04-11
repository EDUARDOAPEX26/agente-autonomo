import os
from dotenv import load_dotenv
from exa_py import Exa
from core.logger import info, warn, erro

# Garante que .env está carregado antes de ler EXA_API_KEY
# Necessário porque o módulo pode ser importado antes do main.py chamar load_dotenv()
load_dotenv()


class ExaClient:
    def __init__(self):
        self.api_key = os.getenv("EXA_API_KEY")
        self.exa = Exa(api_key=self.api_key) if self.api_key else None
        if self.api_key:
            info("EXA", "Cliente Exa inicializado com sucesso")
        else:
            warn("EXA", "EXA_API_KEY não encontrada")

    def buscar(self, query: str, num_results: int = 8):
        if not self.exa:
            erro("EXA", "API key não configurada")
            return []
        try:
            result = self.exa.search_and_contents(
                query,
                num_results=num_results,
                summary=True,
                text=False,
                highlights=True
            )
            resultados = []
            for item in getattr(result, 'results', []):
                conteudo = getattr(item, 'summary', '') or getattr(item, 'highlight', '')
                conteudo = ' '.join(conteudo.split())
                resultados.append({
                    "title":  getattr(item, 'title', ''),
                    "url":    getattr(item, 'url', ''),
                    "text":   conteudo[:10000],
                    "fonte":  "exa"
                })
            info("EXA", f"✅ {len(resultados)} resultados para '{query[:60]}...'")
            return resultados
        except Exception as e:
            erro("EXA", f"Erro na busca: {str(e)[:100]}")
            return []

    def buscar_texto_simples(self, query: str, num_results: int = 5) -> str:
        resultados = self.buscar(query, num_results)
        if not resultados:
            return ""
        partes = [
            f"{r.get('title','')}\n{r.get('text','')[:900]}"
            for r in resultados if r.get('text', '').strip()
        ]
        return "\n\n---\n\n".join(partes)

    def buscar_multi(self, query: str, num_results: int = 3) -> list:
        """Retorna lista de dicts — usado pelo consensus_checker."""
        return self.buscar(query, num_results)


# Instância global — load_dotenv() já foi chamado acima
exa_client = ExaClient()


def exa_disponivel() -> bool:
    return bool(exa_client.api_key) and exa_client.exa is not None


def buscar_exa(query: str, num_results: int = 5) -> str:
    """Retorna string — usado por app.py, books.py, llm.py, pipeline.py."""
    return exa_client.buscar_texto_simples(query, num_results)


def buscar_exa_multi(query: str, num_results: int = 3) -> list:
    """Retorna lista de dicts — usado pelo consensus_checker para tri-source."""
    return exa_client.buscar_multi(query, num_results)


def testar_exa() -> bool:
    if not exa_disponivel():
        return False
    try:
        res = exa_client.buscar_texto_simples("teste", 1)
        return len(res) > 10
    except Exception:
        return False