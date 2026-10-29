import csv
import json
import io
import re
from datetime import datetime

def import_letterboxd_csv(csv_content, con):
    """
    Parses Letterboxd watched.csv and inserts/updates movies in Plotline.
    Format: Date, Name, Year, Letterboxd URI, Rating
    """
    cur = con.cursor()
    reader = csv.DictReader(io.StringIO(csv_content))
    imported_count = 0

    for row in reader:
        name = row.get("Name") or row.get("Title")
        if not name:
            continue
        year_str = row.get("Year", "2024")
        try:
            year = int(year_str)
        except:
            year = 2024

        watched_date = row.get("Date") or datetime.now().isoformat()
        rating_val = 0.0
        try:
            rating_str = row.get("Rating")
            if rating_str:
                rating_val = float(rating_str) * 2 # Letterboxd is 1-5, Plotline is 1-10
        except:
            pass

        # Check if movie already exists
        existing = cur.execute('SELECT id FROM movies WHERE LOWER(title) = LOWER(?)', (name.strip(),)).fetchone()
        if existing:
            cur.execute('''
            UPDATE movies SET is_watched = 1, watched_at = ?, rating = ?, status = 'Watched'
            WHERE id = ?
            ''', (watched_date, rating_val, existing[0]))
        else:
            cur.execute('''
            INSERT INTO movies (title, release_year, runtime, is_watched, watched_at, rating, status, created_at)
            VALUES (?, ?, 120, 1, ?, ?, 'Watched', ?)
            ''', (name.strip(), year, watched_date, rating_val, datetime.now().isoformat()))
        imported_count += 1

    con.commit()
    return imported_count

def import_trakt_history_json(json_content, con):
    """
    Parses Trakt.tv watch history export (JSON) and imports movies and episodes.
    """
    cur = con.cursor()
    data = json.loads(json_content) if isinstance(json_content, str) else json_content
    imported_movies = 0
    imported_episodes = 0

    items = data if isinstance(data, list) else data.get("history", [])

    for item in items:
        item_type = item.get("type") or ("movie" if "movie" in item else "episode")
        watched_at = item.get("watched_at") or datetime.now().isoformat()

        if item_type == "movie":
            m_info = item.get("movie", item)
            title = m_info.get("title")
            year = m_info.get("year", 2024)
            if title:
                existing = cur.execute('SELECT id FROM movies WHERE LOWER(title) = LOWER(?)', (title.strip(),)).fetchone()
                if existing:
                    cur.execute("UPDATE movies SET is_watched = 1, watched_at = ?, status = 'Watched' WHERE id = ?", (watched_at, existing[0]))
                else:
                    cur.execute('''
                    INSERT INTO movies (title, release_year, runtime, is_watched, watched_at, status, created_at)
                    VALUES (?, ?, 120, 1, ?, 'Watched', ?)
                    ''', (title.strip(), year, watched_at, datetime.now().isoformat()))
                imported_movies += 1

        elif item_type == "episode":
            show_info = item.get("show", {})
            show_title = show_info.get("title")
            ep_info = item.get("episode", {})
            s_num = ep_info.get("season", 1)
            e_num = ep_info.get("number", 1)
            ep_title = ep_info.get("title", f"Episode {e_num}")

            if show_title:
                # Find or create show
                show = cur.execute('SELECT id FROM shows WHERE LOWER(title) = LOWER(?)', (show_title.strip(),)).fetchone()
                if not show:
                    cur.execute('''
                    INSERT INTO shows (title, status, total_seasons, total_episodes, created_at)
                    VALUES (?, 'Watching', ?, ?, ?)
                    ''', (show_title.strip(), s_num, s_num * 10, datetime.now().isoformat()))
                    show_id = cur.lastrowid
                else:
                    show_id = show[0]

                # Ensure season
                cur.execute('INSERT OR IGNORE INTO seasons (show_id, season_number, title) VALUES (?, ?, ?)', (show_id, s_num, f"Season {s_num}"))

                # Insert or mark episode
                cur.execute('''
                INSERT OR REPLACE INTO episodes (show_id, season_number, episode_number, title, is_watched, watched_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ''', (show_id, s_num, e_num, ep_title, watched_at))
                imported_episodes += 1

    con.commit()
    return {"movies": imported_movies, "episodes": imported_episodes}

def import_tvtime_json(json_content, con):
    """
    Parses TV Time JSON export or Plotline JSON backup and imports all records.
    """
    cur = con.cursor()
    data = json.loads(json_content) if isinstance(json_content, str) else json_content

    # If it is a Plotline backup format
    if "shows" in data and "episodes" in data:
        for s in data["shows"]:
            cur.execute('''
            INSERT OR REPLACE INTO shows (id, tvdb_id, title, overview, poster_url, network, status, total_seasons, total_episodes, runtime_per_episode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (s.get("id"), s.get("tvdb_id"), s.get("title"), s.get("overview"), s.get("poster_url"), s.get("network"), s.get("status"), s.get("total_seasons"), s.get("total_episodes"), s.get("runtime_per_episode"), s.get("created_at")))
            
        for e in data["episodes"]:
            cur.execute('''
            INSERT OR REPLACE INTO episodes (id, show_id, season_number, episode_number, title, runtime, is_watched, rewatch_count, watched_at, rating, reaction, personal_note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (e.get("id"), e.get("show_id"), e.get("season_number"), e.get("episode_number"), e.get("title"), e.get("runtime"), e.get("is_watched"), e.get("rewatch_count"), e.get("watched_at"), e.get("rating", 0.0), e.get("reaction", ""), e.get("personal_note", "")))

        for m in data.get("movies", []):
            cur.execute('''
            INSERT OR REPLACE INTO movies (id, title, overview, poster_url, release_year, runtime, is_watched, rewatch_count, status, rating, reaction, personal_note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (m.get("id"), m.get("title"), m.get("overview"), m.get("poster_url"), m.get("release_year"), m.get("runtime"), m.get("is_watched"), m.get("rewatch_count"), m.get("status"), m.get("rating", 0.0), m.get("reaction", ""), m.get("personal_note", ""), m.get("created_at")))

        con.commit()
        return {"shows": len(data["shows"]), "episodes": len(data["episodes"]), "movies": len(data.get("movies", []))}

    # If it is raw TV Time tracked shows format
    tracked_shows = data.get("tracked_shows", [])
    count = 0
    for s in tracked_shows:
        title = s.get("name") or s.get("title")
        if not title: continue
        cur.execute('''
        INSERT OR IGNORE INTO shows (tvdb_id, title, poster_url, network, status, total_seasons, total_episodes, created_at)
        VALUES (?, ?, ?, ?, 'Watching', ?, ?, ?)
        ''', (s.get("tvdb_id"), title, s.get("poster_url"), s.get("network", "TV"), 1, s.get("aired_episode_count", 10), datetime.now().isoformat()))
        count += 1
    con.commit()
    return {"shows": count}
