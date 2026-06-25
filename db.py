import sqlite3
import os
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL")
IS_POSTGRES = DATABASE_URL is not None and (DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "user_data.db")

# Ensure the data directory exists
if not IS_POSTGRES:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def get_db_connection():
    if IS_POSTGRES:
        import psycopg2
        import psycopg2.extras
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(url)
        return conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def get_cursor(conn):
    if IS_POSTGRES:
        import psycopg2.extras
        return conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    else:
        return conn.cursor()

def execute_sql(cursor, sql, params=()):
    if IS_POSTGRES:
        # Convert ? parameters to %s for PostgreSQL
        sql = sql.replace("?", "%s")
        # Convert SQLite autoincrement to PostgreSQL serial
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        
        # Convert INSERT OR REPLACE specifically
        if "INSERT OR REPLACE INTO match_votes" in sql:
            sql = """
            INSERT INTO match_votes (match_key, user_id, vote, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (match_key, user_id) 
            DO UPDATE SET vote = EXCLUDED.vote, created_at = EXCLUDED.created_at
            """
            
        # Convert UPSERT syntax for points addition
        if "ON CONFLICT(user_id) DO UPDATE SET" in sql:
            if "points = points + %s" in sql or "points = points + ?" in sql:
                sql = """
                INSERT INTO leaderboard (user_id, username, points)
                VALUES (%s, %s, %s)
                ON CONFLICT(user_id) DO UPDATE SET 
                    points = leaderboard.points + EXCLUDED.points,
                    username = EXCLUDED.username
                """
    cursor.execute(sql, params)
    return cursor

def init_db():
    conn = get_db_connection()
    cursor = get_cursor(conn)
    
    # 1. Favorites Table
    execute_sql(cursor, """
    CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        team_a TEXT NOT NULL,
        team_b TEXT NOT NULL,
        xg_a REAL,
        xg_b REAL,
        prob_a REAL,
        prob_draw REAL,
        prob_b REAL,
        notes TEXT,
        created_at TEXT NOT NULL
    )
    """)
    
    # 2. User Presets Table
    execute_sql(cursor, """
    CREATE TABLE IF NOT EXISTS user_presets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        preset_name TEXT NOT NULL,
        fifa_weight REAL NOT NULL,
        h2h_weight REAL NOT NULL,
        decay REAL NOT NULL,
        override_a REAL NOT NULL,
        override_b REAL NOT NULL,
        altitude INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    
    # 3. Match Votes Table (Community Pre-match polls)
    execute_sql(cursor, """
    CREATE TABLE IF NOT EXISTS match_votes (
        match_key TEXT NOT NULL,
        user_id TEXT NOT NULL,
        vote TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (match_key, user_id)
    )
    """)
    
    # 4. User Pronostics Table (For Leaderboard guesses)
    execute_sql(cursor, """
    CREATE TABLE IF NOT EXISTS user_pronostics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        username TEXT NOT NULL,
        team_a TEXT NOT NULL,
        team_b TEXT NOT NULL,
        match_key TEXT NOT NULL,
        guess TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        is_correct INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """)
    
    # 5. Leaderboard Table
    execute_sql(cursor, """
    CREATE TABLE IF NOT EXISTS leaderboard (
        user_id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        points INTEGER DEFAULT 0
    )
    """)
    
    conn.commit()
    conn.close()

def get_match_key(team_a: str, team_b: str) -> str:
    sorted_teams = sorted([team_a.strip().lower(), team_b.strip().lower()])
    return f"{sorted_teams[0]}_vs_{sorted_teams[1]}"

# ==========================================
# FAVORITES CRUD
# ==========================================
def add_favorite(user_id: str, team_a: str, team_b: str, xg_a: float, xg_b: float, prob_a: float, prob_draw: float, prob_b: float, notes: str):
    conn = get_db_connection()
    cursor = get_cursor(conn)
    created_at = datetime.now().isoformat()
    
    sql = """
    INSERT INTO favorites (user_id, team_a, team_b, xg_a, xg_b, prob_a, prob_draw, prob_b, notes, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    if IS_POSTGRES:
        sql = sql.replace("?", "%s") + " RETURNING id"
        cursor.execute(sql, (user_id, team_a, team_b, xg_a, xg_b, prob_a, prob_draw, prob_b, notes, created_at))
        fav_id = cursor.fetchone()[0]
    else:
        cursor.execute(sql, (user_id, team_a, team_b, xg_a, xg_b, prob_a, prob_draw, prob_b, notes, created_at))
        fav_id = cursor.lastrowid
        
    conn.commit()
    conn.close()
    return fav_id

def get_user_favorites(user_id: str):
    conn = get_db_connection()
    cursor = get_cursor(conn)
    execute_sql(cursor, "SELECT * FROM favorites WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_favorite(user_id: str, favorite_id: int) -> bool:
    conn = get_db_connection()
    cursor = get_cursor(conn)
    execute_sql(cursor, "DELETE FROM favorites WHERE user_id = ? AND id = ?", (user_id, favorite_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

# ==========================================
# CUSTOM PRESETS CRUD
# ==========================================
def add_user_preset(user_id: str, preset_name: str, fifa_weight: float, h2h_weight: float, decay: float, override_a: float, override_b: float, altitude: int):
    conn = get_db_connection()
    cursor = get_cursor(conn)
    created_at = datetime.now().isoformat()
    
    sql = """
    INSERT INTO user_presets (user_id, preset_name, fifa_weight, h2h_weight, decay, override_a, override_b, altitude, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    if IS_POSTGRES:
        sql = sql.replace("?", "%s") + " RETURNING id"
        cursor.execute(sql, (user_id, preset_name, fifa_weight, h2h_weight, decay, override_a, override_b, altitude, created_at))
        preset_id = cursor.fetchone()[0]
    else:
        cursor.execute(sql, (user_id, preset_name, fifa_weight, h2h_weight, decay, override_a, override_b, altitude, created_at))
        preset_id = cursor.lastrowid
        
    conn.commit()
    conn.close()
    return preset_id

def get_user_presets(user_id: str):
    conn = get_db_connection()
    cursor = get_cursor(conn)
    execute_sql(cursor, "SELECT * FROM user_presets WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_user_preset(user_id: str, preset_id: int) -> bool:
    conn = get_db_connection()
    cursor = get_cursor(conn)
    execute_sql(cursor, "DELETE FROM user_presets WHERE user_id = ? AND id = ?", (user_id, preset_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

# ==========================================
# MATCH POLL VOTES
# ==========================================
def cast_vote(match_key: str, user_id: str, vote: str) -> bool:
    conn = get_db_connection()
    cursor = get_cursor(conn)
    created_at = datetime.now().isoformat()
    try:
        execute_sql(cursor, """
        INSERT OR REPLACE INTO match_votes (match_key, user_id, vote, created_at)
        VALUES (?, ?, ?, ?)
        """, (match_key, user_id, vote, created_at))
        conn.commit()
        success = True
    except Exception as e:
        print("Error voting:", e)
        success = False
    finally:
        conn.close()
    return success

def get_match_votes_stats(match_key: str):
    conn = get_db_connection()
    cursor = get_cursor(conn)
    execute_sql(cursor, """
    SELECT vote, COUNT(*) as cnt 
    FROM match_votes 
    WHERE match_key = ? 
    GROUP BY vote
    """, (match_key,))
    rows = cursor.fetchall()
    conn.close()
    
    stats = {"A": 0, "Draw": 0, "B": 0}
    total = 0
    for r in rows:
        stats[r["vote"]] = r["cnt"]
        total += r["cnt"]
        
    percentages = {"A": 0, "Draw": 0, "B": 0}
    if total > 0:
        percentages["A"] = round((stats["A"] / total) * 100)
        percentages["Draw"] = round((stats["Draw"] / total) * 100)
        percentages["B"] = round((stats["B"] / total) * 100)
        
    return {
        "votes": stats,
        "percentages": percentages,
        "total": total
    }

def get_user_vote_for_match(match_key: str, user_id: str):
    conn = get_db_connection()
    cursor = get_cursor(conn)
    execute_sql(cursor, "SELECT vote FROM match_votes WHERE match_key = ? AND user_id = ?", (match_key, user_id))
    row = cursor.fetchone()
    conn.close()
    return row["vote"] if row else None

# ==========================================
# OFFICIAL PRONOSTICS & LEADERBOARD
# ==========================================
def register_official_pronostic(user_id: str, username: str, team_a: str, team_b: str, guess: str) -> bool:
    match_key = get_match_key(team_a, team_b)
    conn = get_db_connection()
    cursor = get_cursor(conn)
    created_at = datetime.now().isoformat()
    
    execute_sql(cursor, """
    SELECT id FROM user_pronostics 
    WHERE user_id = ? AND match_key = ? AND status = 'pending'
    """, (user_id, match_key))
    existing = cursor.fetchone()
    
    if existing:
        conn.close()
        return False
        
    try:
        execute_sql(cursor, """
        INSERT INTO user_pronostics (user_id, username, team_a, team_b, match_key, guess, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, team_a, team_b, match_key, guess, created_at))
        conn.commit()
        success = True
    except Exception as e:
        print("Error registering pronostic:", e)
        success = False
    finally:
        conn.close()
    return success

def get_user_match_pronostic(user_id: str, team_a: str, team_b: str):
    match_key = get_match_key(team_a, team_b)
    conn = get_db_connection()
    cursor = get_cursor(conn)
    execute_sql(cursor, """
    SELECT guess, status, is_correct FROM user_pronostics 
    WHERE user_id = ? AND match_key = ?
    ORDER BY id DESC LIMIT 1
    """, (user_id, match_key))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_leaderboard_rankings():
    conn = get_db_connection()
    cursor = get_cursor(conn)
    execute_sql(cursor, "SELECT * FROM leaderboard ORDER BY points DESC, username ASC LIMIT 100")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def resolve_user_pronostics(team_a: str, team_b: str, actual_outcome: str):
    match_key = get_match_key(team_a, team_b)
    conn = get_db_connection()
    cursor = get_cursor(conn)
    
    execute_sql(cursor, """
    SELECT id, user_id, username, guess FROM user_pronostics 
    WHERE match_key = ? AND status = 'pending'
    """, (match_key,))
    pronostics = cursor.fetchall()
    
    for p in pronostics:
        p_id = p["id"]
        user_id = p["user_id"]
        username = p["username"]
        guess = p["guess"]
        
        is_correct = 1 if guess == actual_outcome else 0
        points_to_add = 10 if is_correct == 1 else 0
        
        execute_sql(cursor, """
        UPDATE user_pronostics 
        SET status = 'completed', is_correct = ? 
        WHERE id = ?
        """, (is_correct, p_id))
        
        if points_to_add > 0:
            execute_sql(cursor, """
            INSERT INTO leaderboard (user_id, username, points)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
                points = points + ?,
                username = EXCLUDED.username
            """, (user_id, username, points_to_add, points_to_add))
        else:
            execute_sql(cursor, """
            INSERT INTO leaderboard (user_id, username, points)
            VALUES (?, ?, 0)
            ON CONFLICT(user_id) DO NOTHING
            """, (user_id, username))
            
    conn.commit()
    conn.close()

# Initialize tables
init_db()
