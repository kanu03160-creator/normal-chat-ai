import os
import json
import psycopg2


# ==========================================
# DATABASE CONNECTION
# ==========================================

def get_db_connection():

    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    return psycopg2.connect(database_url)


# ==========================================
# CREATE TABLE
# ==========================================

def init_history_table():

    conn = get_db_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id SERIAL PRIMARY KEY,
                    username TEXT NOT NULL,
                    title TEXT NOT NULL,
                    messages JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        conn.commit()

    finally:

        conn.close()


# ==========================================
# LOAD HISTORY
# ==========================================

def load_history(username):

    if not username:
        return []

    init_history_table()

    conn = get_db_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute("""
                SELECT id, title, messages
                FROM chat_history
                WHERE username = %s
                ORDER BY id ASC
            """, (username,))

            rows = cursor.fetchall()

            history = []

            for row in rows:

                history.append({
                    "title": row[1],
                    "messages": row[2]
                })

            return history

    finally:

        conn.close()


# ==========================================
# ADD CHAT
# ==========================================

def add_chat(messages, username, title=None):

    if not messages or not username:
        return

    init_history_table()

    if title is None:

        title = "New Chat"

        for message in messages:

            if message.get("role") == "user":

                title = message.get(
                    "content",
                    "New Chat"
                )

                break

        title = str(title)[:40]

    conn = get_db_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute("""
                INSERT INTO chat_history
                (username, title, messages)
                VALUES (%s, %s, %s)
            """, (
                username,
                title,
                json.dumps(
                    messages,
                    ensure_ascii=False
                )
            ))

        conn.commit()

    finally:

        conn.close()


# ==========================================
# DELETE CHAT
# ==========================================

def delete_chat(index, username):

    if not username:
        return False

    history = load_history(username)

    if index < 0 or index >= len(history):
        return False

    init_history_table()

    conn = get_db_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute("""
                SELECT id
                FROM chat_history
                WHERE username = %s
                ORDER BY id ASC
                OFFSET %s
                LIMIT 1
            """, (
                username,
                index
            ))

            row = cursor.fetchone()

            if not row:
                return False

            chat_id = row[0]

            cursor.execute("""
                DELETE FROM chat_history
                WHERE id = %s
                AND username = %s
            """, (
                chat_id,
                username
            ))

        conn.commit()

        return True

    finally:

        conn.close()


# ==========================================
# RENAME CHAT
# ==========================================

def rename_chat(index, title, username):

    if not username:
        return False

    title = str(title).strip()

    if not title:
        return False

    title = title[:40]

    init_history_table()

    conn = get_db_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute("""
                SELECT id
                FROM chat_history
                WHERE username = %s
                ORDER BY id ASC
                OFFSET %s
                LIMIT 1
            """, (
                username,
                index
            ))

            row = cursor.fetchone()

            if not row:
                return False

            chat_id = row[0]

            cursor.execute("""
                UPDATE chat_history
                SET title = %s
                WHERE id = %s
                AND username = %s
            """, (
                title,
                chat_id,
                username
            ))

        conn.commit()

        return True

    finally:

        conn.close()