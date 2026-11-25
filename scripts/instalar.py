"""Instalador do HUBTECH: testa o MySQL, grava o .env, cria o banco/tabelas e o admin.
Rode (na raiz do projeto):  python scripts/instalar.py
"""
from pathlib import Path

import bcrypt
import mysql.connector
from mysql.connector import errors

PASTA = Path(__file__).resolve().parent.parent


def pedir(msg, padrao=""):
    r = input(f"{msg} [{padrao}]: ").strip() if padrao else input(f"{msg}: ").strip()
    return r or padrao


print("=== INSTALADOR HUBTECH ===\n")
print("Informe os dados do seu MySQL (os mesmos que você usa no Workbench).")
print("Para aceitar o valor entre [colchetes], apenas aperte Enter.\n")

while True:
    host = pedir("Host", "localhost")
    try:
        porta = int(pedir("Porta", "3306"))
    except ValueError:
        print("\n[ERRO] A porta deve ser um número (normalmente 3306).\n")
        continue
    usuario = pedir("Usuário do MySQL", "root")
    senha = pedir("Senha do MySQL (aparece na tela)")
    try:
        conn = mysql.connector.connect(host=host, port=porta, user=usuario, password=senha)
        print("\n[OK] Conectado ao MySQL.\n")
        break
    except errors.ProgrammingError as e:
        if e.errno == 1045:
            print("\n[ERRO] Usuário ou senha incorretos. Tente de novo "
                  "(use a senha que abre sua conexão no Workbench).\n")
        else:
            print(f"\n[ERRO] {e}\n")
    except errors.InterfaceError as e:
        print(f"\n[ERRO] Não consegui falar com o MySQL em {host}:{porta}. "
              f"Verifique se o serviço MySQL está iniciado.\n{e}\n")
    except Exception as e:
        print(f"\n[ERRO] {e}\n")

recriar = pedir("Apagar e recriar o banco 'hubtech' do zero? (s/n)", "s").lower() == "s"

cur = conn.cursor()
if recriar:
    cur.execute("DROP DATABASE IF EXISTS hubtech")

sql = (PASTA / "database" / "schema.sql").read_text(encoding="utf-8")
linhas = [l for l in sql.splitlines() if not l.strip().startswith("--")]
sql = "\n".join(l.split("-- ")[0] for l in linhas)  # remove comentários no fim da linha
for comando in [c.strip() for c in sql.split(";") if c.strip()]:
    cur.execute(comando)
conn.commit()
print("[OK] Banco e tabelas criados.\n")

# grava o .env (assim você não precisa editar nada à mão)
(PASTA / ".env").write_text(
    f"DB_HOST={host}\nDB_PORT={porta}\nDB_USER={usuario}\n"
    f"DB_PASSWORD={senha}\nDB_NAME=hubtech\n", encoding="utf-8")
print("[OK] Arquivo .env gravado.\n")

# cria o admin
print("Agora crie o usuário administrador do sistema:")
while True:
    nome = pedir("Nome")
    email = pedir("E-mail").lower()
    senha_admin = pedir("Senha do sistema (mín. 6 caracteres)")
    if nome and email and len(senha_admin) >= 6:
        break
    print("[ERRO] Preencha tudo e use senha com 6+ caracteres.\n")

cur.execute("USE hubtech")
h = bcrypt.hashpw(senha_admin.encode(), bcrypt.gensalt()).decode()
cur.execute("INSERT INTO usuarios (nome,email,senha_hash,perfil) VALUES (%s,%s,%s,'admin')",
            (nome, email, h))
conn.commit()
conn.close()

print("\n=== PRONTO! ===")
print(f"Login do sistema -> e-mail: {email}  senha: {senha_admin}")
print("Agora rode:  python -m streamlit run app.py")
