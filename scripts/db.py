import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    # Projekt jest polski - kalendarz (podzial na dni) ma odpowiadac
    # polskiemu czasowi lokalnemu, nie UTC.
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'Europe/Warsaw'")
    conn.commit()
    return conn
