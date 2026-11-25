"""PONTOS DE INTEGRACAO COM A IA (quem desenvolver a IA edita APENAS este arquivo).

Duas funcoes, mesmas assinaturas de antes:

1) prever(demanda) -> dict
   Entrada: {"produto", "origem", "destino", "peso_ton", "prazo", "frete"}
   Saida:   {"resultado": str, "detalhe": str, "frete_estimado": float (opcional)}

2) estimar_frete(demanda) -> float | None
   Chamada AUTOMATICAMENTE na importacao, so para demandas que chegaram SEM frete.
   Devolve a estimativa em R$ ou None quando NAO ha base real suficiente. O valor vai para a coluna
   `frete_estimado` e NUNCA sobrescreve o frete real informado. Se esta funcao falhar, a importacao
   continua normalmente (sem estimativa).

A logica esta em ia/frete.py: mediana do R$/t de demandas REAIS da mesma rota (minimo de casos).
O historico vem da tabela `demandas` (somente as que tem frete informado).
"""
import time

import pandas as pd

from ia import frete as _frete

_CACHE = {"t": 0.0, "h": None}
_COLS = ["produto", "origem", "destino", "peso_ton", "frete"]


def carregar_historico(max_idade_s=10):
    """Historico de fretes reais do banco, ja preparado (com cache curto para importacoes em lote)."""
    if _CACHE["h"] is None or time.time() - _CACHE["t"] > max_idade_s:
        from core.db import consultar
        rows = consultar("SELECT produto, origem, destino, peso_ton, frete FROM demandas "
                         "WHERE frete IS NOT NULL AND peso_ton > 0")
        df = pd.DataFrame(
            [{c: (float(r[c]) if c in ("peso_ton", "frete") and r[c] is not None else r[c])
              for c in _COLS} for r in rows], columns=_COLS)
        _CACHE.update(t=time.time(), h=_frete.preparar(df))
    return _CACHE["h"]


def prever(demanda: dict) -> dict:
    est = _frete.estimar(demanda, carregar_historico())
    if est is None:
        return {"resultado": "Sem base para estimar o frete", "detalhe": _frete.SEM_BASE}
    return {"resultado": f"Frete sugerido: R$ {est['valor']:,.2f}",
            "detalhe": _frete.explicar(est), "frete_estimado": est["valor"]}


def estimar_frete(demanda: dict):
    est = _frete.estimar(demanda, carregar_historico())
    return None if est is None else est["valor"]
