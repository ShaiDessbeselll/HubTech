"""Leitura de ARQUIVOS (Excel, CSV, JSON, PDF, TXT) com apoio da IA de PLN.

Cada arquivo vira uma lista de demandas (uma por linha/bloco). Como a IA entra:
  * Arquivo em TABELA (Excel, CSV, JSON, PDF com tabela): as colunas conhecidas (produto, origem,
    destino, peso, prazo, frete e seus apelidos) sao lidas pelas regras do importador. Quando uma
    celula essencial esta vazia, o extrator de PLN (ia/extrator.py) le o RESTO DA LINHA (por exemplo
    uma coluna de observacao: "levar ate sexta, uns 6 mil") e preenche a lacuna.
  * Arquivo de TEXTO (TXT, PDF sem tabela, coluna com mensagens): o extrator de PLN le cada bloco
    de texto e extrai os campos.

Frete: quando uma demanda NAO tem frete, a IA pode SUGERIR um valor com base no historico real
(ia/frete.py), em colunas separadas (`frete_estimado`, `base_estimativa`). O frete real nunca e
preenchido pela estimativa e, sem base suficiente, a IA nao estima.

O resultado traz colunas de transparencia: `leitura` (de onde veio cada dado) e `trecho`
(o pedaco do arquivo que originou a demanda), para a pessoa conferir antes de salvar.
"""
import io
import re

import pandas as pd

from core import importador as im
from ia import extrator
from ia import frete as frete_ia

CAMPOS = extrator.CAMPOS
SAIDA = CAMPOS + ["frete_estimado", "base_estimativa", "leitura", "trecho"]
_ESSENCIAIS = ("produto", "origem", "destino", "peso_ton")


def _vazio(v):
    if v is None:
        return True
    if not isinstance(v, str):
        try:
            return bool(pd.isna(v))
        except (TypeError, ValueError):
            return False
    return v.strip().lower() in ("", "nan", "none", "nat")


def _como_tipo(campo, v):
    if v is None:
        return None
    if campo == "prazo" and isinstance(v, str):
        return pd.to_datetime(v).date()
    if campo in ("peso_ton", "frete"):
        return float(v)
    return v


def _resumo(valores, limite=90):
    return " ; ".join(str(v) for v in valores if not _vazio(v))[:limite]


# ---------- arquivos em tabela ----------
def _tabela(df_raw, data_ref, usar_spacy):
    padrao = im.padronizar(df_raw)  # mesmas linhas, mesma ordem
    linhas = []
    for (_, raw), (_, p) in zip(df_raw.iterrows(), padrao.iterrows()):
        valores = {c: (None if _vazio(p[c]) else p[c]) for c in CAMPOS}
        faltam = [c for c in CAMPOS if valores[c] is None]
        preenchidos = []
        if faltam:
            texto = "\n".join(f"{k}: {v}" for k, v in raw.items() if not _vazio(v))
            if texto:
                ia = extrator.extrair(texto, data_ref, usar_spacy)
                for c in faltam:
                    if ia[c] is not None:
                        valores[c] = _como_tipo(c, ia[c])
                        preenchidos.append(c)
        linha = {c: _como_tipo(c, valores[c]) for c in CAMPOS}
        linha["leitura"] = ("Tabela + IA (" + ", ".join(preenchidos) + ")") if preenchidos else "Tabela"
        linha["trecho"] = _resumo(raw.values)
        linhas.append(linha)
    return pd.DataFrame(linhas, columns=SAIDA)


# ---------- arquivos de texto ----------
def _blocos(texto):
    """Separa o texto em demandas: blocos separados por linha em branco; se um bloco tiver
    varias linhas com peso, cada linha vira uma demanda."""
    saida = []
    for b in (b.strip() for b in re.split(r"\n\s*\n", texto)):
        if not b:
            continue
        linhas = [x for x in b.splitlines() if x.strip()]
        com_peso = [x for x in linhas if extrator._peso(extrator._norm(x))[0] is not None]
        saida += com_peso if len(com_peso) >= 2 else [b]
    return saida


def _texto(texto, data_ref, usar_spacy):
    linhas = []
    for b in _blocos(texto):
        ia = extrator.extrair(b, data_ref, usar_spacy)
        if sum(ia[c] is not None for c in _ESSENCIAIS) < 2:  # ruido (titulo, rodape, etc.)
            continue
        linha = {c: _como_tipo(c, ia[c]) for c in CAMPOS}
        linha["leitura"] = "IA (texto)"
        linha["trecho"] = " ".join(b.split())[:90]
        linhas.append(linha)
    return pd.DataFrame(linhas, columns=SAIDA)


def _pdf(conteudo):
    """-> (DataFrame com as tabelas do PDF ou None, texto corrido do PDF)"""
    import pdfplumber
    linhas, texto = [], ""
    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        for pag in pdf.pages:
            for tabela in pag.extract_tables():
                if tabela and len(tabela) > 1:
                    cab = [str(c or "").strip() for c in tabela[0]]
                    linhas += [dict(zip(cab, row)) for row in tabela[1:]]
            texto += (pag.extract_text() or "") + "\n"
    return (pd.DataFrame(linhas).astype(str) if linhas else None), texto


def _com_estimativa(df, historico):
    """Para as demandas SEM frete, sugere um valor (colunas separadas) se houver base real."""
    if df.empty:
        return df
    est, base = [], []
    for _, r in df.iterrows():
        if not _vazio(r["frete"]):
            est.append(None)
            base.append(None)
            continue
        e = frete_ia.estimar({c: r[c] for c in CAMPOS}, historico) if historico is not None else None
        est.append(e["valor"] if e else None)
        base.append(frete_ia.explicar(e) if e else frete_ia.SEM_BASE)
    df = df.copy()
    df["frete_estimado"] = est
    df["base_estimativa"] = base
    return df


# ---------- funcao principal ----------
def ler_demandas(nome, conteudo, data_ref=None, usar_spacy=True, historico=None):
    """Le um arquivo e devolve um DataFrame com uma demanda por linha
    (colunas: produto, origem, destino, peso_ton, prazo, frete, frete_estimado, base_estimativa,
    leitura, trecho). `historico` = fretes reais ja preparados (ia.frete.preparar); sem ele, nao
    ha sugestao de frete."""
    ext = nome.lower().rsplit(".", 1)[-1]
    if ext in ("xlsx", "xls", "csv", "json"):
        df = _tabela(im.ler_arquivo(nome, conteudo), data_ref, usar_spacy)
    elif ext == "txt":
        df = _texto(conteudo.decode("utf-8-sig", errors="replace"), data_ref, usar_spacy)
    elif ext == "pdf":
        tabela, texto = _pdf(conteudo)
        df = _tabela(tabela, data_ref, usar_spacy) if tabela is not None else \
            _texto(texto, data_ref, usar_spacy)
    else:
        raise ValueError(f"Formato não suportado: .{ext}")
    return _com_estimativa(df, historico)
