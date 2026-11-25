"""Estimativa de FRETE a partir do HISTORICO REAL de demandas - sem inventar valores.

Principio: a IA so sugere um frete quando existe base real para sustentar o numero. A sugestao
nunca substitui o frete informado (vai para a coluna propria `frete_estimado`).

Como calcula (tecnica: regressao simples por similaridade com casos anteriores):
  1. Do historico, calcula o frete por tonelada (R$/t) de cada demanda que tinha frete real.
  2. Procura casos da MESMA ROTA E MESMO PRODUTO; se nao houver casos suficientes, usa a MESMA ROTA.
  3. Estimativa = mediana do R$/t desses casos x peso da demanda nova. A faixa (minimo-maximo, ou
     quartis quando ha casos de sobra) mostra a incerteza.
  4. Menos de MIN_CASOS casos semelhantes  ->  NAO estima (devolve None).

Tambem tem `avaliar()`: validacao leave-one-out (estima cada frete real usando todos os outros) e
compara com uma linha de base simples (media geral de R$/t x peso).
"""
import pandas as pd

from ia.extrator import _norm

MIN_CASOS = 3
COLUNAS = ["produto", "origem", "destino", "peso_ton", "frete"]


def _chave(v):
    return _norm(v).strip() if isinstance(v, str) else ""


def _num(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return None if n != n else n  # NaN -> None


def preparar(historico):
    """DataFrame (produto, origem, destino, peso_ton, frete) -> so os casos validos, com R$/t."""
    if historico is None or len(historico) == 0:
        return pd.DataFrame(columns=COLUNAS + ["rpt", "k_produto", "k_origem", "k_destino"])
    h = historico[COLUNAS].copy()
    h["peso_ton"] = pd.to_numeric(h["peso_ton"], errors="coerce")
    h["frete"] = pd.to_numeric(h["frete"], errors="coerce")
    h = h[(h["peso_ton"] > 0) & (h["frete"] > 0)].dropna(subset=["origem", "destino"])
    h["rpt"] = h["frete"] / h["peso_ton"]
    for c in ("produto", "origem", "destino"):
        h["k_" + c] = h[c].map(_chave)
    return h.reset_index(drop=True)


def _resultado(sub, peso, base):
    rpt = sub["rpt"]
    n = len(sub)
    med = float(rpt.median())
    lo, hi = (float(rpt.quantile(0.25)), float(rpt.quantile(0.75))) if n >= 4 else \
             (float(rpt.min()), float(rpt.max()))
    aviso = None
    pmin, pmax = float(sub["peso_ton"].min()), float(sub["peso_ton"].max())
    if peso < pmin * 0.5 or peso > pmax * 1.5:
        aviso = f"peso fora do que essa rota já transportou ({pmin:g} a {pmax:g} t)"
    return {
        "valor": round(med * peso, 2), "minimo": round(lo * peso, 2), "maximo": round(hi * peso, 2),
        "n_casos": n, "base": base, "rpt_mediano": round(med, 2), "aviso": aviso,
    }


def estimar(demanda, historico_preparado, min_casos=MIN_CASOS):
    """-> dict com valor/minimo/maximo/n_casos/base/aviso, ou None quando NAO ha base suficiente."""
    h = historico_preparado
    peso = _num(demanda.get("peso_ton"))
    origem, destino = _chave(demanda.get("origem")), _chave(demanda.get("destino"))
    if h is None or h.empty or not origem or not destino or not peso or peso <= 0:
        return None
    rota = h[(h["k_origem"] == origem) & (h["k_destino"] == destino)]
    produto = _chave(demanda.get("produto"))
    if produto:
        mesmo = rota[rota["k_produto"] == produto]
        if len(mesmo) >= min_casos:
            return _resultado(mesmo, peso, "mesma rota e mesmo produto")
    if len(rota) >= min_casos:
        return _resultado(rota, peso, "mesma rota")
    return None


def explicar(r):
    """Texto curto para mostrar na tela."""
    f = lambda v: "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")  # noqa: E731
    txt = (f"{f(r['valor'])} (faixa {f(r['minimo'])} a {f(r['maximo'])}), baseado em "
           f"{r['n_casos']} demanda(s) reais da {r['base']}, ~{f(r['rpt_mediano'])}/t")
    return txt + (f". Atenção: {r['aviso']}" if r["aviso"] else "")


SEM_BASE = "Sem base suficiente: não há demandas reais parecidas o bastante, então a IA não estima."


# ---------------------------------------------------------------------------------------------
# Avaliacao (leave-one-out)
# ---------------------------------------------------------------------------------------------
def avaliar(historico, min_casos=MIN_CASOS):
    """Estima cada frete real usando TODOS os outros casos e mede o erro.
    Compara com a linha de base: media geral de R$/t x peso (estima sempre, sem criterio)."""
    h = preparar(historico)
    n = len(h)
    e_ia, p_ia, e_bs, p_bs, e_bt, p_bt = [], [], [], [], [], []
    niveis = {}
    for i in range(n):
        linha = h.iloc[i]
        resto = h.drop(index=i)
        real, peso = float(linha["frete"]), float(linha["peso_ton"])
        base = float(resto["rpt"].mean()) * peso if len(resto) else None
        if base is not None:
            e_bt.append(abs(base - real))
            p_bt.append(abs(base - real) / real)
        est = estimar({"produto": linha["produto"], "origem": linha["origem"],
                       "destino": linha["destino"], "peso_ton": peso}, resto, min_casos)
        if est:
            e_ia.append(abs(est["valor"] - real))
            p_ia.append(abs(est["valor"] - real) / real)
            niveis[est["base"]] = niveis.get(est["base"], 0) + 1
            if base is not None:
                e_bs.append(abs(base - real))
                p_bs.append(abs(base - real) / real)

    def media(x):
        return sum(x) / len(x) if x else None
    return {
        "n": n, "n_estimados": len(e_ia), "cobertura": (len(e_ia) / n) if n else 0.0,
        "mae_ia": media(e_ia), "mape_ia": media(p_ia),
        "mae_base_mesmos": media(e_bs), "mape_base_mesmos": media(p_bs),
        "mae_base_todos": media(e_bt), "mape_base_todos": media(p_bt),
        "niveis": niveis, "min_casos": min_casos,
    }
