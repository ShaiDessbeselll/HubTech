import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

# lê o .env da raiz do projeto, independente da pasta onde o terminal está
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)


def get_conn():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "hubtech"),
    )


def consultar(sql, params=None):
    """SELECT parametrizado -> lista de dicts."""
    conn = get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        return cur.fetchall()
    finally:
        conn.close()


def executar(sql, params=None):
    """INSERT/UPDATE/DELETE parametrizado -> id gerado."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()
