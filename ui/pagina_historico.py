"""Histórico de importações + aba com os registros REJEITADOS e DUPLICADOS (quais foram e por quê)."""
import json

import pandas as pd
import streamlit as st

from core.db import consultar
from ui import paginas

PREFIXO_DUPLICADO = "DUPLICADO"


def _conteudo(txt):
    """O conteúdo do registro foi guardado como JSON; devolve dict (ou vazio se não der para ler)."""
    try:
        d = json.loads(txt)
        return d if isinstance(d, dict) else {}
    except (TypeError, ValueError):
        return {}


def linhas_problemas(u):
    """Registros rejeitados e duplicados. Admin vê tudo; operador vê só as suas importações."""
    sql = ("SELECT r.id, r.importacao_id, i.nome_arquivo, i.origem AS fonte, us.nome AS usuario, "
           "i.data_hora, r.linha, r.motivo, r.conteudo FROM registros_rejeitados r "
           "JOIN importacoes i ON i.id = r.importacao_id JOIN usuarios us ON us.id = i.usuario_id ")
    if u["perfil"] == "admin":
        return consultar(sql + "ORDER BY r.id DESC LIMIT 1000")
    return consultar(sql + "WHERE i.usuario_id = %s ORDER BY r.id DESC LIMIT 1000", (u["id"],))


def montar_tabela(rows):
    saida = []
    for r in rows:
        c = _conteudo(r["conteudo"])
        dup = str(r["motivo"] or "").upper().startswith(PREFIXO_DUPLICADO)
        saida.append({
            "Tipo": "🔁 Duplicado" if dup else "⛔ Rejeitado",
            "Motivo": r["motivo"],
            "Importação": r["importacao_id"],
            "Arquivo": r["nome_arquivo"],
            "Linha": r["linha"],
            "Produto": c.get("produto"),
            "Origem": c.get("origem"),
            "Destino": c.get("destino"),
            "Peso (t)": c.get("peso_ton"),
            "Prazo": c.get("prazo"),
            "Frete (R$)": c.get("frete"),
            "Quando": r["data_hora"],
        })
    return pd.DataFrame(saida)


def _aba_problemas(u):
    st.caption("Registros que **não entraram** na base: os rejeitados (dados inválidos) e os "
               "duplicados (já existiam). Cada um mostra o motivo.")
    df = montar_tabela(linhas_problemas(u))
    n_dup = 0 if df.empty else int((df["Tipo"] == "🔁 Duplicado").sum())
    n_rej = 0 if df.empty else int((df["Tipo"] == "⛔ Rejeitado").sum())

    c1, c2 = st.columns(2)
    c1.metric("Rejeitados", n_rej)
    c2.metric("Duplicados", n_dup)

    total_dup = consultar("SELECT COALESCE(SUM(qtd_duplicados),0) AS n FROM importacoes")[0]["n"]
    if u["perfil"] == "admin" and int(total_dup) > n_dup:
        st.info(f"{int(total_dup) - n_dup} duplicado(s) foram descartados em importações feitas antes "
                "desta versão; nesses casos só o número foi guardado, não dá para listar quais eram.")

    if df.empty:
        st.success("Nenhum registro rejeitado ou duplicado.")
        return
    filtro = st.radio("Mostrar", ["Todos", "⛔ Rejeitado", "🔁 Duplicado"], horizontal=True)
    if filtro != "Todos":
        df = df[df["Tipo"] == filtro]
    df["Quando"] = pd.to_datetime(df["Quando"])
    st.dataframe(df, hide_index=True, use_container_width=True, column_config={
        "Quando": st.column_config.DatetimeColumn("Quando", format="DD/MM/YYYY HH:mm"),
    })


def pg_historico_completo(u):
    aba1, aba2 = st.tabs(["🕘 Importações", "⚠️ Rejeitados e duplicados"])
    with aba1:
        paginas.pg_historico(u)
    with aba2:
        _aba_problemas(u)
