from database.db import get_db_connection


class DownloadModel:

    @staticmethod
    def find_by_filename(filename):
        """Retorna dict com id, filename e filepath, ou None se não achar."""
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