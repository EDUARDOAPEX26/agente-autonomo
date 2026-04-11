"""
core/sovereign_will.py
Redirecionamento — evita instância duplicada.
O módulo real está em core/nucleo_vivo/sovereign_will.py
"""
from core.nucleo_vivo.sovereign_will import SovereignWill, sovereign_will

__all__ = ["SovereignWill", "sovereign_will"]