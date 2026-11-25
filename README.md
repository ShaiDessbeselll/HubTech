
🚚 HUBTECH – Sistema de Integração e Gestão de Dados

Protótipo desenvolvido para a Rodomax Transportes na disciplina de Data Science e Inteligência Artificial (Tecnologia em Análise e Desenvolvimento de Sistemas – Univel, 4º período).

O HUBTECH recebe demandas de frete de várias fontes (planilhas, PDF, JSON, mensagens de WhatsApp e e-mail), extrai, valida, padroniza e remove duplicidades, gravando tudo em uma base MySQL única, com login e rastreabilidade de quem importou cada registro.

✨ Funcionalidades
Login com senha protegida por hash (bcrypt) e perfis admin / operador
Tela Importar dados (IA): cole uma mensagem de WhatsApp/e-mail ou envie um arquivo (xlsx, csv, json, pdf, txt); a IA extrai produto, origem, destino, peso, prazo e frete, você confere/edita e salva
Extração por PLN (regras linguísticas + spaCy opcional), comparada com o sistema antigo (regex)
Frete sugerido pela IA a partir do histórico real de demandas da mesma rota (só quando há base suficiente)
Validação, padronização (peso em toneladas, valores em R$, datas) e detecção de duplicados
Registros rejeitados guardados com o motivo
CRM de demandas: funil de status (Nova → Em análise → Aguardando motorista → Em transporte → Entregue/Cancelada), quadro estilo Kanban, prioridade automática por prazo, responsável e histórico de cada demanda
Painel com indicadores e gráficos, base de demandas com busca e exportação em CSV
Histórico de importações e log de auditoria (login, importação, análises, gestão de usuários)
Ponto de integração para o módulo de IA (ia/modulo.py)
Administração (perfil admin): gestão de usuários e log de auditoria
🗂️ Estrutura
hubtech/
├── app.py                 # ponto de entrada (Streamlit)
├── core/                  # regras de negócio
│   ├── db.py              #   conexão MySQL e consultas parametrizadas
│   ├── auth.py            #   usuários, login (bcrypt) e auditoria
│   ├── crm.py             #   funil, prioridade, responsável e histórico
│   └── importador.py      #   leitura, validação, padronização, deduplicação
├── ia/                    # inteligência artificial
│   ├── extrator.py        #   extração de campos de mensagens livres (PLN)
│   ├── leitor_arquivo.py  #   leitura de arquivos pela IA (xlsx, csv, json, pdf, txt)
│   ├── frete.py           #   estimativa de frete pelo histórico real
│   └── modulo.py          #   ponto de integração: prever() e estimar_frete()
├── ui/                    # interface
│   ├── estilo.py          #   tema e CSS
│   ├── paginas.py         #   painel, CRM, demandas, usuários, auditoria
│   ├── pagina_mensagem.py #   tela Importar dados (IA)
│   └── pagina_historico.py#   histórico, rejeitados e duplicados
├── database/schema.sql    # criação do banco e tabelas
├── scripts/               # instalar.py, criar_admin.py, migrar_crm.py, avaliar_extracao.py, avaliar_frete.py
├── data/                  # arquivos de exemplo para testes
├── tests/                 # testes automatizados
└── .streamlit/config.toml # tema visual
🚀 Como rodar

Pré-requisitos: Python 3.10+ e MySQL Server em execução.

bash
python -m venv .venv
.venv\Scripts\activate            # Linux/Mac: source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/instalar.py        # testa o MySQL, cria banco/tabelas, grava o .env e cria o admin
python -m streamlit run app.py

Abra http://localhost:8501 e entre com o usuário criado no instalador. Para testar, use os arquivos de data/ na tela Importar dados (IA) (aba Arquivo; as mensagens de exemplo ficam na aba Mensagem).

⚠️ O arquivo .env contém a senha do banco e não deve ser enviado ao GitHub (já está no .gitignore). Use .env.example como modelo.

🗂️ CRM de demandas

Toda demanda que passa na validação e não é duplicada entra automaticamente no CRM: status Nova, prioridade calculada pelo prazo (até 2 dias ou vencido = alta, até 7 = média, acima = baixa), responsável = quem importou e a primeira linha do histórico. Depois, o time move a demanda pelo funil na tela CRM, troca responsável/prioridade e registra anotações; tudo fica no histórico e no log de auditoria. A tela tem três abas: Quadro (cartões coloridos por prioridade, com tempo parado na etapa), Planilha (edição em lote de status, responsável e prioridade) e Meu dia (minhas demandas atrasadas, que vencem hoje ou paradas há 3+ dias). Ao abrir um cartão, uma janela mostra os detalhes (incluindo o frete sugerido pela IA, quando houver), permite alterar status, responsável e prioridade, e mostra o histórico. Regras: o funil não permite pular etapas e cancelar exige motivo. O status final (Entregue/Cancelada) serve de rótulo para a trilha de classificação da IA.

Banco já existente (criado antes do CRM)? Rode python scripts/migrar_crm.py (não apaga dados).

🧪 Testes
bash
python -m pip install pytest
python -m pytest
🤖 IA

A tela Importar dados (IA) usa ia/extrator.py (mensagens) e ia/leitor_arquivo.py (arquivos). Quando a demanda chega sem frete, ia/frete.py sugere um valor a partir da mediana do R$/t de pelo menos 3 demandas reais da mesma rota (e do mesmo produto, quando possível); sem base suficiente, não estima. O spaCy é opcional (python -m pip install spacy e python -m spacy download pt_core_news_sm). Para medir a qualidade: python scripts/avaliar_extracao.py --metodo todos (não precisa de banco) e python scripts/avaliar_frete.py --csv <arquivo>.

Integração

O ponto de integração com o sistema é ia/modulo.py, que tem duas funções:

python
def prever(demanda: dict) -> dict          # {"resultado", "detalhe", "frete_estimado" (opcional)}
def estimar_frete(demanda: dict) -> float  # chamada na importação quando o frete veio vazio

O frete estimado vai para a coluna própria frete_estimado (aparece no cartão do CRM como "💡 ~R$ ... (IA)") e nunca sobrescreve o frete real informado. Os dados estão na tabela demandas (from core.db import consultar).

📋 Requisitos atendidos
ID	Requisito	Onde
RF01	Receber dados de diferentes fontes	core/importador.py, tela Importar dados (IA)
RF02	Extrair e identificar informações	_ler_pdf, _ler_texto, ia/extrator.py
RF03	Validar dados	validar() + tabela registros_rejeitados
RF04	Limpar e padronizar	padronizar()
RF05	Identificar duplicidades	hash_registro único em demandas
RF06	Base unificada	MySQL (database/schema.sql)
RNF03	Segurança	bcrypt, consultas parametrizadas, perfis, auditoria
👥 Equipe

Ananda dos Santos · Ewerton Gustavo · Matheus Fonseca · Shaiane Dessbesell Professor: Lucas Soares da Silva

📚 Referências

Python 3 Documentation · pandas Documentation · Streamlit Documentation · IBM e Oracle (What is Data Integration?)
=======
# HubTech
Protótipo desenvolvido para a Rodomax Transportes na disciplina de Data Science e Inteligência Artificial (Tecnologia em Análise e Desenvolvimento de Sistemas – Univel, 4º período).

✨ O que o sistema faz
🧠 Ler mensagem (IA): cola uma mensagem ("Preciso levar 20 t de milho de Toledo para Maringá até sexta, uns 6 mil") ou envia um arquivo (xlsx, csv, json, pdf, txt) e a IA extrai produto, origem, destino, peso, prazo e frete. A tela compara o que o sistema antigo (regex) entendeu com o que a IA entendeu, e a pessoa confere e corrige antes de salvar.
💡 Sugestão de frete: quando a demanda chega sem frete, a IA sugere um valor com base no histórico real da mesma rota. Sem base suficiente, ela não estima, e a sugestão nunca substitui o frete informado.
🗂️ CRM de demandas: funil de status (Nova → Em análise → Aguardando motorista → Em transporte → Entregue/ Cancelada), quadro Kanban, prioridade automática por prazo, responsável e histórico.
🕘 Histórico: importações realizadas e a lista de registros rejeitados e duplicados, com o motivo.
Painel com indicadores, base de demandas com busca e exportação, login (bcrypt), perfis admin/operador e log de auditoria.
e5aecb8912449487269c1ebe133df15ac0655433
