"""Testes da regra de prioridade do CRM (não precisam de banco)."""
from datetime import date, timedelta

from core.crm import calcular_prioridade

HOJE = date(2026, 11, 22)


def test_prazo_curto_ou_vencido_e_alta():
    assert calcular_prioridade(HOJE + timedelta(days=2), HOJE) == "ALTA"
    assert calcular_prioridade(HOJE - timedelta(days=3), HOJE) == "ALTA"


def test_prazo_medio():
    assert calcular_prioridade(HOJE + timedelta(days=3), HOJE) == "MEDIA"
    assert calcular_prioridade(HOJE + timedelta(days=7), HOJE) == "MEDIA"


def test_prazo_longo_e_baixa():
    assert calcular_prioridade(HOJE + timedelta(days=8), HOJE) == "BAIXA"


def test_sem_prazo():
    assert calcular_prioridade(None, HOJE) == "MEDIA"


def test_funil_nao_deixa_pular_etapas():
    from core.crm import status_permitidos
    assert status_permitidos("NOVA") == ["NOVA", "EM_ANALISE", "CANCELADA"]
    assert "ENTREGUE" not in status_permitidos("NOVA")
    assert "NOVA" not in status_permitidos("ENTREGUE")
    assert status_permitidos("CANCELADA") == ["CANCELADA", "NOVA"]
