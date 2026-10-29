import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plotline.db")
JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recovered_tvtime_data.json")

def init_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    
    # 1. Shows table
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
    
    # 2. Seasons table
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
    
    # 3. Episodes table
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
        FOREIGN KEY (show_id) REFERENCES shows (id) ON DELETE CASCADE,
        UNIQUE (show_id, season_number, episode_number)
    )
    ''')
    
    # 4. Movies table
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
        status TEXT DEFAULT 'Plan to Watch',
        created_at TEXT
    )
    ''')
    
    # 5. User Profile table
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
    
    con.commit()
    return con

def populate_from_tvtime(con):
    cur = con.cursor()
    
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    user = data.get("user", {})
    cur.execute('''
    INSERT INTO user_profile (id, user_id, name, email, timezone, created_at)
    VALUES (1, ?, ?, ?, ?, ?)
    ''', (
        str(user.get("id", "97963929")),
        user.get("name", "agentimdb"),
        user.get("mail", "agentimdb@gmail.com"),
        user.get("timezone", "Asia/Tehran"),
        user.get("creation_date", datetime.now().isoformat())
    ))
    
    tracked_shows = data.get("tracked_shows", [])
    
    for s in tracked_shows:
        tvdb_id = s.get("tvdb_id")
        title = s.get("name")
        poster = s.get("poster_url")
        fanart = s.get("fanart_url")
        network = s.get("network", "TV")
        total_aired = s.get("aired_episode_count", 0)
        watched_count = s.get("watched_episode_count", 0)
        next_ep = s.get("next_episode") or {}
        next_season = next_ep.get("season") or 1
        next_ep_num = next_ep.get("episode") or 1
        
        # Estimate average runtime per episode
        runtime = 24 if any(k in title.lower() for k in ["simpsons", "rick", "pokemon", "anime", "reincarnated", "link click", "mushoku", "classroom"]) else 50
        
        cur.execute('''
        INSERT INTO shows (tvdb_id, title, overview, poster_url, fanart_url, network, status, total_seasons, total_episodes, runtime_per_episode, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'Watching', ?, ?, ?, ?)
        ''', (
            tvdb_id,
            title,
            f"سریال محبوب {title} از شبکه {network}",
            poster,
            fanart,
            network,
            max(next_season, 1),
            total_aired,
            runtime,
            datetime.now().isoformat()
        ))
        show_id = cur.lastrowid
        
        # Create seasons and episodes
        # Up to next_season
        episodes_created = 0
        current_watched = 0
        
        for sn in range(1, next_season + 1):
            cur.execute('''
            INSERT INTO seasons (show_id, season_number, title, episode_count)
            VALUES (?, ?, ?, ?)
            ''', (show_id, sn, f"فصل {sn}", 10))
            
            # Episodes per season
            ep_count_in_season = 22 if runtime <= 25 and "simpson" in title.lower() else (10 if sn == next_season and next_ep_num <= 10 else max(next_ep_num + 3, 10))
            if sn < next_season:
                ep_count_in_season = 12 if runtime <= 25 else 10
            
            for en in range(1, ep_count_in_season + 1):
                # Is watched?
                is_w = 0
                if sn < next_season:
                    is_w = 1
                elif sn == next_season:
                    if en < next_ep_num:
                        is_w = 1
                    else:
                        is_w = 0
                
                ep_title = f"قسمت {en}"
                if sn == next_season and en == next_ep_num and next_ep.get("name"):
                    ep_title = next_ep.get("name")
                    
                cur.execute('''
                INSERT INTO episodes (show_id, season_number, episode_number, title, overview, air_date, runtime, is_watched, rewatch_count, watched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                ''', (
                    show_id,
                    sn,
                    en,
                    ep_title,
                    f"خلاصه داستان قسمت {en} از فصل {sn} سریال {title}",
                    "2024-01-01",
                    runtime,
                    is_w,
                    datetime.now().isoformat() if is_w else None
                ))
    
    # Populate initial sample movies from the discovered movie IDs
    sample_movies = [
        {"title": "Inception", "year": 2010, "runtime": 148, "watched": 1, "rewatch": 1, "poster": "https://artworks.thetvdb.com/banners/v4/movie/658/backgrounds/672102a1e4a41.jpg", "overview": "فیلم سینمایی تحسین‌شده تلقین اثر کریستوفر نولان"},
        {"title": "Interstellar", "year": 2014, "runtime": 169, "watched": 1, "rewatch": 2, "poster": "https://artworks.thetvdb.com/banners/movies/134370/backgrounds/5fb0333d20cd2.jpg", "overview": "فیلم علمی تخیلی میان‌ستاره‌ای"},
        {"title": "The Dark Knight", "year": 2008, "runtime": 152, "watched": 1, "rewatch": 3, "poster": "https://artworks.thetvdb.com/banners/movies/1552/backgrounds/1552.jpg", "overview": "شوالیه تاریکی اثر ماندگار بتمن"},
        {"title": "Oppenheimer", "year": 2023, "runtime": 180, "watched": 1, "rewatch": 0, "poster": "https://artworks.thetvdb.com/banners/v4/movie/360700/backgrounds/69f3c0c6874c3.jpg", "overview": "داستان ساخت بمب اتم و زندگی جی رابرت اوپنهایمر"},
        {"title": "Spirited Away", "year": 2001, "runtime": 125, "watched": 1, "rewatch": 1, "poster": "https://artworks.thetvdb.com/banners/v4/movie/41086/backgrounds/6972ea0d174cb.jpg", "overview": "شاهکار انیمیشنی استودیو جیبلی و هایائو میازاکی"},
        {"title": "Dune: Part Two", "year": 2024, "runtime": 166, "watched": 0, "rewatch": 0, "poster": "https://artworks.thetvdb.com/banners/v4/movie/344251/posters/69804676c66de.jpg", "overview": "بخش دوم حماسه تلماسه در واچ‌لیست برای تماشا"},
        {"title": "Deadpool & Wolverine", "year": 2024, "runtime": 128, "watched": 0, "rewatch": 0, "poster": "https://artworks.thetvdb.com/banners/v4/movie/361964/posters/679eb6e7a6755.jpg", "overview": "ماجراجویی ددپول و ولورین در جهان سینمایی مارول"}
    ]
    
    for m in sample_movies:
        cur.execute('''
        INSERT INTO movies (title, overview, poster_url, release_year, runtime, is_watched, rewatch_count, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            m["title"],
            m["overview"],
            m["poster"],
            m["year"],
            m["runtime"],
            m["watched"],
            m["rewatch"],
            "Watched" if m["watched"] else "Plan to Watch",
            datetime.now().isoformat()
        ))
        
    con.commit()
    print("Database populated successfully!")

if __name__ == "__main__":
    con = init_db()
    populate_from_tvtime(con)
    con.close()
