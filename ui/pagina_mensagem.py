"""Tela "Importar dados (IA)": a IA le uma mensagem OU um arquivo e extrai as demandas.

Aba MENSAGEM:
  1. cola (ou escolhe um exemplo de) mensagem de WhatsApp/e-mail;
  2. a IA extrai produto, origem, destino, peso, prazo e frete;
  3. a tela mostra lado a lado o que o sistema ANTIGO (regex) leu e o que a IA leu;
  4. a pessoa confere/corrige e so entao salva no HUB (entra no CRM como "Nova").

Aba ARQUIVO (Excel, CSV, JSON, PDF, TXT):
  1. envia o arquivo; a IA le cada linha/bloco e preenche o que estiver faltando;
  2. a tela mostra uma tabela editavel (uma demanda por linha) com a origem de cada dado;
  3. a pessoa confere/corrige e salva tudo de uma vez no HUB.
"""
from datetime import date

import pandas as pd
import streamlit as st

from core import auth, importador
from ia import extrator, leitor_arquivo
from ia import frete as frete_ia
from ia import modulo as ia_modulo
from ui.estilo import cabecalho
from ui.paginas import _mostrar_resultado

EXEMPLOS = {
    "Prazo e frete informais": "Preciso levar 20 t de milho de Toledo para Maringá até sexta, uns 6 mil",
    "Peso em quilos": "Bom dia! Tenho uns 30 mil quilos de soja saindo de Cascavel com destino a "
                      "Paranaguá, preciso até dia 28. Frete R$ 9.800,00",
    "Formato livre": "Pessoal, 25 toneladas de trigo, Londrina > Curitiba, tem que chegar amanhã, "
                     "pago 7k",
}


def _vazio(v):
    return v is None or (not isinstance(v, str) and pd.isna(v))


def leitura_regex(texto):
    """O que o extrator ANTIGO (regex, core/importador.py) entende da mesma mensagem."""
    try:
        df = importador.padronizar(importador._ler_texto(texto))
    except Exception:
        return {c: None for c in extrator.CAMPOS}
    if df.empty:
        return {c: None for c in extrator.CAMPOS}
    r = df.iloc[0]
    saida = {c: (None if _vazio(r[c]) else r[c]) for c in extrator.CAMPOS}
    if saida["prazo"] is not None:
        saida["prazo"] = str(saida["prazo"])
    return saida


def _linha_importador(campos):
    """Uma demanda conferida -> linha no formato que o importador espera.
    Peso e frete vao como texto com virgula decimal (o importador le assim sem ambiguidade)."""
    prazo = campos["prazo"].strftime("%d/%m/%Y") if campos["prazo"] else None
    frete = f"{campos['frete']:.2f}".replace(".", ",") if campos["frete"] else None
    peso = f"{campos['peso_ton']:.2f}".replace(".", ",") if campos["peso_ton"] else None
    return {"produto": campos["produto"], "origem": campos["origem"], "destino": campos["destino"],
            "peso_ton": peso, "prazo": prazo, "frete": frete}


def para_dataframe(campos):
    return pd.DataFrame([_linha_importador(campos)])


def _nulo(v):
    return None if _vazio(v) or v == "" else v


def para_dataframe_lote(df):
    """Tabela editada na tela (uma demanda por linha) -> DataFrame para o importador.
    Linhas totalmente vazias sao ignoradas."""
    linhas = []
    for _, r in df.iterrows():
        prazo = _nulo(r["prazo"])
        campos = {
            "produto": _nulo(r["produto"]), "origem": _nulo(r["origem"]),
            "destino": _nulo(r["destino"]),
            "peso_ton": _nulo(r["peso_ton"]), "frete": _nulo(r["frete"]),
            "prazo": prazo.date() if hasattr(prazo, "date") else prazo,
        }
        if all(v is None for v in campos.values()):
            continue
        linhas.append(_linha_importador(campos))
    return pd.DataFrame(linhas, columns=["produto", "origem", "destino", "peso_ton", "prazo", "frete"])


def _fmt(campo, v):
    if _vazio(v) or v == "":
        return "—"
    if campo == "peso_ton":
        return f"{float(v):g} t"
    if campo == "frete":
        return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if campo == "prazo":
        a, m, d = str(v)[:10].split("-")
        return f"{d}/{m}/{a}"
    return str(v)


def _sugestao_frete(campos):
    """Sugestao de frete (ou None) quando a mensagem NAO trouxe frete. Falha na IA nao derruba a tela."""
    if campos.get("frete") is not None:
        return None
    try:
        return frete_ia.estimar(campos, ia_modulo.carregar_historico())
    except Exception:
        return None


def _usar_exemplo(texto):
    st.session_state["msg_texto"] = texto
    st.session_state.pop("msg_resultado", None)


def pg_mensagem(u):
    cabecalho("Importar dados (IA)",
              "Cole uma mensagem ou envie um arquivo (Excel, CSV, JSON, PDF, TXT): a IA extrai as demandas",
              "🧠")
    aba_msg, aba_arq = st.tabs(["💬 Mensagem", "📎 Arquivo"])
    with aba_msg:
        _aba_mensagem(u)
    with aba_arq:
        _aba_arquivo(u)


def _aba_mensagem(u):
    st.caption("Exemplos para testar:")
    cols = st.columns(len(EXEMPLOS))
    for col, (nome, txt) in zip(cols, EXEMPLOS.items()):
        col.button(nome, on_click=_usar_exemplo, args=(txt,), use_container_width=True)

    texto = st.text_area("Mensagem recebida", height=130, key="msg_texto",
                         placeholder="Ex.: Preciso levar 28 toneladas de soja de Cascavel para "
                                     "Paranaguá até sexta, uns 10 mil de frete")
    c1, c2 = st.columns(2)
    ref = c1.date_input("Data em que a mensagem chegou", value=date.today(), key="msg_ref",
                        help="Usada para entender 'amanhã', 'sexta', 'fim do mês'...")
    spacy_ok, _erro = extrator.status_spacy()
    usar_spacy = c2.checkbox("Usar também o spaCy (modelo de linguagem)", value=spacy_ok,
                             disabled=not spacy_ok, key="msg_spacy")
    c2.caption("✅ spaCy carregado" if spacy_ok else "ℹ️ spaCy não carregado: usando só as regras")

    if st.button("🧠 Extrair com IA", type="primary"):
        if not texto.strip():
            st.warning("Cole uma mensagem antes de extrair.")
        else:
            campos_ia = extrator.extrair(texto, ref, usar_spacy=usar_spacy)
            st.session_state["msg_resultado"] = {
                "texto": texto,
                "ia": campos_ia,
                "regex": leitura_regex(texto),
                "frete_ia": _sugestao_frete(campos_ia),
                "n": st.session_state.get("msg_n", 0) + 1,
            }
            st.session_state["msg_n"] = st.session_state["msg_resultado"]["n"]
            auth.registrar_log(u["id"], "EXTRACAO_PLN", texto[:200])

    res = st.session_state.get("msg_resultado")
    if not res:
        return

    st.markdown("#### O que cada sistema entendeu")
    nomes = {"produto": "Produto", "origem": "Origem", "destino": "Destino",
             "peso_ton": "Peso", "prazo": "Prazo", "frete": "Frete"}
    tabela = pd.DataFrame({
        "Campo": [nomes[c] for c in extrator.CAMPOS],
        "Sistema antigo (regex)": [_fmt(c, res["regex"][c]) for c in extrator.CAMPOS],
        "IA (PLN)": [_fmt(c, res["ia"][c]) for c in extrator.CAMPOS],
    })
    st.dataframe(tabela, hide_index=True, use_container_width=True)

    st.markdown("#### Conferir e salvar no HUB")
    st.caption("A IA pode errar: confira os campos antes de salvar. Peso e frete vazios são aceitos "
               "só se você preencher; frete 0 = sem frete informado.")
    ia, n = res["ia"], res["n"]
    a, b, c = st.columns(3)
    produto = a.text_input("Produto", value=ia["produto"] or "", key=f"p_{n}")
    origem = b.text_input("Origem", value=ia["origem"] or "", key=f"o_{n}")
    destino = c.text_input("Destino", value=ia["destino"] or "", key=f"d_{n}")
    d1, d2, d3 = st.columns(3)
    peso = d1.number_input("Peso (t)", min_value=0.0, step=0.5, value=float(ia["peso_ton"] or 0.0),
                           key=f"w_{n}")
    tem_prazo = d2.checkbox("Tem prazo", value=bool(ia["prazo"]), key=f"tp_{n}")
    prazo = d2.date_input("Prazo", value=date.fromisoformat(ia["prazo"]) if ia["prazo"] else ref,
                          disabled=not tem_prazo, key=f"pz_{n}")
    frete = d3.number_input("Frete (R$)", min_value=0.0, step=100.0, value=float(ia["frete"] or 0.0),
                            key=f"f_{n}")
    if ia["frete"] is None:
        if res.get("frete_ia"):
            d3.info("💡 **Sugestão da IA** (não é o frete real): " + frete_ia.explicar(res["frete_ia"]))
        else:
            d3.caption("💡 " + frete_ia.SEM_BASE)
    origem_dado = st.selectbox("De onde veio a mensagem?", ["WhatsApp", "E-mail", "Outro"],
                               key=f"od_{n}")

    if st.button("💾 Salvar no HUB", key=f"s_{n}"):
        if not (produto.strip() and origem.strip() and destino.strip() and peso > 0):
            st.warning("Preencha produto, origem, destino e peso para salvar.")
            return
        campos = {"produto": produto.strip(), "origem": origem.strip(), "destino": destino.strip(),
                  "peso_ton": peso, "prazo": prazo if tem_prazo else None,
                  "frete": frete or None}
        try:
            resultado = importador._processar(u["id"], "mensagem_ia", para_dataframe(campos), origem_dado)
        except Exception as e:
            auth.registrar_log(u["id"], "IMPORTACAO_ERRO", f"mensagem_ia: {e}")
            st.error(f"Falha ao salvar: {e}")
            return
        _mostrar_resultado(resultado)


FONTES = ["Planilha", "PDF", "E-mail", "WhatsApp", "API/JSON", "Outro"]
_FONTE_POR_EXT = {"xlsx": "Planilha", "xls": "Planilha", "csv": "Planilha", "pdf": "PDF",
                  "json": "API/JSON", "txt": "Outro"}


def _para_editor(df):
    """Prepara a tabela para o editor da tela (data como Timestamp, números como float)."""
    df = df.copy()
    df["prazo"] = pd.to_datetime(df["prazo"], errors="coerce")
    for c in ("peso_ton", "frete", "frete_estimado"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _aba_arquivo(u):
    st.caption("A IA lê o arquivo, entende o que cada linha diz e preenche o que estiver faltando "
               "(por exemplo, um prazo escrito como \"até sexta\" numa coluna de observação).")
    arq = st.file_uploader("Arquivo (Excel, CSV, JSON, PDF ou TXT)",
                           type=["xlsx", "xls", "csv", "json", "pdf", "txt"], key="arq_up")
    c1, c2 = st.columns(2)
    ref = c1.date_input("Data de referência do arquivo", value=date.today(), key="arq_ref",
                        help="Usada para entender 'amanhã', 'sexta', 'fim do mês'...")
    spacy_ok, _erro = extrator.status_spacy()
    usar_spacy = c2.checkbox("Usar também o spaCy (modelo de linguagem)", value=spacy_ok,
                             disabled=not spacy_ok, key="arq_spacy")

    if st.button("🧠 Ler arquivo com IA", type="primary", disabled=arq is None):
        try:
            try:
                historico = ia_modulo.carregar_historico()
            except Exception:
                historico = None  # sem banco/histórico: lê o arquivo normalmente, sem sugerir frete
            df = leitor_arquivo.ler_demandas(arq.name, arq.getvalue(), ref, usar_spacy, historico)
        except Exception as e:
            auth.registrar_log(u["id"], "LEITURA_ARQUIVO_ERRO", f"{arq.name}: {e}")
            st.error(f"Não consegui ler o arquivo: {e}")
            return
        st.session_state["arq_n"] = st.session_state.get("arq_n", 0) + 1
        st.session_state["arq_resultado"] = {"nome": arq.name, "df": df, "n": st.session_state["arq_n"]}
        auth.registrar_log(u["id"], "LEITURA_ARQUIVO_IA", f"{arq.name} | {len(df)} demanda(s)")

    res = st.session_state.get("arq_resultado")
    if not res:
        return
    if res["df"].empty:
        st.warning(f"Não encontrei nenhuma demanda em **{res['nome']}**.")
        return

    n = res["n"]
    st.markdown(f"#### {len(res['df'])} demanda(s) encontrada(s) em {res['nome']}")
    st.caption("Confira e corrija na própria tabela (clique na célula). Para apagar uma linha, "
               "selecione-a e aperte Delete. A coluna *Leitura* mostra de onde veio cada dado. "
               "O *frete sugerido pela IA* só aparece quando a demanda não tem frete e existe base "
               "real; ele **não** vira o frete da demanda, fica guardado como sugestão.")
    editado = st.data_editor(
        _para_editor(res["df"]), key=f"ed_{n}", hide_index=True, num_rows="dynamic",
        use_container_width=True,
        disabled=["frete_estimado", "base_estimativa", "leitura", "trecho"],
        column_config={
            "produto": "Produto", "origem": "Origem", "destino": "Destino",
            "peso_ton": st.column_config.NumberColumn("Peso (t)", min_value=0.0, step=0.5),
            "prazo": st.column_config.DateColumn("Prazo", format="DD/MM/YYYY"),
            "frete": st.column_config.NumberColumn("Frete (R$)", min_value=0.0, step=100.0,
                                                   format="%.2f"),
            "frete_estimado": st.column_config.NumberColumn("💡 Frete sugerido pela IA (R$)",
                                                            format="%.2f"),
            "base_estimativa": "Base da sugestão",
            "leitura": "Leitura", "trecho": "Trecho do arquivo",
        })
    ext = res["nome"].lower().rsplit(".", 1)[-1]
    origem_dado = st.selectbox("Fonte dos dados", FONTES, key=f"fonte_{n}",
                               index=FONTES.index(_FONTE_POR_EXT.get(ext, "Outro")))

    if st.button("💾 Salvar todas no HUB", key=f"salvar_arq_{n}"):
        lote = para_dataframe_lote(editado)
        if lote.empty:
            st.warning("Não há demandas para salvar.")
            return
        try:
            resultado = importador._processar(u["id"], res["nome"], lote, origem_dado)
        except Exception as e:
            auth.registrar_log(u["id"], "IMPORTACAO_ERRO", f"{res['nome']}: {e}")
            st.error(f"Falha ao salvar: {e}")
            return
        _mostrar_resultado(resultado)
        st.caption("Os registros rejeitados e os duplicados podem ser consultados em "
                   "**🕘 Histórico → Rejeitados e duplicados**.")
