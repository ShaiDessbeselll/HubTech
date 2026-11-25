"""Testes do leitor/padronizador (não precisam de banco). Rode: python -m pytest"""
from core import importador as im


def test_texto_livre():
    df = im.padronizar(im._ler_texto(
        "Preciso levar 28 toneladas de soja de Cascavel para Paranaguá até 25/11/2026, frete R$ 9.800,00"))
    r = df.iloc[0]
    assert (r["produto"], r["origem"], r["destino"]) == ("Soja", "Cascavel", "Paranaguá")
    assert r["peso_ton"] == 28.0 and r["frete"] == 9800.0
    assert str(r["prazo"]) == "2026-11-25"


def test_texto_com_campos_e_kg():
    df = im.padronizar(im._ler_texto(
        "Produto: Milho\nOrigem: Foz do Iguaçu\nDestino: Curitiba\nPeso: 30000 kg\nPrazo: 27/11/2026"))
    r = df.iloc[0]
    assert r["origem"] == "Foz do Iguaçu" and r["peso_ton"] == 30.0


def test_validacao():
    df = im.padronizar(im._ler_texto("Produto: Trigo\nOrigem: Toledo\nPeso: 32"))
    assert "ausentes" in im.validar(df.iloc[0])


def test_prazo_sem_ano_usa_ano_atual():
    from datetime import date
    df = im.padronizar(im._ler_texto("Levar 20 toneladas de milho de Toledo para Maringá até 30/11"))
    assert df.iloc[0]["prazo"].year in (date.today().year, date.today().year + 1)


def test_prazo_invalido_vira_vazio():
    df = im.padronizar(im._ler_texto("Produto: Trigo\nOrigem: Toledo\nDestino: Maringá\nPeso: 25\nPrazo: urgente"))
    assert df.iloc[0]["prazo"] is None


def test_frete_por_extenso():
    df = im.padronizar(im._ler_texto("Levar 20 toneladas de milho de Toledo para Maringá, frete 7 mil"))
    assert df.iloc[0]["frete"] == 7000.0
    df = im.padronizar(im._ler_texto("Produto: Trigo\nFrete: R$ 9,8 mil"))
    assert df.iloc[0]["frete"] == 9800.0


class _Cur:
    """Cursor falso: confere se cada SQL tem o mesmo número de %s e de parâmetros."""
    def __init__(self):
        self.sqls, self.lastrowid = [], 0

    def execute(self, sql, params=()):
        assert sql.count("%s") == len(params), sql
        self.sqls.append((sql, params))
        self.lastrowid += 1


class _Conn:
    def __init__(self):
        self.c = _Cur()

    def cursor(self):
        return self.c

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _rodar(frete, estimativa):
    import pandas as pd
    from unittest.mock import patch
    conn = _Conn()
    linha = {"produto": "Soja", "origem": "Cascavel", "destino": "Paranaguá", "peso_ton": "28",
             "prazo": "25/11/2026"}
    if frete:
        linha["frete"] = frete
    with patch.object(im, "get_conn", return_value=conn), patch.object(im, "registrar_log"), \
            patch.object(im, "estimar_frete", return_value=estimativa) as ia:
        res = im._processar(1, "x.csv", pd.DataFrame([linha]), "Planilha")
    return res, conn.c.sqls, ia


def test_frete_vazio_pede_estimativa_a_ia():
    res, sqls, ia = _rodar(None, 8123.456)
    assert res["ok"] == 1 and ia.called
    insert = [p for s, p in sqls if s.startswith("INSERT INTO demandas")][0]
    assert 8123.46 in insert and None in insert          # estimado gravado, frete real vazio
    assert any("IA sugeriu" in str(p) for s, p in sqls)


def test_frete_informado_nao_chama_a_ia():
    res, sqls, ia = _rodar("R$ 9.800,00", 7777.77)
    assert res["ok"] == 1 and not ia.called
    insert = [p for s, p in sqls if s.startswith("INSERT INTO demandas")][0]
    assert 9800.0 in insert and 7777.77 not in insert


def test_falha_da_ia_nao_derruba_a_importacao():
    import pandas as pd
    from unittest.mock import patch
    conn = _Conn()
    linha = {"produto": "Soja", "origem": "Cascavel", "destino": "Paranaguá", "peso_ton": "28"}
    with patch.object(im, "get_conn", return_value=conn), patch.object(im, "registrar_log"), \
            patch.object(im, "estimar_frete", side_effect=RuntimeError("modelo quebrou")):
        res = im._processar(1, "x.csv", pd.DataFrame([linha]), "Planilha")
    assert res["ok"] == 1
