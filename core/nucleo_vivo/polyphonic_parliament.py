# core/nucleo_vivo/polyphonic_parliament.py
# Fase 35 — Pesos Dinâmicos das Facções
# FIX v5: conecta com parliament_integration passando query real
#          opiniões contextualizadas por query

from typing import Dict, Any
import json
import os
from datetime import datetime
from core.logger import info

class PolyphonicParliament:
    ARQUIVO_PESOS = "livro_pesos_facções.json"

    def __init__(self):
        self.facções = self._carregar_pesos()
        info("POLYPHONIC_PARLIAMENT", f"Fase 35 ativada - {len(self.facções)} facções")

    def _carregar_pesos(self) -> Dict:
        if os.path.exists(self.ARQUIVO_PESOS):
            try:
                with open(self.ARQUIVO_PESOS, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "Guardião":   {"peso": 0.22, "vitorias": 0, "ultima_vitoria": None},
            "Visionário": {"peso": 0.18, "vitorias": 0, "ultima_vitoria": None},
            "Herético":   {"peso": 0.15, "vitorias": 0, "ultima_vitoria": None},
            "Predador":   {"peso": 0.12, "vitorias": 0, "ultima_vitoria": None},
            "Coruja":     {"peso": 0.20, "vitorias": 0, "ultima_vitoria": None},
            "impulso":    {"peso": 0.08, "vitorias": 0, "ultima_vitoria": None},
            "continuidade": {"peso": 0.25, "vitorias": 0, "ultima_vitoria": None},
        }

    def salvar_pesos(self):
        try:
            with open(self.ARQUIVO_PESOS, "w", encoding="utf-8") as f:
                json.dump(self.facções, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _ajustar_pesos(self, query: str):
        q = query.lower()
        if any(w in q for w in ["mudar","trocar","novo","inovar","criar","arriscar","refatorar"]):
            self.facções["Visionário"]["peso"] += 0.06
            self.facções["Guardião"]["peso"]   -= 0.04
        elif any(w in q for w in ["risco","perigo","cuidado","seguro","estável","manter","preservar"]):
            self.facções["Guardião"]["peso"]  += 0.07
            self.facções["Herético"]["peso"]  -= 0.05
        elif any(w in q for w in ["decidir","escolher","decisão","opção","dilema"]):
            self.facções["Coruja"]["peso"]   += 0.05
            self.facções["Predador"]["peso"] += 0.03
        elif any(w in q for w in ["rápido","urgente","agora","prazo","imediato"]):
            self.facções["Predador"]["peso"]  += 0.06
            self.facções["Coruja"]["peso"]    -= 0.03
        # Normaliza para soma = 1.0
        total = sum(f["peso"] for f in self.facções.values())
        if total > 0:
            for f in self.facções.values():
                f["peso"] = round(f["peso"] / total, 4)

    def _gerar_opiniao(self, faccao: str, query: str) -> str:
        """FIX v5: opiniões contextualizadas — usam os primeiros 60 chars da query."""
        q_curta = query[:60].strip() if query else "esta questão"
        base = {
            "Guardião":   f"Sobre '{q_curta}': priorize estabilidade. Mudanças devem ser graduais e reversíveis.",
            "Visionário": f"Sobre '{q_curta}': há oportunidade aqui. Use isso para evoluir o sistema.",
            "Herético":   f"Sobre '{q_curta}': o padrão atual pode ser o problema. Considere romper com ele.",
            "Predador":   f"Sobre '{q_curta}': seja prático. Corte o que não gera resultado real agora.",
            "Coruja":     f"Sobre '{q_curta}': observe o quadro completo antes de agir. Consequências de longo prazo importam.",
        }
        return base.get(faccao, f"Sobre '{q_curta}': avaliar com cuidado.")

    def debate(self, query: str) -> Dict[str, Any]:
        """FIX v5: passa query real para parliament_integration após o debate."""
        self._ajustar_pesos(query)

        # FIX v5: opiniões contextualizadas com a query real
        opinioes = {
            f: self._gerar_opiniao(f, query)
            for f in ["Guardião", "Visionário", "Herético", "Predador", "Coruja"]
        }

        vencedor = max(self.facções, key=lambda f: self.facções[f]["peso"])
        regime = {
            "Guardião":   "cautela",
            "Visionário": "expansao",
            "Herético":   "ruptura",
            "Predador":   "eficiencia",
            "Coruja":     "equilibrio",
        }.get(vencedor, "equilibrio")

        self.facções[vencedor]["vitorias"] = self.facções[vencedor].get("vitorias", 0) + 1
        self.facções[vencedor]["ultima_vitoria"] = datetime.now().isoformat()
        self.salvar_pesos()

        resultado = {
            "opinioes":       opinioes,
            "vencedor_faccao": vencedor,
            "regime":         regime,
            "query":          query,  # FIX v5: query salva no resultado
            "pesos":          {f: round(self.facções[f]["peso"], 3) for f in self.facções},
        }

        # FIX v5: conecta com parliament_integration passando query real
        try:
            from core.nucleo_vivo.parliament_integration import parliament_integration
            parliament_integration.registrar_debate(resultado, query=query)
        except Exception:
            pass

        info("POLYPHONIC_PARLIAMENT",
             f"Debate concluído — Vencedor: {vencedor} | Regime: {regime} | "
             f"Query: {query[:40]}")

        return resultado

    def get_pesos(self) -> Dict:
        return {f: round(self.facções[f]["peso"], 3) for f in self.facções}


# Instância global
polyphonic_parliament = PolyphonicParliament()