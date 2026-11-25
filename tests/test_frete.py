"""Testes da estimativa de frete (nao precisam de banco). Rode: python -m pytest

ATENCAO: os dados abaixo sao SINTETICOS e servem so para testar o codigo; nao representam a Rodomax.
"""
import pandas as pd
import pytest

from ia import frete


def hist(casos):
    return frete.preparar(pd.DataFrame(casos, columns=["produto", "origem", "destino", "peso_ton", "frete"]))


# soja Cascavel -> Paranaguá a R$ 300, 320 e 340 por tonelada
H = hist([("Soja", "Cascavel", "Paranaguá", 20, 6000), ("Soja", "Cascavel", "Paranaguá", 25, 8000),
          ("Soja", "Cascavel", "Paranaguá", 30, 10200), ("Milho", "Toledo", "Maringá", 30, 5000)])


def test_estima_pela_mediana_do_valor_por_tonelada():
    r = frete.estimar({"produto": "soja", "origem": "cascavel", "destino": "paranagua", "peso_ton": 10}, H)
    assert r["valor"] == 3200.0  # mediana 320 R$/t x 10 t
    assert r["n_casos"] == 3 and r["base"] == "mesma rota e mesmo produto"
    assert r["minimo"] == 3000.0 and r["maximo"] == 3400.0


def test_nao_inventa_sem_base_suficiente():
    # rota Toledo -> Maringá tem so 1 caso: a IA se recusa a estimar
    assert frete.estimar({"produto": "Milho", "origem": "Toledo", "destino": "Maringá", "peso_ton": 30}, H) is None
    # rota que nunca apareceu
    assert frete.estimar({"produto": "Soja", "origem": "Londrina", "destino": "Curitiba", "peso_ton": 20}, H) is None


def test_usa_a_rota_quando_o_produto_e_novo():
    r = frete.estimar({"produto": "Trigo", "origem": "Cascavel", "destino": "Paranaguá", "peso_ton": 10}, H)
    assert r["base"] == "mesma rota" and r["valor"] == 3200.0


def test_sem_peso_ou_sem_cidade_nao_estima():
    assert frete.estimar({"produto": "Soja", "origem": "Cascavel", "destino": "Paranaguá", "peso_ton": None}, H) is None
    assert frete.estimar({"produto": "Soja", "origem": None, "destino": "Paranaguá", "peso_ton": 10}, H) is None
    assert frete.estimar({"origem": "Cascavel", "destino": "Paranaguá", "peso_ton": 0}, H) is None


def test_historico_vazio():
    assert frete.estimar({"origem": "A", "destino": "B", "peso_ton": 10}, frete.preparar(None)) is None


def test_avisa_quando_o_peso_foge_do_historico():
    r = frete.estimar({"produto": "Soja", "origem": "Cascavel", "destino": "Paranaguá", "peso_ton": 60}, H)
    assert r["aviso"] and "20 a 30 t" in r["aviso"]


def test_min_casos_configuravel():
    assert frete.estimar({"produto": "Milho", "origem": "Toledo", "destino": "Maringá", "peso_ton": 30},
                         H, min_casos=1)["valor"] == 5000.0


def test_avaliacao_leave_one_out():
    r = frete.avaliar(pd.DataFrame(
        [("Soja", "Cascavel", "Paranaguá", 20, 6000), ("Soja", "Cascavel", "Paranaguá", 25, 7500),
         ("Soja", "Cascavel", "Paranaguá", 30, 9000), ("Soja", "Cascavel", "Paranaguá", 10, 3000),
         ("Milho", "Toledo", "Maringá", 30, 5000)],
        columns=["produto", "origem", "destino", "peso_ton", "frete"]))
    assert r["n"] == 5 and r["n_estimados"] == 4  # a unica de Toledo nao tem base
    assert r["mae_ia"] == pytest.approx(0.0)      # todas custam exatamente R$ 300/t
    assert r["mae_base_mesmos"] > r["mae_ia"]     # a linha de base erra mais


def test_explicar_mostra_a_base():
    r = frete.estimar({"produto": "Soja", "origem": "Cascavel", "destino": "Paranaguá", "peso_ton": 10}, H)
    txt = frete.explicar(r)
    assert "3 demanda(s) reais" in txt and "R$ 3.200,00" in txt


def test_modulo_estimar_frete_usa_o_historico(monkeypatch):
    import time

    from ia import modulo
    monkeypatch.setattr(modulo, "_CACHE", {"t": time.time() + 1000, "h": H})
    d = {"produto": "Soja", "origem": "Cascavel", "destino": "Paranaguá", "peso_ton": 10}
    assert modulo.estimar_frete(d) == 3200.0
    assert modulo.prever(d)["frete_estimado"] == 3200.0
    sem = {"produto": "Soja", "origem": "Londrina", "destino": "Curitiba", "peso_ton": 10}
    assert modulo.estimar_frete(sem) is None
    assert "frete_estimado" not in modulo.prever(sem)
