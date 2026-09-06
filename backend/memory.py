import os
import psycopg2


def get_db_connection():
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    return psycopg2.connect(database_url)


def init_memory_table():
    conn = get_db_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    username TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (username, key)
                )
            """)

        conn.commit()

    finally:
        conn.close()


def load_memory(username):
    if not username:
        return {}

    init_memory_table()

    conn = get_db_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT key, value
                FROM memories
                WHERE username = %s
                """,
                (username,)
            )

            rows = cursor.fetchall()

            return {
                key: value
                for key, value in rows
            }

    finally:
        conn.close()


def update_memory(key, value, username):
    if not username:
        return

    value = str(value).strip()

    if not value:
        return

    init_memory_table()

    conn = get_db_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO memories (username, key, value)
                VALUES (%s, %s, %s)
                ON CONFLICT (username, key)
                DO UPDATE SET value = EXCLUDED.value
                """,
                (username, key, value)
            )

        conn.commit()

    finally:
        conn.close()