"""Identidade visual do HUBTECH (CSS + helpers)."""
import streamlit as st

CSS = """
<style>
:root{--azul:#0B8FCB;--navy:#0B2A4A;--borda:#E3EAF2;--suave:#6B7A8C;}
.block-container{padding-top:2rem;max-width:1250px;}
#MainMenu, footer{visibility:hidden;}
h1,h2,h3{color:var(--navy);letter-spacing:-.01em;}

/* sidebar */
[data-testid="stSidebar"]{background:#fff;border-right:1px solid var(--borda);}
.hub-brand{background:linear-gradient(135deg,#0B2A4A 0%,#0B8FCB 100%);color:#fff;
  border-radius:14px;padding:16px 18px;margin-bottom:12px;}
.hub-brand .t{font-size:1.3rem;font-weight:800;letter-spacing:.02em;}
.hub-brand .s{font-size:.75rem;opacity:.85;}
.hub-user{border:1px solid var(--borda);border-radius:12px;padding:10px 14px;margin-bottom:10px;background:#F8FAFD;}
.hub-user .n{font-weight:700;color:var(--navy);}
.hub-user .p{font-size:.75rem;color:var(--suave);}

/* cabeçalho de página */
.hub-head{margin-bottom:1.2rem;padding-bottom:.8rem;border-bottom:2px solid var(--borda);}
.hub-head h1{margin:0;font-size:1.9rem;}
.hub-head p{margin:.2rem 0 0;color:var(--suave);}

/* cartões de métrica */
[data-testid="stMetric"]{background:#fff;border:1px solid var(--borda);border-radius:14px;
  padding:14px 18px;box-shadow:0 1px 3px rgba(16,24,40,.05);}
[data-testid="stMetricLabel"] p{color:var(--suave);font-weight:600;text-transform:uppercase;
  font-size:.72rem;letter-spacing:.06em;}
[data-testid="stMetricValue"]{color:var(--navy);font-weight:800;}

/* botões, tabelas, abas */
.stButton>button,.stFormSubmitButton>button,.stDownloadButton>button{border-radius:10px;font-weight:600;}
.stFormSubmitButton>button{width:100%;}
[data-testid="stDataFrame"]{border:1px solid var(--borda);border-radius:12px;overflow:hidden;}
.stTabs [data-baseweb="tab"]{font-weight:600;}
[data-testid="stForm"]{background:#fff;border:1px solid var(--borda);border-radius:14px;padding:1.2rem;}

/* quadro CRM */
.crm-col-head{display:flex;justify-content:space-between;align-items:center;background:#475569;color:#fff;
  border-radius:10px;padding:8px 12px;font-weight:700;font-size:.85rem;margin-bottom:8px;}
.crm-col-head span{background:rgba(255,255,255,.25);border-radius:20px;padding:0 9px;}
.crm-col-head.s-NOVA{background:#475569;}
.crm-col-head.s-EM_ANALISE{background:#0B8FCB;}
.crm-col-head.s-AGUARDANDO_MOTORISTA{background:#D97706;}
.crm-col-head.s-EM_TRANSPORTE{background:#7C3AED;}
.crm-col-head.s-ENTREGUE{background:#15803D;}
.kcard{background:#fff;border:1px solid var(--borda);border-left:5px solid #CBD5E1;border-radius:12px;
  padding:10px 12px;box-shadow:0 1px 3px rgba(16,24,40,.06);}
.kcard.prio-ALTA{border-left-color:#E5484D;}
.kcard.prio-MEDIA{border-left-color:#F5A524;}
.kcard.prio-BAIXA{border-left-color:#30A46C;}
.kc-top{display:flex;justify-content:space-between;font-size:.72rem;color:var(--suave);font-weight:600;}
.kc-title{font-size:1.05rem;font-weight:800;color:var(--navy);margin:2px 0;}
.kc-route{font-size:.82rem;color:#334155;margin-bottom:6px;}
.kc-chips{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px;}
.chip{background:#EEF3F9;border-radius:20px;padding:1px 8px;font-size:.72rem;color:#334155;}
.chip-red{background:#FDECEC;color:#B42318;font-weight:700;}
.chip-ia{background:#EDE9FE;color:#5B21B6;font-weight:600;}
.kc-foot{font-size:.75rem;color:var(--suave);}
.kc-foot .warn{color:#B42318;font-weight:700;}

/* login */
.login-hero{text-align:center;margin:3vh 0 1.2rem;}
.login-hero .logo{font-size:3rem;}
.login-hero h1{margin:.2rem 0;font-size:2.4rem;color:var(--navy);}
.login-hero p{color:var(--suave);}
</style>
"""


def aplicar():
    st.markdown(CSS, unsafe_allow_html=True)


def cabecalho(titulo, subtitulo="", icone=""):
    st.markdown(
        f'<div class="hub-head"><h1>{icone} {titulo}</h1><p>{subtitulo}</p></div>',
        unsafe_allow_html=True,
    )
