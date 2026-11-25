"""Testes do leitor de arquivos com IA (nao precisam de banco). Rode: python -m pytest"""
import json
from pathlib import Path

import pandas as pd
import pytest

from ia.leitor_arquivo import ler_demandas

REF = "2026-11-23"  # segunda-feira
DATA = Path(__file__).resolve().parent.parent / "data"


def ler(nome, conteudo):
    if isinstance(conteudo, str):
        conteudo = conteudo.encode("utf-8")
    return ler_demandas(nome, conteudo, REF, usar_spacy=False)


def test_csv_de_exemplo_do_projeto():
    df = ler("exemplo_demandas.csv", (DATA / "exemplo_demandas.csv").read_bytes())
    assert len(df) == 5
    assert list(df["produto"][:2]) == ["Soja", "Milho"]
    assert df.iloc[0]["peso_ton"] == 28 and df.iloc[0]["frete"] == 9800
    assert pd.isna(df.iloc[4]["destino"])  # a linha sem destino continua sem destino
    assert (df["leitura"] == "Tabela").all()


def test_ia_preenche_lacunas_a_partir_da_observacao():
    csv = ("Produto;Origem;Destino;Peso;Prazo;Valor;Observacao\n"
           "soja;Cascavel;Paranaguá;28 t;;;levar até sexta, uns 6 mil\n")
    r = ler("pedidos.csv", csv).iloc[0]
    assert str(r["prazo"]) == "2026-11-27"
    assert r["frete"] == 6000
    assert r["leitura"].startswith("Tabela + IA")
    assert "prazo" in r["leitura"] and "frete" in r["leitura"]


def test_ia_nao_inventa_o_que_esta_vazio():
    csv = "Produto;Origem;Destino;Peso;Prazo;Valor\nTrigo;Toledo;;32;01/12/2026;R$ 7.500,00\n"
    r = ler("pedidos.csv", csv).iloc[0]
    assert pd.isna(r["destino"])


def test_coluna_com_mensagens_livres():
    csv = "mensagem\n\"Preciso levar 20 t de milho de Toledo para Maringá até sexta, uns 6 mil\"\n"
    r = ler("whatsapp.csv", csv).iloc[0]
    assert (r["produto"], r["origem"], r["destino"], r["peso_ton"]) == ("Milho", "Toledo", "Maringá", 20)
    assert str(r["prazo"]) == "2026-11-27" and r["frete"] == 6000


def test_json_em_lista():
    dados = [{"produto": "Soja", "origem": "Cascavel", "destino": "Paranaguá", "peso": "28 t",
              "prazo": "25/11/2026", "valor": "R$ 9.800,00"}]
    r = ler("api.json", json.dumps(dados)).iloc[0]
    assert (r["produto"], r["peso_ton"], r["frete"]) == ("Soja", 28, 9800)


def test_txt_com_varias_demandas_e_ruido():
    txt = ("Pedidos da semana\n\n"
           "Preciso levar 28 toneladas de soja de Cascavel para Paranaguá até 25/11/2026\n\n"
           "Produto: Milho\nOrigem: Foz do Iguaçu\nDestino: Curitiba\nPeso: 30000 kg\nPrazo: 27/11/2026\n\n"
           "Att, Joao")
    df = ler("mensagens.txt", txt)
    assert len(df) == 2  # titulo e assinatura nao viram demanda
    assert list(df["produto"]) == ["Soja", "Milho"]
    assert df.iloc[1]["peso_ton"] == 30


def test_txt_com_uma_demanda_por_linha():
    txt = ("28 toneladas de soja de Cascavel para Paranaguá até 25/11/2026\n"
           "30 toneladas de milho de Toledo para Maringá até sexta\n")
    df = ler("lista.txt", txt)
    assert len(df) == 2
    assert str(df.iloc[1]["prazo"]) == "2026-11-27"


def test_excel():
    pytest.importorskip("openpyxl")
    import io
    buf = io.BytesIO()
    pd.DataFrame([{"Produto": "Soja", "Origem": "Cascavel", "Destino": "Paranaguá", "Peso": "28 t",
                   "Prazo": "25/11/2026", "Valor": "R$ 9.800,00"}]).to_excel(buf, index=False)
    r = ler("planilha.xlsx", buf.getvalue()).iloc[0]
    assert (r["produto"], r["peso_ton"], r["frete"]) == ("Soja", 28, 9800)


def test_formato_nao_suportado():
    with pytest.raises(ValueError):
        ler("foto.png", b"x")


def test_sugere_frete_so_quando_falta_e_nunca_preenche_o_frete_real():
    from ia import frete
    hist = frete.preparar(pd.DataFrame(
        [("Soja", "Cascavel", "Paranaguá", 20, 6000), ("Soja", "Cascavel", "Paranaguá", 25, 8000),
         ("Soja", "Cascavel", "Paranaguá", 30, 10200)],
        columns=["produto", "origem", "destino", "peso_ton", "frete"]))
    csv = ("Produto;Origem;Destino;Peso;Prazo;Valor\n"
           "soja;Cascavel;Paranaguá;10 t;25/11/2026;\n"        # sem frete, rota com historico
           "soja;Cascavel;Paranaguá;10 t;25/11/2026;R$ 4.000,00\n"  # frete real informado
           "milho;Toledo;Maringá;10 t;25/11/2026;\n")           # sem frete e sem historico
    df = ler_demandas("p.csv", csv.encode("utf-8"), REF, usar_spacy=False, historico=hist)
    assert pd.isna(df.iloc[0]["frete"]) and df.iloc[0]["frete_estimado"] == 3200.0
    assert df.iloc[1]["frete"] == 4000 and pd.isna(df.iloc[1]["frete_estimado"])
    assert pd.isna(df.iloc[2]["frete_estimado"]) and "Sem base" in df.iloc[2]["base_estimativa"]


def test_sem_historico_nao_sugere_nada():
    df = ler("p.csv", "Produto;Origem;Destino;Peso;Prazo;Valor\nsoja;Cascavel;Paranaguá;10 t;25/11/2026;\n")
    assert pd.isna(df.iloc[0]["frete_estimado"])
