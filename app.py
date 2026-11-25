"""HUBTECH – ponto de entrada. Rode:  python -m streamlit run app.py"""
import html

import streamlit as st

st.set_page_config(page_title="HUBTECH", page_icon="🚚", layout="wide")

from core import auth  # noqa: E402
from ui import estilo, pagina_historico, pagina_mensagem, paginas  # noqa: E402

PERFIL = {"admin": "Administrador", "operador": "Operador"}


def main():
    estilo.aplicar()
    u = st.session_state.get("user")
    if not u:
        paginas.tela_login()
        return

    menu = {
        "📊 Painel": paginas.pg_painel,
        "🗂️ CRM": paginas.pg_crm,
        "🧠 Importar dados (IA)": pagina_mensagem.pg_mensagem,
        "📦 Demandas": paginas.pg_demandas,
        "🕘 Histórico": pagina_historico.pg_historico_completo,
    }
    if u["perfil"] == "admin":
        menu["👥 Usuários"] = paginas.pg_usuarios
        menu["🛡️ Auditoria"] = paginas.pg_auditoria

    st.sidebar.markdown(
        '<div class="hub-brand"><div class="t">🚚 HUBTECH</div>'
        '<div class="s">Rodomax Transportes</div></div>'
        f'<div class="hub-user"><div class="n">{html.escape(u["nome"])}</div>'
        f'<div class="p">{PERFIL.get(u["perfil"], u["perfil"])} · {html.escape(u["email"])}</div></div>',
        unsafe_allow_html=True,
    )
    escolha = st.sidebar.radio("Menu", list(menu), label_visibility="collapsed")
    st.sidebar.divider()
    if st.sidebar.button("Sair"):
        auth.registrar_log(u["id"], "LOGOUT", u["email"])
        st.session_state.clear()
        st.rerun()

    menu[escolha](u)


main()
