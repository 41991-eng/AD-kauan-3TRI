from psycopg2 import errors
from database.db import get_db_connection


class UploadModel:

    @staticmethod
    def save_file(filename, filepath):
        """Registra o arquivo no banco. filepath = chave do objeto no storage (ex: uploads/<uuid>_foto.png)."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO uploads (filename, filepath) VALUES (%s, %s)",
                    (filename, filepath),
                )
            conn.commit()
            return True
        except errors.UniqueViolation:
            conn.rollback()
            return None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def find_by_filename(filename):
        """Busca um arquivo pelo nome. Retorna dict ou None."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, filename, filepath FROM uploads WHERE filename = %s",
                    (filename,),
                )
                return cur.fetchone()
        finally:
            conn.close()