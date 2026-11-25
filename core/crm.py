"""CRM das demandas: funil de status, prioridade, responsável e histórico."""
from datetime import date, datetime

from core.auth import registrar_log
from core.db import consultar, get_conn

STATUS = ["NOVA", "EM_ANALISE", "AGUARDANDO_MOTORISTA", "EM_TRANSPORTE", "ENTREGUE", "CANCELADA"]
STATUS_ROTULO = {
    "NOVA": "Nova",
    "EM_ANALISE": "Em análise",
    "AGUARDANDO_MOTORISTA": "Aguardando motorista",
    "EM_TRANSPORTE": "Em transporte",
    "ENTREGUE": "Entregue",
    "CANCELADA": "Cancelada",
}
STATUS_ABERTOS = ["NOVA", "EM_ANALISE", "AGUARDANDO_MOTORISTA", "EM_TRANSPORTE"]

# Regra do funil: de cada etapa só se pode ir para as etapas abaixo (sem pular etapas).
TRANSICOES = {
    "NOVA": ["EM_ANALISE", "CANCELADA"],
    "EM_ANALISE": ["NOVA", "AGUARDANDO_MOTORISTA", "CANCELADA"],
    "AGUARDANDO_MOTORISTA": ["EM_ANALISE", "EM_TRANSPORTE", "CANCELADA"],
    "EM_TRANSPORTE": ["AGUARDANDO_MOTORISTA", "ENTREGUE", "CANCELADA"],
    "ENTREGUE": ["EM_TRANSPORTE"],
    "CANCELADA": ["NOVA"],
}


def status_permitidos(atual):
    """Status atual + os que podem ser escolhidos a partir dele (o atual vem primeiro)."""
    return [atual] + TRANSICOES.get(atual, [])

PRIORIDADES = ["ALTA", "MEDIA", "BAIXA"]
PRIORIDADE_ROTULO = {"ALTA": "🔴 Alta", "MEDIA": "🟡 Média", "BAIXA": "🟢 Baixa"}

_SEM_MUDANCA = object()


def calcular_prioridade(prazo, hoje=None):
    """Regra automática: prazo em até 2 dias (ou vencido) = ALTA; até 7 dias = MEDIA; acima = BAIXA.
    Sem prazo informado = MEDIA."""
    if prazo is None:
        return "MEDIA"
    if isinstance(prazo, datetime):
        prazo = prazo.date()
    hoje = hoje or date.today()
    dias = (prazo - hoje).days
    if dias <= 2:
        return "ALTA"
    if dias <= 7:
        return "MEDIA"
    return "BAIXA"


def formatar_brl(v):
    """1234.5 -> '1.234,50'"""
    return f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def registrar_estimativa(demanda_id, valor, usuario_id):
    """Guarda a sugestão de frete da IA em coluna própria (NUNCA sobrescreve o frete real)."""
    valor = round(float(valor), 2)
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE demandas SET frete_estimado=%s WHERE id=%s", (valor, demanda_id))
        cur.execute("INSERT INTO demanda_historico (demanda_id, usuario_id, tipo, texto) "
                    "VALUES (%s,%s,'IA',%s)",
                    (demanda_id, usuario_id, f"IA sugeriu o frete em R$ {formatar_brl(valor)}"))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    registrar_log(usuario_id, "IA_FRETE_ESTIMADO", f"demanda={demanda_id} valor={valor}")


def listar_quadro(responsavel_id=None, prioridade=None, busca=None):
    sql = ("SELECT d.id, d.produto, d.origem, d.destino, d.peso_ton, d.prazo, d.frete, d.frete_estimado, d.status, "
           "d.prioridade, d.responsavel_id, u.nome AS responsavel, "
           "COALESCE((SELECT MAX(h.data_hora) FROM demanda_historico h WHERE h.demanda_id = d.id "
           "AND h.tipo IN ('CRIACAO','STATUS')), d.criado_em) AS etapa_desde "
           "FROM demandas d LEFT JOIN usuarios u ON u.id = d.responsavel_id WHERE 1=1 ")
    params = []
    if responsavel_id:
        sql += "AND d.responsavel_id = %s "
        params.append(responsavel_id)
    if prioridade:
        sql += "AND d.prioridade = %s "
        params.append(prioridade)
    if busca:
        sql += "AND (d.produto LIKE %s OR d.origem LIKE %s OR d.destino LIKE %s) "
        params += [f"%{busca}%"] * 3
    sql += ("ORDER BY FIELD(d.prioridade,'ALTA','MEDIA','BAIXA'), d.prazo IS NULL, d.prazo, d.id DESC "
            "LIMIT 600")
    return consultar(sql, params)


def resumo_funil():
    linhas = consultar("SELECT status, COUNT(*) AS n FROM demandas GROUP BY status")
    abertos = ",".join(f"'{s}'" for s in STATUS_ABERTOS)
    atrasadas = consultar(f"SELECT COUNT(*) AS n FROM demandas WHERE prazo < CURDATE() "
                          f"AND status IN ({abertos})")[0]["n"]
    return {"status": {r["status"]: int(r["n"]) for r in linhas}, "atrasadas": int(atrasadas)}


def obter(demanda_id):
    rows = consultar(
        "SELECT d.*, i.id AS importacao, i.nome_arquivo, i.origem AS fonte, i.data_hora AS importado_em, "
        "ui.nome AS importado_por, ur.nome AS responsavel "
        "FROM demandas d JOIN importacoes i ON i.id = d.importacao_id "
        "JOIN usuarios ui ON ui.id = i.usuario_id "
        "LEFT JOIN usuarios ur ON ur.id = d.responsavel_id WHERE d.id = %s", (demanda_id,))
    return rows[0] if rows else None


def historico(demanda_id):
    return consultar(
        "SELECT h.id, h.tipo, h.de_valor, h.para_valor, h.texto, h.data_hora, "
        "COALESCE(u.nome,'(sistema)') AS usuario FROM demanda_historico h "
        "LEFT JOIN usuarios u ON u.id = h.usuario_id WHERE h.demanda_id = %s ORDER BY h.id DESC",
        (demanda_id,))


def atualizar(demanda_id, usuario_id, status=None, prioridade=None,
              responsavel_id=_SEM_MUDANCA, nota=None):
    """Aplica mudanças em uma única transação e registra cada uma no histórico.
    Retorna quantas alterações foram feitas (nota conta como uma)."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    mudancas = []
    try:
        cur.execute(
            "SELECT d.status, d.prioridade, d.responsavel_id, u.nome AS resp FROM demandas d "
            "LEFT JOIN usuarios u ON u.id = d.responsavel_id WHERE d.id = %s FOR UPDATE", (demanda_id,))
        atual = cur.fetchone()
        if not atual:
            raise ValueError("Demanda não encontrada.")

        if status and status != atual["status"]:
            if status not in STATUS:
                raise ValueError("Status inválido.")
            if status not in TRANSICOES.get(atual["status"], STATUS):
                raise ValueError(f"não dá para ir de «{STATUS_ROTULO[atual['status']]}» direto para "
                                 f"«{STATUS_ROTULO[status]}». Siga as etapas do funil.")
            if status == "CANCELADA":
                if not (nota or "").strip():
                    raise ValueError("informe o motivo do cancelamento na anotação.")
                nota = "Motivo do cancelamento: " + nota.strip()
            cur.execute("UPDATE demandas SET status=%s WHERE id=%s", (status, demanda_id))
            mudancas.append(("STATUS", STATUS_ROTULO[atual["status"]], STATUS_ROTULO[status]))

        if prioridade and prioridade != atual["prioridade"]:
            if prioridade not in PRIORIDADES:
                raise ValueError("Prioridade inválida.")
            cur.execute("UPDATE demandas SET prioridade=%s WHERE id=%s", (prioridade, demanda_id))
            mudancas.append(("PRIORIDADE", PRIORIDADE_ROTULO[atual["prioridade"]],
                             PRIORIDADE_ROTULO[prioridade]))

        if responsavel_id is not _SEM_MUDANCA and responsavel_id != atual["responsavel_id"]:
            novo_nome = "(sem responsável)"
            if responsavel_id is not None:
                cur.execute("SELECT nome FROM usuarios WHERE id=%s", (responsavel_id,))
                linha = cur.fetchone()
                if not linha:
                    raise ValueError("Responsável não encontrado.")
                novo_nome = linha["nome"]
            cur.execute("UPDATE demandas SET responsavel_id=%s WHERE id=%s", (responsavel_id, demanda_id))
            mudancas.append(("RESPONSAVEL", atual["resp"] or "(sem responsável)", novo_nome))

        for tipo, de, para in mudancas:
            cur.execute(
                "INSERT INTO demanda_historico (demanda_id, usuario_id, tipo, de_valor, para_valor) "
                "VALUES (%s,%s,%s,%s,%s)", (demanda_id, usuario_id, tipo, de, para))

        nota = (nota or "").strip()
        if nota:
            cur.execute(
                "INSERT INTO demanda_historico (demanda_id, usuario_id, tipo, texto) "
                "VALUES (%s,%s,'NOTA',%s)", (demanda_id, usuario_id, nota))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    total = len(mudancas) + (1 if nota else 0)
    if total:
        resumo = "; ".join(f"{t}: {d} -> {p}" for t, d, p in mudancas) + ("; nota" if nota else "")
        registrar_log(usuario_id, "CRM_ATUALIZAR", f"demanda={demanda_id} | {resumo}")
    return total
