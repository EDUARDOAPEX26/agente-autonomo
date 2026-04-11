# core/nucleo_vivo/sovereign_will.py
# Sovereign Will v36.3 - Versão corrigida para usar memórias reais

from typing import Dict, Any
import time
import json
import os
from core.logger import info, warn, debug

class SovereignWill:
    def __init__(self):
        self.dor_acumulada = 0.52
        self.versao = "v36.3"
        self.stagnation_counter = 0
        self.last_mutation = time.time()
        self._carregar_memorias()
        info("SOVEREIGN_WILL", f"Sovereign Will {self.versao} inicializado - Memórias carregadas")

    def _carregar_memorias(self):
        """Carrega os principais livros de memória de forma segura"""
        self.memoria = {}
        arquivos = [
            "livro_raciocinio.json",
            "constituicao_viva.json",
            "pain_register.json",
            "livro_parlamento.json"
        ]
        
        for arquivo in arquivos:
            caminho = os.path.join("core", "..", arquivo)  # raiz do projeto
            if os.path.exists(caminho):
                try:
                    with open(caminho, "r", encoding="utf-8") as f:
                        self.memoria[arquivo] = json.load(f)
                    info("SOVEREIGN_WILL", f"Memória carregada: {arquivo}")
                except Exception as e:
                    warn("SOVEREIGN_WILL", f"Falha ao carregar {arquivo}: {e}")
            else:
                debug("SOVEREIGN_WILL", f"Arquivo não encontrado: {arquivo}")

    def registrar_dor(self, intensidade: float, motivo: str):
        self.dor_acumulada = min(1.0, self.dor_acumulada + intensidade)
        info("SOVEREIGN_WILL", f"DOR: +{intensidade:.2f} | TOTAL: {self.dor_acumulada:.2f} | MOTIVO: {motivo}")
        if self.dor_acumulada > 0.75:
            warn("SOVEREIGN_WILL", "TENSÃO CRÍTICA detectada")
        return "ESTAVEL"

    def processar(self, query: str) -> Dict[str, Any]:
        query_lower = query.lower()
        dor_gerada = 0.0
        motivo = ""

        # Detecção de conflitos
        if any(p in query_lower for p in ["fase 31", "fase 32", "polyphonic", "parliament", "facções"]):
            dor_gerada = 0.1
            motivo = "Consulta sobre histórico interno"

        status_ruptura = self.registrar_dor(dor_gerada, motivo) if dor_gerada > 0 else "ESTAVEL"

        decisao = {
            "decisao_final": "Aceito com prioridade v36",
            "versao_ativa": self.versao,
            "dor_acumulada": round(self.dor_acumulada, 2),
            "status_ruptura": status_ruptura,
            "motivo_dor": motivo if motivo else None,
            "memoria_carregada": len(self.memoria) > 0
        }

        # Recuperação natural
        self.dor_acumulada = max(0.1, self.dor_acumulada - 0.03)
        
        return decisao

# Instância global
sovereign_will = SovereignWill()