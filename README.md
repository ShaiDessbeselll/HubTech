# HubTech
Protótipo desenvolvido para a Rodomax Transportes na disciplina de Data Science e Inteligência Artificial (Tecnologia em Análise e Desenvolvimento de Sistemas – Univel, 4º período).

✨ O que o sistema faz
🧠 Ler mensagem (IA): cola uma mensagem ("Preciso levar 20 t de milho de Toledo para Maringá até sexta, uns 6 mil") ou envia um arquivo (xlsx, csv, json, pdf, txt) e a IA extrai produto, origem, destino, peso, prazo e frete. A tela compara o que o sistema antigo (regex) entendeu com o que a IA entendeu, e a pessoa confere e corrige antes de salvar.
💡 Sugestão de frete: quando a demanda chega sem frete, a IA sugere um valor com base no histórico real da mesma rota. Sem base suficiente, ela não estima, e a sugestão nunca substitui o frete informado.
🗂️ CRM de demandas: funil de status (Nova → Em análise → Aguardando motorista → Em transporte → Entregue/ Cancelada), quadro Kanban, prioridade automática por prazo, responsável e histórico.
🕘 Histórico: importações realizadas e a lista de registros rejeitados e duplicados, com o motivo.
Painel com indicadores, base de demandas com busca e exportação, login (bcrypt), perfis admin/operador e log de auditoria.
