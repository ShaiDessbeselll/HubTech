"""Atualiza um banco JÁ EXISTENTE para o CRM, sem apagar dados.
Rode na raiz do projeto:  python scripts/migrar_crm.py
(pode rodar mais de uma vez, ele só faz o que falta)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.crm import calcular_prioridade  # noqa: E402
from core.db import get_conn  # noqa: E402

COLUNAS = {
    "status": "ALTER TABLE demandas ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'NOVA'",
    "prioridade": "ALTER TABLE demandas ADD COLUMN prioridade VARCHAR(10) NOT NULL DEFAULT 'MEDIA'",
    "responsavel_id": "ALTER TABLE demandas ADD COLUMN responsavel_id INT NULL",
    "frete_estimado": "ALTER TABLE demandas ADD COLUMN frete_estimado DECIMAL(12,2) NULL",
    "atualizado_em": ("ALTER TABLE demandas ADD COLUMN atualizado_em DATETIME "
                      "DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
}

TABELA_HISTORICO = """
CREATE TABLE IF NOT EXISTS demanda_historico (
  id INT AUTO_INCREMENT PRIMARY KEY,
  demanda_id INT NOT NULL,
  usuario_id INT NULL,
  tipo VARCHAR(20) NOT NULL,
  de_valor VARCHAR(100),
  para_valor VARCHAR(100),
  texto TEXT,
  data_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (demanda_id) REFERENCES demandas(id)
)"""


def tem_coluna(cur, coluna):
    cur.execute("SELECT COUNT(*) AS n FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME='demandas' AND COLUMN_NAME=%s", (coluna,))
    return cur.fetchone()["n"] > 0


conn = get_conn()
cur = conn.cursor(dictionary=True)
try:
    for coluna, ddl in COLUNAS.items():
        if tem_coluna(cur, coluna):
            print(f"[ok]   coluna demandas.{coluna} já existe")
        else:
            cur.execute(ddl)
            print(f"[novo] coluna demandas.{coluna} criada")
            if coluna == "responsavel_id":
                try:
                    cur.execute("ALTER TABLE demandas ADD CONSTRAINT fk_demandas_responsavel "
                                "FOREIGN KEY (responsavel_id) REFERENCES usuarios(id)")
                except Exception as e:
                    print(f"[aviso] FK não criada ({e}); segue funcionando sem ela")

    cur.execute(TABELA_HISTORICO)
    print("[ok]   tabela demanda_historico pronta")

    # demandas antigas: responsável = quem importou, prioridade pelo prazo, histórico inicial
    cur.execute(
        "SELECT d.id, d.prazo, i.id AS imp, i.usuario_id, i.origem, i.nome_arquivo "
        "FROM demandas d JOIN importacoes i ON i.id=d.importacao_id "
        "WHERE NOT EXISTS (SELECT 1 FROM demanda_historico h WHERE h.demanda_id=d.id)")
    antigas = cur.fetchall()
    for d in antigas:
        cur.execute("UPDATE demandas SET responsavel_id=COALESCE(responsavel_id,%s), prioridade=%s "
                    "WHERE id=%s", (d["usuario_id"], calcular_prioridade(d["prazo"]), d["id"]))
        cur.execute("INSERT INTO demanda_historico (demanda_id, usuario_id, tipo, para_valor, texto) "
                    "VALUES (%s,%s,'CRIACAO','Nova',%s)",
                    (d["id"], d["usuario_id"],
                     f"Criada pela importação #{d['imp']} ({d['origem']}, {d['nome_arquivo']}) "
                     f"- migrada para o CRM"))
    conn.commit()
    print(f"[ok]   {len(antigas)} demanda(s) antiga(s) incluída(s) no CRM")
    print("\nMigração concluída. Pode abrir o sistema.")
except Exception as e:
    conn.rollback()
    print(f"\n[ERRO] {e}")
    raise
finally:
    conn.close()
