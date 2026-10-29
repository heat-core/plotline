import sqlite3
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = "plotline.db"

def get_db_path():
    # If DATA_DIR environment variable is set
    data_env = os.environ.get("DATA_DIR")
    if data_env:
        os.makedirs(data_env, exist_ok=True)
        return os.path.join(data_env, DB_NAME)

    # If root plotline.db exists, prioritize it (Desktop standalone mode)
    root_path = os.path.join(BASE_DIR, DB_NAME)
    if os.path.exists(root_path):
        return root_path

    # Docker or container volume mode
    data_dir = os.path.join(BASE_DIR, "data")
    if os.path.exists(data_dir):
        return os.path.join(data_dir, DB_NAME)

    return root_path

def init_db(db_path=None):
    if not db_path:
        db_path = get_db_path()
        
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    # Enable WAL mode
    con.execute('PRAGMA journal_mode = WAL;')
    cur = con.cursor()
    
    # 1. Shows
    cur.execute('''
    CREATE TABLE IF NOT EXISTS shows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tvdb_id INTEGER UNIQUE,
        tmdb_id INTEGER,
        title TEXT NOT NULL,
        overview TEXT,
        poster_url TEXT,
        fanart_url TEXT,
        network TEXT,
        status TEXT DEFAULT 'Watching',
        total_seasons INTEGER DEFAULT 1,
        total_episodes INTEGER DEFAULT 0,
        runtime_per_episode INTEGER DEFAULT 45,
        created_at TEXT
    )
    ''')
    
    # 2. Seasons
    cur.execute('''
    CREATE TABLE IF NOT EXISTS seasons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        show_id INTEGER NOT NULL,
        season_number INTEGER NOT NULL,
        title TEXT,
        episode_count INTEGER DEFAULT 0,
        FOREIGN KEY (show_id) REFERENCES shows (id) ON DELETE CASCADE,
        UNIQUE (show_id, season_number)
    )
    ''')
    
    # 3. Episodes
    cur.execute('''
    CREATE TABLE IF NOT EXISTS episodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        show_id INTEGER NOT NULL,
        season_number INTEGER NOT NULL,
        episode_number INTEGER NOT NULL,
        title TEXT,
        overview TEXT,
        air_date TEXT,
        runtime INTEGER DEFAULT 45,
        is_watched INTEGER DEFAULT 0,
        rewatch_count INTEGER DEFAULT 0,
        watched_at TEXT,
        rating REAL DEFAULT 0.0,
        reaction TEXT DEFAULT '',
        personal_note TEXT DEFAULT '',
        FOREIGN KEY (show_id) REFERENCES shows (id) ON DELETE CASCADE,
        UNIQUE (show_id, season_number, episode_number)
    )
    ''')
    
    # 4. Movies
    cur.execute('''
    CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tmdb_id INTEGER,
        tvdb_id INTEGER,
        title TEXT NOT NULL,
        overview TEXT,
        poster_url TEXT,
        fanart_url TEXT,
        release_year INTEGER,
        runtime INTEGER DEFAULT 120,
        is_watched INTEGER DEFAULT 0,
        rewatch_count INTEGER DEFAULT 0,
        watched_at TEXT,
        rating REAL DEFAULT 0.0,
        reaction TEXT DEFAULT '',
        personal_note TEXT DEFAULT '',
        status TEXT DEFAULT 'Plan to Watch',
        created_at TEXT
    )
    ''')
    
    # 5. User Profile
    cur.execute('''
    CREATE TABLE IF NOT EXISTS user_profile (
        id INTEGER PRIMARY KEY,
        user_id TEXT,
        name TEXT,
        email TEXT,
        timezone TEXT,
        created_at TEXT
    )
    ''')

    # 6. App Settings
    cur.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TEXT
    )
    ''')

    # 7. Multi-Profile Tables
    cur.execute('''
    CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        avatar TEXT DEFAULT '👤',
        is_active INTEGER DEFAULT 0,
        created_at TEXT
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS profile_episodes (
        profile_id INTEGER NOT NULL,
        episode_id INTEGER NOT NULL,
        show_id INTEGER DEFAULT 0,
        is_watched INTEGER DEFAULT 0,
        rewatch_count INTEGER DEFAULT 0,
        watched_at TEXT,
        reaction TEXT DEFAULT '',
        personal_note TEXT DEFAULT '',
        PRIMARY KEY (profile_id, episode_id)
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS profile_movies (
        profile_id INTEGER NOT NULL,
        movie_id INTEGER NOT NULL,
        is_watched INTEGER DEFAULT 0,
        rewatch_count INTEGER DEFAULT 0,
        watched_at TEXT,
        status TEXT DEFAULT 'Plan to Watch',
        reaction TEXT DEFAULT '',
        personal_note TEXT DEFAULT '',
        PRIMARY KEY (profile_id, movie_id)
    )
    ''')

    # Ensure at least one active default profile exists
    p_count = cur.execute('SELECT COUNT(*) FROM profiles').fetchone()[0]
    if p_count == 0:
        existing_user = cur.execute('SELECT name FROM user_profile LIMIT 1').fetchone()
        name = existing_user[0] if (existing_user and existing_user[0]) else 'Dororo'
        now_str = datetime.now().isoformat()
        cur.execute('INSERT INTO profiles (name, avatar, is_active, created_at) VALUES (?, ?, 1, ?)', (name, '👑', now_str))
        default_pid = cur.lastrowid

        # Migrate existing watched episodes to profile 1
        cur.execute('''
        INSERT OR IGNORE INTO profile_episodes (profile_id, episode_id, is_watched, rewatch_count, watched_at, reaction, personal_note)
        SELECT ?, id, is_watched, rewatch_count, watched_at, reaction, personal_note FROM episodes
        WHERE is_watched = 1 OR rewatch_count > 0 OR reaction != '' OR personal_note != ''
        ''', (default_pid,))

        # Migrate existing movies to profile 1
        cur.execute('''
        INSERT OR IGNORE INTO profile_movies (profile_id, movie_id, is_watched, rewatch_count, watched_at, status, reaction, personal_note)
        SELECT ?, id, is_watched, rewatch_count, watched_at, status, reaction, personal_note FROM movies
        ''', (default_pid,))

    # Safe column migrations if database already existed
    try:
        cur.execute("ALTER TABLE profile_episodes ADD COLUMN show_id INTEGER DEFAULT 0")
        cur.execute("UPDATE profile_episodes SET show_id = (SELECT show_id FROM episodes WHERE episodes.id = profile_episodes.episode_id) WHERE show_id = 0 OR show_id IS NULL")
    except:
        pass
    try:
        cur.execute("ALTER TABLE episodes ADD COLUMN reaction TEXT DEFAULT ''")
    except:
        pass
    try:
        cur.execute("ALTER TABLE episodes ADD COLUMN personal_note TEXT DEFAULT ''")
    except:
        pass
    try:
        cur.execute("ALTER TABLE movies ADD COLUMN reaction TEXT DEFAULT ''")
    except:
        pass
    try:
        cur.execute("ALTER TABLE movies ADD COLUMN personal_note TEXT DEFAULT ''")
    except:
        pass

    con.commit()
    cur.close()
    return con

def get_active_profile(con):
    cur = con.cursor()
    row = cur.execute('SELECT * FROM profiles WHERE is_active = 1 LIMIT 1').fetchone()
    if not row:
        row = cur.execute('SELECT * FROM profiles ORDER BY id ASC LIMIT 1').fetchone()
        if row:
            cur.execute('UPDATE profiles SET is_active = 1 WHERE id = ?', (row['id'],))
            con.commit()
    return dict(row) if row else {"id": 1, "name": "Dororo", "avatar": "👑"}

def set_active_profile(con, profile_id):
    cur = con.cursor()
    cur.execute('UPDATE profiles SET is_active = 0')
    cur.execute('UPDATE profiles SET is_active = 1 WHERE id = ?', (profile_id,))
    con.commit()
    return get_active_profile(con)
