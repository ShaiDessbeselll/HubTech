"""Testes do extrator de PLN (nao precisam de banco nem de spaCy). Rode: python -m pytest"""
from ia.extrator import extrair

REF = "2026-11-23"  # segunda-feira


def ex(texto):
    return extrair(texto, REF, usar_spacy=False)


def test_prazo_relativo_sexta_e_amanha():
    assert ex("28 toneladas de soja de Cascavel para Paranaguá até sexta")["prazo"] == "2026-11-27"
    assert ex("30 toneladas de milho de Toledo para Maringá pra amanhã")["prazo"] == "2026-11-24"


def test_prazo_semana_que_vem_e_fim_do_mes():
    assert ex("25 t de trigo de Cascavel para Ponta Grossa no começo da semana que vem")["prazo"] == "2026-11-30"
    assert ex("27 t de açúcar de Maringá para Santos até o fim do mês")["prazo"] == "2026-11-30"


def test_prazo_dia_n_e_em_n_dias():
    assert ex("32 t de fertilizante de Londrina para Curitiba até dia 28")["prazo"] == "2026-11-28"
    assert ex("22 t de arroz de Pelotas para Porto Alegre, entrega em 3 dias")["prazo"] == "2026-11-26"


def test_frete_informal():
    base = "28 toneladas de soja de Cascavel para Paranaguá até 25/11/2026"
    assert ex(base + ", uns 10 mil de frete")["frete"] == 10000
    assert ex(base + ", pago 6k")["frete"] == 6000
    assert ex(base + ", frete a combinar")["frete"] is None
    assert ex(base + " por R$ 8,5 mil")["frete"] == 8500


def test_peso_em_varias_formas():
    assert ex("Levar uns 30 mil quilos de milho de Toledo para Maringá")["peso_ton"] == 30
    assert ex("Levar 1,5 toneladas de sementes de Cascavel para Toledo")["peso_ton"] == 1.5
    assert ex("vinte toneladas de milho de Toledo para Cascavel")["peso_ton"] == 20
    assert ex("Peso: 12500 kg")["peso_ton"] == 12.5


def test_origem_e_destino_pelo_contexto():
    r = ex("Coleta em Cascavel, entrega em Paranaguá, 28 toneladas de soja")
    assert (r["origem"], r["destino"]) == ("Cascavel", "Paranaguá")
    r = ex("Soja 28t Cascavel > Paranaguá 25/11/2026 R$ 9.800")
    assert (r["origem"], r["destino"]) == ("Cascavel", "Paranaguá")
    r = ex("Tem carga saindo de Toledo com destino a Maringá")
    assert (r["origem"], r["destino"]) == ("Toledo", "Maringá")


def test_cidade_composta_e_minuscula():
    r = ex("28 toneladas de soja de Foz do Iguaçu para Curitiba")
    assert r["origem"] == "Foz do Iguaçu"
    r = ex("preciso levar 28 toneladas de soja de cascavel para paranagua ate 25/11/2026")
    assert (r["origem"], r["destino"]) == ("Cascavel", "Paranaguá")


def test_produto_composto_nao_vira_cidade():
    r = ex("Produto: Farelo de Soja\nOrigem: Cascavel\nDestino: Foz do Iguaçu\nPeso: 30 t")
    assert (r["produto"], r["origem"], r["destino"]) == ("Farelo de Soja", "Cascavel", "Foz do Iguaçu")
