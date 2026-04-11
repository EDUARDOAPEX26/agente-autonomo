# core/nucleo_vivo/parliament_memory.py
# Fase 34 - Memória persistente dos debates do Polyphonic Parliament

import json
import os
from datetime import datetime
from core.logger import info

class ParliamentMemory:
    ARQUIVO = "livro_debates_parliament.json"

    def __init__(self):
        self.debates = self._carregar()
        info("PARLIAMENT_MEMORY", f"Fase 34 carregada - {len(self.debates)} debates na memória")

    def _carregar(self):
        if os.path.exists(self.ARQUIVO):
            try:
                with open(self.ARQUIVO, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return []

    def salvar(self):
        with open(self.ARQUIVO, "w", encoding="utf-8") as f:
            json.dump(self.debates, f, indent=2, ensure_ascii=False)

    def registrar_debate(self, query: str, debate_result: dict):
        entrada = {
            "timestamp": datetime.now().isoformat(),
            "query": query[:200],
            "vencedor": debate_result.get("vencedor_faccao"),
            "regime": debate_result.get("regime"),
            "opinioes": debate_result.get("opinioes", {}),
            "faccoes_ativas": list(debate_result.get("opinioes", {}).keys())
        }
        self.debates.append(entrada)
        if len(self.debates) > 200:
            self.debates.pop(0)
        self.salvar()
        info("PARLIAMENT_MEMORY", f"Debate salvo na memória - Vencedor: {entrada['vencedor']}")

    def get_ultimos_debates(self, quantidade: int = 5):
        return self.debates[-quantidade:]

    def get_status(self):
        return {
            "total_debates": len(self.debates),
            "ultimo_debate": self.debates[-1] if self.debates else None
        }

# Instância global
parliament_memory = ParliamentMemory()