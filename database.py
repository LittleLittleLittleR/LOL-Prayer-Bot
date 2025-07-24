# database.py
import sqlite3
from collections import defaultdict
from state import PrayerRequest

def get_connection():
    conn = sqlite3.connect("prayerbot.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Prayer_Requests (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                username TEXT,
                text TEXT,
                is_anonymous BOOLEAN
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Group_Membership (
                user_id INTEGER,
                group_id INTEGER,
                PRIMARY KEY (user_id, group_id)
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS Group_Metadata (
                group_id INTEGER PRIMARY KEY,
                group_title TEXT
            )
        ''')

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Joined_Users (
                request_id TEXT,
                user_id INTEGER,
                PRIMARY KEY (request_id, user_id),
                FOREIGN KEY (request_id) REFERENCES Prayer_Requests(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Prayed_Users (
                request_id TEXT,
                user_id INTEGER,
                PRIMARY KEY (request_id, user_id),
                FOREIGN KEY (request_id) REFERENCES Prayer_Requests(id)
            )
        """)

        conn.commit()


# Prayer_Requests functions
def insert_prayer_request(req: PrayerRequest):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO Prayer_Requests (id, text, user_id, username, is_anonymous)
            VALUES (?, ?, ?, ?, ?)
        """, (req.id, req.text, req.user_id, req.username, int(req.is_anonymous)))
        conn.commit()

def get_user_requests(user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, text FROM Prayer_Requests WHERE user_id = ?", (user_id,))
        return cursor.fetchall()

def get_request_by_id(req_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, username, text, is_anonymous
            FROM Prayer_Requests
            WHERE id = ?
        """, (req_id,))
        row = cursor.fetchone()
        if row:
            return PrayerRequest(
                id=row[0],
                user_id=row[1],
                username=row[2],
                text=row[3],
                is_anonymous=bool(row[4]),
            )
        return None

def delete_request_by_id(req_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Prayer_Requests WHERE id = ?", (req_id,))
        conn.commit()

def get_all_prayer_requests() -> list[PrayerRequest]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM Prayer_Requests").fetchall()
        return [
            PrayerRequest(
                id=row['id'],
                user_id=row['user_id'],
                username=row['username'],
                text=row['text'],
                is_anonymous=bool(row['is_anonymous']),
            ) for row in rows
        ]


# Group_Membership functions
def save_user_group_membership(user_id: int, group_id: int):
    with get_connection() as conn:
        conn.execute(
            'INSERT OR IGNORE INTO Group_Membership (user_id, group_id) VALUES (?, ?)',
            (user_id, group_id)
        )

def get_user_groups(user_id: int) -> set[int]:
    with get_connection() as conn:
        cursor = conn.execute(
            'SELECT group_id FROM Group_Membership WHERE user_id = ?', (user_id,)
        )
        return {row[0] for row in cursor.fetchall()}

def get_group_users(group_id: int) -> set[int]:
    with get_connection() as conn:
        cursor = conn.execute(
            'SELECT user_id FROM Group_Membership WHERE group_id = ?', (group_id,)
        )
        return {row[0] for row in cursor.fetchall()}


# Group_Metadata functions
def save_group_title(group_id: int, title: str):
    with get_connection() as conn:
        conn.execute('''
            INSERT INTO Group_Metadata (group_id, group_title)
            VALUES (?, ?)
            ON CONFLICT(group_id) DO UPDATE SET group_title=excluded.group_title
        ''', (group_id, title))

def get_group_title(group_id: int) -> str:
    with get_connection() as conn:
        cursor = conn.execute('SELECT group_title FROM Group_Metadata WHERE group_id = ?', (group_id,))
        row = cursor.fetchone()
        return row[0] if row else f"Group {group_id}"


# Prayed_Users functions
def mark_prayed(user_id: int, req_id: str):
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO Prayed_Users (user_id, request_id) VALUES (?, ?)", (user_id, req_id))
        conn.commit()

def get_all_prayed_users() -> dict[int, set[int]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT request_id, user_id FROM Prayed_Users")
        prayed_map = defaultdict(set)
        for req_id, user_id in cursor.fetchall():
            prayed_map[req_id].add(user_id)
        return prayed_map

# Joined_Users functions
def mark_joined(user_id: int, req_id: str):
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO Joined_Users (user_id, request_id) VALUES (?, ?)", (user_id, req_id))
        conn.commit()

def unmark_joined(user_id: int, req_id: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM Joined_Users WHERE user_id = ? AND request_id = ?", (user_id, req_id))
        conn.commit()

def get_joined_users(req_id: str) -> set[int]:
    with get_connection() as conn:
        rows = conn.execute("SELECT user_id FROM Joined_Users WHERE request_id = ?", (req_id,)).fetchall()
        return {row[0] for row in rows}