import bcrypt

from core.db import consultar, executar


def registrar_log(usuario_id, acao, detalhe=""):
    executar(
        "INSERT INTO log_auditoria (usuario_id, acao, detalhe) VALUES (%s,%s,%s)",
        (usuario_id, acao, detalhe),
    )


def criar_usuario(nome, email, senha, perfil="operador", autor_id=None):
    if len(senha) < 6:
        raise ValueError("A senha deve ter ao menos 6 caracteres.")
    senha_hash = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()
    uid = executar(
        "INSERT INTO usuarios (nome, email, senha_hash, perfil) VALUES (%s,%s,%s,%s)",
        (nome.strip(), email.strip().lower(), senha_hash, perfil),
    )
    registrar_log(autor_id, "CRIAR_USUARIO", f"{email} ({perfil})")
    return uid


def autenticar(email, senha):
    """Retorna dict do usuário se OK, senão None. Sempre registra no log."""
    email = email.strip().lower()
    rows = consultar(
        "SELECT id, nome, email, senha_hash, perfil FROM usuarios WHERE email=%s AND ativo=1",
        (email,),
    )
    if rows and bcrypt.checkpw(senha.encode(), rows[0]["senha_hash"].encode()):
        registrar_log(rows[0]["id"], "LOGIN_OK", email)
        return {k: rows[0][k] for k in ("id", "nome", "email", "perfil")}
    registrar_log(rows[0]["id"] if rows else None, "LOGIN_FALHA", email)
    return None


def alterar_status(usuario_id, ativo, autor_id):
    executar("UPDATE usuarios SET ativo=%s WHERE id=%s", (1 if ativo else 0, usuario_id))
    registrar_log(autor_id, "ALTERAR_STATUS_USUARIO", f"id={usuario_id} ativo={ativo}")
