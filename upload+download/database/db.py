import os
import psycopg2
from psycopg2.extras import RealDictCursor


def get_db_connection():
    """Abre conexão com o Postgres usando a DATABASE_URL (variável de ambiente)."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL não definida")
    # RealDictCursor faz as linhas virarem dict (equivalente ao sqlite3.Row)
    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def init_db():
    """Cria a tabela uploads se ela ainda não existir."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS uploads (
                    id SERIAL PRIMARY KEY,
                    filename TEXT UNIQUE NOT NULL,
                    filepath TEXT NOT NULL
                )
            ''')
        conn.commit()
    finally:
        conn.close()