"""Páginas da interface do HUBTECH."""
import html
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import streamlit as st

from core import auth, crm, importador
from core.db import consultar
from ia.modulo import prever
from ui.estilo import cabecalho

STATUS = {
    "CONCLUIDA": "✅ Concluída",
    "SEM_REGISTROS_NOVOS": "⚠️ Sem registros novos",
    "PROCESSANDO": "⏳ Processando",
}


# ---------- utilitários ----------
def _df(rows):
    """Lista de dicts -> DataFrame, com Decimal do MySQL convertido para número."""
    df = pd.DataFrame(rows)
    for c in df.columns:
        if df[c].map(lambda x: isinstance(x, Decimal)).any():
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _br(v, casas=0):
    s = f"{float(v or 0):,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# ---------- login ----------
def tela_login():
    _, meio, _ = st.columns([1, 1.4, 1])
    with meio:
        st.markdown(
            '<div class="login-hero"><div class="logo">🚚</div><h1>HUBTECH</h1>'
            "<p>Sistema de Integração e Gestão de Dados<br><b>Rodomax Transportes</b></p></div>",
            unsafe_allow_html=True,
        )
        with st.form("login"):
            email = st.text_input("E-mail", placeholder="voce@empresa.com")
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar", type="primary")
        if entrar:
            try:
                u = auth.autenticar(email, senha)
            except Exception as e:
                st.error(f"Erro ao conectar no banco: {e}")
                return
            if u:
                st.session_state["user"] = u
                st.rerun()
            st.error("E-mail ou senha inválidos.")


# ---------- painel ----------
def pg_painel(u):
    cabecalho("Painel", "Visão geral da base unificada de demandas", "📊")
    d = consultar("SELECT COUNT(*) AS n, COALESCE(SUM(peso_ton),0) AS ton, AVG(frete) AS frete FROM demandas")[0]
    i = consultar("SELECT COUNT(*) AS n, COALESCE(SUM(qtd_duplicados),0) AS dup, "
                  "COALESCE(SUM(qtd_rejeitados),0) AS rej FROM importacoes")[0]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Demandas", _br(d["n"]))
    c2.metric("Toneladas", _br(d["ton"], 1))
    c3.metric("Importações", _br(i["n"]))
    c4.metric("Duplicados evitados", _br(i["dup"]))
    c5.metric("Rejeitados", _br(i["rej"]))

    if int(d["n"]) == 0:
        st.info("Ainda não há dados. Vá em **🧠 Importar dados (IA)** para colar uma mensagem de frete.")
        return

    st.write("")
    st.subheader("Funil de demandas")
    funil = crm.resumo_funil()
    for c, s in zip(st.columns(len(crm.STATUS)), crm.STATUS):
        c.metric(crm.STATUS_ROTULO[s], funil["status"].get(s, 0))
    if funil["atrasadas"]:
        st.warning(f"⏰ {funil['atrasadas']} demanda(s) em aberto com prazo vencido. Veja no **🗂️ CRM**.")

    st.write("")
    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.subheader("Toneladas por produto")
            df = _df(consultar("SELECT produto, SUM(peso_ton) AS toneladas FROM demandas "
                               "GROUP BY produto ORDER BY toneladas DESC LIMIT 8"))
            st.bar_chart(df.set_index("produto")["toneladas"])
    with col2:
        with st.container(border=True):
            st.subheader("Rotas mais frequentes")
            df = _df(consultar("SELECT CONCAT(origem,' → ',destino) AS rota, COUNT(*) AS demandas "
                               "FROM demandas GROUP BY rota ORDER BY demandas DESC LIMIT 8"))
            st.bar_chart(df.set_index("rota")["demandas"])

    with st.container(border=True):
        st.subheader("Últimas importações")
        rows = consultar(
            "SELECT i.id, us.nome AS usuario, i.nome_arquivo, i.origem, i.qtd_registros, "
            "i.status, i.data_hora FROM importacoes i JOIN usuarios us ON us.id=i.usuario_id "
            "ORDER BY i.id DESC LIMIT 5")
        df = _df(rows)
        if not df.empty:
            df["status"] = df["status"].map(lambda s: STATUS.get(s, s))
            df["data_hora"] = pd.to_datetime(df["data_hora"])
        st.dataframe(df, hide_index=True, column_config={
            "id": "ID", "usuario": "Usuário", "nome_arquivo": "Arquivo", "origem": "Fonte",
            "qtd_registros": "Gravados", "status": "Status",
            "data_hora": st.column_config.DatetimeColumn("Quando", format="DD/MM/YYYY HH:mm"),
        })


# ---------- importar ----------
def _mostrar_resultado(res):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lidos", res["lidos"])
    c2.metric("Gravados", res["ok"])
    c3.metric("Duplicados", res["duplicados"])
    c4.metric("Rejeitados", res["rejeitados"])
    st.success(f"Importação #{res['importacao_id']} registrada em seu nome.")
    if res["ok"]:
        st.info(f"🗂️ {res['ok']} demanda(s) nova(s) já estão no **CRM**, com status *Nova* e você como responsável.")
    if res["rejeitados"]:
        rej = consultar("SELECT linha, motivo FROM registros_rejeitados WHERE importacao_id=%s",
                        (res["importacao_id"],))
        st.warning("Registros rejeitados:")
        st.dataframe(_df(rej), hide_index=True,
                     column_config={"linha": "Linha", "motivo": "Motivo"})


def pg_importar(u):
    cabecalho("Importar dados", "Envie um arquivo ou cole uma mensagem recebida", "📥")
    aba_arq, aba_txt = st.tabs(["📎 Enviar arquivo", "📋 Colar texto"])

    with aba_arq:
        origem = st.selectbox("Origem dos dados",
                              ["Planilha", "PDF", "E-mail", "WhatsApp", "API/JSON", "Outro"], key="origem_arq")
        arq = st.file_uploader("Arquivo (xlsx, csv, json, pdf, txt)",
                               type=["xlsx", "xls", "csv", "json", "pdf", "txt"])
        if arq and st.button("Processar e importar", type="primary", key="btn_arq"):
            try:
                res = importador.importar(u["id"], arq.name, arq.getvalue(), origem)
            except Exception as e:
                auth.registrar_log(u["id"], "IMPORTACAO_ERRO", f"{arq.name}: {e}")
                st.error(f"Falha na importação: {e}")
                return
            _mostrar_resultado(res)

    with aba_txt:
        origem_t = st.selectbox("De onde veio a mensagem?", ["WhatsApp", "E-mail", "Outro"], key="origem_txt")
        with st.expander("Exemplos de texto aceito"):
            st.code("Preciso levar 28 toneladas de soja de Cascavel para Paranaguá até 25/11/2026, "
                    "frete R$ 9.800,00\n\nProduto: Milho\nOrigem: Foz do Iguaçu\nDestino: Curitiba\n"
                    "Peso: 30000 kg\nPrazo: 27/11/2026", language=None)
            st.caption("Para várias demandas, separe cada uma com uma linha em branco.")
        texto = st.text_area("Texto da mensagem", height=220, key="texto_colado")
        if st.button("Processar texto", type="primary", key="btn_txt"):
            if not texto.strip():
                st.warning("Cole algum texto antes de processar.")
                return
            try:
                res = importador.importar_texto(u["id"], texto, origem_t)
            except Exception as e:
                auth.registrar_log(u["id"], "IMPORTACAO_ERRO", f"texto_colado: {e}")
                st.error(f"Falha na importação: {e}")
                return
            _mostrar_resultado(res)


# ---------- demandas ----------
def pg_demandas(u):
    cabecalho("Base de demandas", "Todas as demandas padronizadas, com origem e responsável pela importação", "📦")
    rows = consultar(
        "SELECT d.id, d.produto, d.origem, d.destino, d.peso_ton, d.prazo, d.frete, "
        "d.frete_estimado, d.status, d.prioridade, resp.nome AS responsavel, "
        "i.nome_arquivo, i.origem AS fonte, us.nome AS importado_por, i.data_hora "
        "FROM demandas d JOIN importacoes i ON i.id=d.importacao_id "
        "JOIN usuarios us ON us.id=i.usuario_id "
        "LEFT JOIN usuarios resp ON resp.id=d.responsavel_id ORDER BY d.id DESC LIMIT 2000")
    df = _df(rows)
    if df.empty:
        st.info("Nenhuma demanda importada ainda.")
        return
    df["prazo"] = pd.to_datetime(df["prazo"])
    df["data_hora"] = pd.to_datetime(df["data_hora"])
    df["status"] = df["status"].map(lambda s: crm.STATUS_ROTULO.get(s, s))
    df["prioridade"] = df["prioridade"].map(lambda p: crm.PRIORIDADE_ROTULO.get(p, p))

    busca = st.text_input("🔎 Buscar por produto, origem ou destino")
    if busca:
        m = df[["produto", "origem", "destino"]].apply(
            lambda c: c.astype(str).str.contains(busca, case=False)).any(axis=1)
        df = df[m]

    a, b = st.columns(2)
    a.metric("Demandas exibidas", _br(len(df)))
    b.metric("Toneladas", _br(df["peso_ton"].sum(), 1))

    st.dataframe(df, hide_index=True, column_config={
        "id": "ID", "produto": "Produto", "origem": "Origem", "destino": "Destino",
        "status": "Status", "prioridade": "Prioridade", "responsavel": "Responsável",
        "peso_ton": st.column_config.NumberColumn("Peso (t)", format="%.2f"),
        "prazo": st.column_config.DateColumn("Prazo", format="DD/MM/YYYY"),
        "frete": st.column_config.NumberColumn("Frete", format="R$ %.2f"),
        "frete_estimado": st.column_config.NumberColumn("Frete estimado (IA)", format="R$ %.2f"),
        "nome_arquivo": "Arquivo", "fonte": "Fonte", "importado_por": "Importado por",
        "data_hora": st.column_config.DatetimeColumn("Importado em", format="DD/MM/YYYY HH:mm"),
    })
    st.download_button("⬇️ Baixar CSV", df.to_csv(index=False).encode("utf-8-sig"), "demandas.csv")


# ---------- histórico ----------
def pg_historico(u):
    cabecalho("Histórico de importações", "Quem importou o quê, e quando", "🕘")
    sql = ("SELECT i.id, us.nome AS usuario, i.nome_arquivo, i.origem, i.qtd_lidos, i.qtd_registros, "
           "i.qtd_duplicados, i.qtd_rejeitados, i.status, i.data_hora FROM importacoes i "
           "JOIN usuarios us ON us.id=i.usuario_id ")
    if u["perfil"] == "admin":
        rows = consultar(sql + "ORDER BY i.id DESC LIMIT 500")
    else:
        rows = consultar(sql + "WHERE i.usuario_id=%s ORDER BY i.id DESC LIMIT 500", (u["id"],))
        st.caption("Você vê apenas as suas importações.")
    df = _df(rows)
    if df.empty:
        st.info("Nenhuma importação registrada.")
        return
    df["status"] = df["status"].map(lambda s: STATUS.get(s, s))
    df["data_hora"] = pd.to_datetime(df["data_hora"])
    st.dataframe(df, hide_index=True, column_config={
        "id": "ID", "usuario": "Usuário", "nome_arquivo": "Arquivo", "origem": "Fonte",
        "qtd_lidos": "Lidos", "qtd_registros": "Gravados", "qtd_duplicados": "Duplicados",
        "qtd_rejeitados": "Rejeitados", "status": "Status",
        "data_hora": st.column_config.DatetimeColumn("Quando", format="DD/MM/YYYY HH:mm"),
    })


# ---------- IA ----------
def pg_ia(u):
    cabecalho("Análise de demanda (IA)", "Envie uma demanda nova para o modelo de Inteligência Artificial", "🤖")
    with st.form("ia"):
        c1, c2 = st.columns(2)
        produto = c1.text_input("Produto")
        peso = c2.number_input("Peso (t)", min_value=0.0, step=0.5)
        origem = c1.text_input("Origem")
        destino = c2.text_input("Destino")
        frete = c1.number_input("Frete (R$)", min_value=0.0, step=100.0)
        prazo = c2.date_input("Prazo")
        ok = st.form_submit_button("Analisar demanda", type="primary")
    if ok:
        dem = dict(produto=produto, origem=origem, destino=destino, peso_ton=peso,
                   prazo=str(prazo), frete=frete)
        res = prever(dem)
        auth.registrar_log(u["id"], "ANALISE_IA", str(dem))
        with st.container(border=True):
            st.subheader(str(res.get("resultado")))
            st.write(res.get("detalhe"))
            if res.get("frete_estimado") is not None:
                st.metric("Frete estimado", f"R$ {_br(res['frete_estimado'], 2)}")


# ---------- administração ----------
def pg_usuarios(u):
    cabecalho("Usuários", "Gerencie quem tem acesso ao HUBTECH", "👥")
    with st.expander("➕ Novo usuário"):
        with st.form("novo"):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome")
            email = c2.text_input("E-mail")
            senha = c1.text_input("Senha", type="password")
            perfil = c2.selectbox("Perfil", ["operador", "admin"])
            if st.form_submit_button("Criar usuário", type="primary"):
                try:
                    auth.criar_usuario(nome, email, senha, perfil, autor_id=u["id"])
                    st.success("Usuário criado.")
                except Exception as e:
                    st.error(str(e))

    rows = consultar("SELECT id, nome, email, perfil, ativo, criado_em FROM usuarios ORDER BY id")
    df = _df(rows)
    df["ativo"] = df["ativo"].map(lambda a: "🟢 Ativo" if int(a) else "🔴 Inativo")
    df["criado_em"] = pd.to_datetime(df["criado_em"])
    st.dataframe(df, hide_index=True, column_config={
        "id": "ID", "nome": "Nome", "email": "E-mail", "perfil": "Perfil", "ativo": "Situação",
        "criado_em": st.column_config.DatetimeColumn("Criado em", format="DD/MM/YYYY HH:mm"),
    })

    st.subheader("Ativar / desativar")
    opcoes = {f"{r['nome']} ({r['email']})": r["id"] for r in rows}
    escolhido = st.selectbox("Usuário", list(opcoes))
    c1, c2, _ = st.columns([1, 1, 3])
    if c1.button("Ativar"):
        auth.alterar_status(opcoes[escolhido], True, u["id"])
        st.rerun()
    if c2.button("Desativar"):
        if opcoes[escolhido] == u["id"]:
            st.error("Você não pode desativar a si mesmo.")
        else:
            auth.alterar_status(opcoes[escolhido], False, u["id"])
            st.rerun()


def pg_auditoria(u):
    cabecalho("Log de auditoria", "Registro de todas as ações realizadas no sistema", "🛡️")
    rows = consultar(
        "SELECT l.id, COALESCE(us.nome,'(desconhecido)') AS usuario, l.acao, l.detalhe, l.data_hora "
        "FROM log_auditoria l LEFT JOIN usuarios us ON us.id=l.usuario_id "
        "ORDER BY l.id DESC LIMIT 1000")
    df = _df(rows)
    if df.empty:
        st.info("Nenhum registro ainda.")
        return
    df["data_hora"] = pd.to_datetime(df["data_hora"])
    acoes = ["Todas"] + sorted(df["acao"].unique())
    filtro = st.selectbox("Filtrar por ação", acoes)
    if filtro != "Todas":
        df = df[df["acao"] == filtro]
    st.dataframe(df, hide_index=True, column_config={
        "id": "ID", "usuario": "Usuário", "acao": "Ação", "detalhe": "Detalhe",
        "data_hora": st.column_config.DatetimeColumn("Quando", format="DD/MM/YYYY HH:mm:ss"),
    })


# ---------- CRM ----------
COLUNAS_QUADRO = ["NOVA", "EM_ANALISE", "AGUARDANDO_MOTORISTA", "EM_TRANSPORTE", "ENTREGUE"]
MAX_CARTOES = 12


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def _info_cartao(r):
    """(aberta, dias_de_atraso, dias_na_etapa) de uma demanda."""
    hoje = date.today()
    aberta = r["status"] in crm.STATUS_ABERTOS
    atraso = (hoje - r["prazo"]).days if (aberta and r["prazo"] and r["prazo"] < hoje) else 0
    etapa = (datetime.now() - r["etapa_desde"]).days if r.get("etapa_desde") else 0
    return aberta, atraso, max(etapa, 0)


def _card_html(r):
    aberta, atraso, etapa = _info_cartao(r)
    e = html.escape
    chips = [f'<span class="chip">⚖️ {_br(r["peso_ton"], 1)} t</span>']
    if r["prazo"]:
        chips.append(f'<span class="chip">📅 {r["prazo"]:%d/%m}</span>')
    else:
        chips.append('<span class="chip">📅 sem prazo</span>')
    if atraso:
        chips.append(f'<span class="chip chip-red">⏰ atrasada há {_plural(atraso, "dia", "dias")}</span>')
    if r.get("frete") is None and r.get("frete_estimado") is not None:
        chips.append(f'<span class="chip chip-ia">💡 ~R$ {crm.formatar_brl(r["frete_estimado"])} (IA)</span>')
    rodape = f'👤 {e(r["responsavel"] or "sem responsável")}'
    if aberta and etapa >= 1:
        classe = "warn" if etapa >= 3 else ""
        rodape += f' · <span class="{classe}">⏳ {_plural(etapa, "dia", "dias")} nesta etapa</span>'
    return (
        f'<div class="kcard prio-{e(str(r["prioridade"]))}">'
        f'<div class="kc-top"><span>#{r["id"]}</span>'
        f'<span>{crm.PRIORIDADE_ROTULO.get(r["prioridade"], "")}</span></div>'
        f'<div class="kc-title">{e(str(r["produto"]))}</div>'
        f'<div class="kc-route">{e(str(r["origem"]))} → {e(str(r["destino"]))}</div>'
        f'<div class="kc-chips">{"".join(chips)}</div>'
        f'<div class="kc-foot">{rodape}</div></div>'
    )


def _cartao(r, prefixo):
    st.markdown(_card_html(r), unsafe_allow_html=True)
    if st.button("Abrir", key=f"{prefixo}_abrir_{r['id']}"):
        _dialog_demanda(r["id"], st.session_state["user"])


def _texto_historico(h):
    if h["tipo"] == "STATUS":
        return f"mudou o status de **{h['de_valor']}** para **{h['para_valor']}**"
    if h["tipo"] == "PRIORIDADE":
        return f"mudou a prioridade de {h['de_valor']} para {h['para_valor']}"
    if h["tipo"] == "RESPONSAVEL":
        return f"mudou o responsável de {h['de_valor']} para **{h['para_valor']}**"
    if h["tipo"] == "NOTA":
        return f"anotou: {h['texto']}"
    return h["texto"] or h["tipo"]


@st.dialog("Detalhe da demanda", width="large")
def _dialog_demanda(demanda_id, u):
    d = crm.obter(demanda_id)
    if not d:
        st.warning("Demanda não encontrada.")
        return
    usuarios = consultar("SELECT id, nome FROM usuarios WHERE ativo=1 ORDER BY nome")

    st.subheader(f"#{d['id']} · {d['produto']}")
    i1, i2, i3, i4 = st.columns(4)
    i1.metric("Rota", f"{d['origem']} → {d['destino']}")
    i2.metric("Peso", f"{_br(d['peso_ton'], 2)} t")
    i3.metric("Prazo", d["prazo"].strftime("%d/%m/%Y") if d["prazo"] else "—")
    if d["frete"] is not None:
        i4.metric("Frete", f"R$ {_br(d['frete'], 2)}")
    elif d.get("frete_estimado") is not None:
        i4.metric("Frete (sugestão IA)", f"~R$ {_br(d['frete_estimado'], 2)}")
    else:
        i4.metric("Frete", "—")
    st.caption(f"Origem do dado: importação #{d['importacao']} ({d['fonte']}, {d['nome_arquivo']}) "
               f"por {d['importado_por']} em {d['importado_em']:%d/%m/%Y %H:%M}")

    nomes = {None: "(sem responsável)"}
    nomes.update({x["id"]: x["nome"] for x in usuarios})
    if d["responsavel_id"] not in nomes:
        nomes[d["responsavel_id"]] = f"{d['responsavel']} (inativo)"
    ids = list(nomes)
    permitidos = crm.status_permitidos(d["status"])

    with st.form(f"form_crm_{demanda_id}"):
        c1, c2, c3 = st.columns(3)
        novo_status = c1.selectbox("Status", permitidos, index=0,
                                   format_func=lambda s: crm.STATUS_ROTULO[s])
        novo_resp = c2.selectbox("Responsável", ids, index=ids.index(d["responsavel_id"]),
                                 format_func=lambda i: nomes[i])
        nova_prio = c3.selectbox("Prioridade", crm.PRIORIDADES,
                                 index=crm.PRIORIDADES.index(d["prioridade"]),
                                 format_func=lambda p: crm.PRIORIDADE_ROTULO[p])
        nota = st.text_area("Anotação (obrigatória ao cancelar: informe o motivo)", height=80,
                            placeholder="Ex.: motorista confirmado para quarta-feira")
        salvar = st.form_submit_button("Salvar alterações", type="primary")
    if salvar:
        try:
            n = crm.atualizar(d["id"], u["id"], status=novo_status, prioridade=nova_prio,
                              responsavel_id=novo_resp, nota=nota)
        except Exception as e:
            st.error(f"Não foi possível salvar: {e}")
        else:
            st.session_state["crm_msg"] = (f"Demanda #{d['id']} atualizada ({n} alteração(ões))."
                                           if n else "Nada foi alterado.")
            st.rerun()

    st.markdown("**Histórico**")
    for h in crm.historico(demanda_id):
        st.markdown(f"- `{h['data_hora']:%d/%m/%Y %H:%M}` **{h['usuario']}** — {_texto_historico(h)}")


def _grade(lista, prefixo, ncols=4):
    cols = st.columns(ncols)
    for i, r in enumerate(lista[:24]):
        with cols[i % ncols]:
            _cartao(r, prefixo)


def _aba_quadro(rows):
    if not rows:
        st.info("Nenhuma demanda encontrada. Cole uma mensagem em **🧠 Importar dados (IA)** "
                "e ela entra aqui automaticamente como *Nova*.")
        return
    por_status = {s: [r for r in rows if r["status"] == s] for s in crm.STATUS}
    for col, s in zip(st.columns(len(COLUNAS_QUADRO)), COLUNAS_QUADRO):
        with col:
            st.markdown(f'<div class="crm-col-head s-{s}">{crm.STATUS_ROTULO[s]}'
                        f'<span>{len(por_status[s])}</span></div>', unsafe_allow_html=True)
            if not por_status[s]:
                st.caption("— vazio —")
            for r in por_status[s][:MAX_CARTOES]:
                _cartao(r, "q")
            if len(por_status[s]) > MAX_CARTOES:
                st.caption(f"+ {len(por_status[s]) - MAX_CARTOES} demanda(s). Use os filtros.")
    with st.expander(f"Canceladas ({len(por_status['CANCELADA'])})"):
        for r in por_status["CANCELADA"][:MAX_CARTOES]:
            _cartao(r, "q")


def _aba_planilha(u, rows, usuarios):
    if not rows:
        st.info("Nenhuma demanda encontrada.")
        return
    st.caption("Edite status, responsável e prioridade direto na tabela e clique em salvar. "
               "As mudanças de status seguem as regras do funil; para cancelar, use o cartão "
               "(o motivo é obrigatório).")
    sem = "(sem responsável)"
    nomes = {x["id"]: x["nome"] for x in usuarios}
    for r in rows:
        if r["responsavel_id"] and r["responsavel_id"] not in nomes:
            nomes[r["responsavel_id"]] = f"{r['responsavel']} (inativo)"
    contagem = {}
    for n in nomes.values():
        contagem[n] = contagem.get(n, 0) + 1
    rotulo_resp = {i: (n if contagem[n] == 1 else f"{n} (#{i})") for i, n in nomes.items()}
    id_por_rotulo = {v: k for k, v in rotulo_resp.items()}
    opcoes_resp = [sem] + sorted(rotulo_resp.values())
    rot_status = [crm.STATUS_ROTULO[s] for s in crm.STATUS]
    cod_status = {crm.STATUS_ROTULO[s]: s for s in crm.STATUS}
    rot_prio = [crm.PRIORIDADE_ROTULO[p] for p in crm.PRIORIDADES]
    cod_prio = {crm.PRIORIDADE_ROTULO[p]: p for p in crm.PRIORIDADES}

    df = pd.DataFrame([{
        "id": r["id"], "produto": r["produto"], "rota": f"{r['origem']} → {r['destino']}",
        "peso_ton": float(r["peso_ton"] or 0),
        "prazo": pd.to_datetime(r["prazo"]) if r["prazo"] else pd.NaT,
        "status": crm.STATUS_ROTULO[r["status"]],
        "prioridade": crm.PRIORIDADE_ROTULO[r["prioridade"]],
        "responsavel": rotulo_resp.get(r["responsavel_id"], sem),
    } for r in rows])

    chave = f"planilha_{st.session_state.get('planilha_v', 0)}"
    editado = st.data_editor(
        df, hide_index=True, key=chave,
        disabled=["id", "produto", "rota", "peso_ton", "prazo"],
        column_config={
            "id": "ID", "produto": "Produto", "rota": "Rota",
            "peso_ton": st.column_config.NumberColumn("Peso (t)", format="%.2f"),
            "prazo": st.column_config.DateColumn("Prazo", format="DD/MM/YYYY"),
            "status": st.column_config.SelectboxColumn("Status", options=rot_status, required=True),
            "prioridade": st.column_config.SelectboxColumn("Prioridade", options=rot_prio, required=True),
            "responsavel": st.column_config.SelectboxColumn("Responsável", options=opcoes_resp,
                                                            required=True),
        })

    if st.button("💾 Salvar alterações da planilha", type="primary", key="salvar_planilha"):
        campos = ["status", "prioridade", "responsavel"]
        alteradas, erros = 0, []
        for idx in editado.index:
            novo, antigo = editado.loc[idx], df.loc[idx]
            if all(novo[c] == antigo[c] for c in campos):
                continue
            resp = None if novo["responsavel"] == sem else id_por_rotulo[novo["responsavel"]]
            try:
                crm.atualizar(int(antigo["id"]), u["id"], status=cod_status[novo["status"]],
                              prioridade=cod_prio[novo["prioridade"]], responsavel_id=resp)
                alteradas += 1
            except Exception as e:
                erros.append(f"#{int(antigo['id'])}: {e}")
        if not alteradas and not erros:
            st.info("Nenhuma alteração para salvar.")
            return
        st.session_state["planilha_v"] = st.session_state.get("planilha_v", 0) + 1
        if alteradas:
            st.session_state["crm_msg"] = f"{alteradas} demanda(s) atualizada(s) pela planilha."
        if erros:
            st.session_state["crm_erros"] = erros
        st.rerun()


def _aba_meu_dia(u):
    minhas = [r for r in crm.listar_quadro(responsavel_id=u["id"]) if r["status"] in crm.STATUS_ABERTOS]
    hoje = date.today()
    atrasadas = [r for r in minhas if r["prazo"] and r["prazo"] < hoje]
    vencem_hoje = [r for r in minhas if r["prazo"] == hoje]
    usados = {r["id"] for r in atrasadas + vencem_hoje}
    paradas = [r for r in minhas if r["id"] not in usados and _info_cartao(r)[2] >= 3]

    c1, c2, c3 = st.columns(3)
    c1.metric("Atrasadas", len(atrasadas))
    c2.metric("Vencem hoje", len(vencem_hoje))
    c3.metric("Paradas há 3+ dias", len(paradas))
    if not (atrasadas or vencem_hoje or paradas):
        st.success("Tudo em dia! Nenhuma demanda sua atrasada, vencendo hoje ou parada.")
        return
    for titulo, lista in (("⏰ Atrasadas", atrasadas), ("📅 Vencem hoje", vencem_hoje),
                          ("⏳ Paradas na etapa", paradas)):
        if lista:
            st.subheader(f"{titulo} ({len(lista)})")
            _grade(lista, "d")


def pg_crm(u):
    cabecalho("CRM de demandas", "Acompanhe cada demanda do recebimento até a entrega", "🗂️")
    msg = st.session_state.pop("crm_msg", None)
    if msg:
        st.success(msg)
    for erro in st.session_state.pop("crm_erros", None) or []:
        st.error(erro)

    usuarios = consultar("SELECT id, nome FROM usuarios WHERE ativo=1 ORDER BY nome")
    f1, f2, f3 = st.columns([1.2, 1.2, 2.4])
    escopo = f1.selectbox("Responsável", ["Todas", "Minhas"])
    rot_prio = ["Todas"] + [crm.PRIORIDADE_ROTULO[p] for p in crm.PRIORIDADES]
    esc_prio = f2.selectbox("Prioridade", rot_prio)
    busca = f3.text_input("🔎 Buscar", placeholder="produto, origem ou destino")
    prio = None if esc_prio == "Todas" else crm.PRIORIDADES[rot_prio.index(esc_prio) - 1]
    rows = crm.listar_quadro(u["id"] if escopo == "Minhas" else None, prio, busca or None)

    tab_q, tab_p, tab_d = st.tabs(["📋 Quadro", "🗒️ Planilha", "☀️ Meu dia"])
    with tab_q:
        _aba_quadro(rows)
    with tab_p:
        _aba_planilha(u, rows, usuarios)
    with tab_d:
        _aba_meu_dia(u)
