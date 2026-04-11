# core/nucleo_vivo/parliament_integration.py
# Fase 34 - Integração com memória persistente dos debates
# FIX v5: query real passada ao debate, get_prompt_influence comprimido

import json
from datetime import datetime
from core.logger import info
from core.nucleo_vivo.parliament_memory import parliament_memory


class ParliamentIntegration:
    def __init__(self):
        self.ultimo_debate  = None
        self.ultimo_vencedor = None
        self.ultimo_regime  = None
        self._ultima_query  = ""
        info("PARLIAMENT_INTEGRATION", "Fase 34 ativada - Memória persistente dos debates")

    def registrar_debate(self, debate_result: dict, query: str = ""):
        """FIX v5: recebe query real — elimina 'query_desconhecida'."""
        self.ultimo_debate   = debate_result
        self.ultimo_vencedor = debate_result.get("vencedor_faccao")
        self.ultimo_regime   = debate_result.get("regime")
        self._ultima_query   = query or ""
        try:
            # FIX v5: passa query real em vez de placeholder
            parliament_memory.registrar_debate(
                self._ultima_query or "sem_query",
                debate_result
            )
        except Exception:
            pass
        info(
            "PARLIAMENT_INTEGRATION",
            f"Debate registrado — Vencedor: {self.ultimo_vencedor} | "
            f"Regime: {self.ultimo_regime} | Query: {self._ultima_query[:40]}"
        )

    def get_prompt_influence(self) -> str:
        """FIX v5: comprimido de ~500 chars para ~60 chars — economiza tokens."""
        if not self.ultimo_debate:
            return ""
        return (
            f"[PARLAMENTO: {self.ultimo_vencedor or 'equilibrio'} | "
            f"regime={self.ultimo_regime or 'cautela'}]"
        )

    def foi_ativado_ultima_vez(self) -> bool:
        return self.ultimo_debate is not None


# Instância global
parliament_integration = ParliamentIntegration()