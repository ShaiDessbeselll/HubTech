"""Cria um usuário admin. Rode na raiz do projeto: python scripts/criar_admin.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.auth import criar_usuario  # noqa: E402

nome = input("Nome: ")
email = input("E-mail: ")
senha = input("Senha (min. 6 caracteres): ")
criar_usuario(nome, email, senha, perfil="admin")
print("Admin criado com sucesso.")
