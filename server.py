import http.server
import socketserver
import urllib.parse
import json
import os
import sqlite3
import re
from datetime import datetime

import metadata
import gamification
import importers

PORT = 8765
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
MEDIA_DIR = os.path.join(BASE_DIR, "data", "media")
DB_PATH = os.path.join(BASE_DIR, "plotline.db")

def get_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode = WAL;")
    con.row_factory = sqlite3.Row
    return con

def get_active_pid(con):
    cur = con.cursor()
    row = cur.execute('SELECT id FROM profiles WHERE is_active = 1 LIMIT 1').fetchone()
    if row:
        return row[0]
    p = cur.execute('SELECT id FROM profiles ORDER BY id ASC LIMIT 1').fetchone()
    if p:
        cur.execute('UPDATE profiles SET is_active = 1 WHERE id = ?', (p[0],))
        con.commit()
        return p[0]
    now_str = datetime.now().isoformat()
    cur.execute("INSERT INTO profiles (name, avatar, is_active, created_at) VALUES ('Dororo', '👑', 1, ?)", (now_str,))
    con.commit()
    return cur.lastrowid

class PlotlineHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        # 1. Serve cached media assets (posters, backdrops)
        if path.startswith("/media/"):
            rel_path = path[len("/media/"):]
            file_path = os.path.join(MEDIA_DIR, urllib.parse.unquote(rel_path))
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.send_response(200)
                ext = os.path.splitext(file_path)[1].lower()
                mime = "image/jpeg"
                if ext == ".png": mime = "image/png"
                elif ext == ".webp": mime = "image/webp"
                self.send_header('Content-Type', mime)
                self.send_header('Cache-Control', 'public, max-age=31536000')
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_error(404, "Media asset not found")
                return

        # 2. API Routes
        if path.startswith("/api/"):
            self.handle_api_get(path, urllib.parse.parse_qs(parsed.query))
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b'{}'
        try:
            data = json.loads(body.decode('utf-8'))
        except:
            data = {}
            
        if path.startswith("/api/"):
            self.handle_api_post(path, data)
        else:
            self.send_error(404, "Not Found")

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def handle_api_get(self, path, params):
        con = get_db()
        cur = con.cursor()
        
        try:
            # 1. Profiles List & Active Profile
            if path == "/api/profiles":
                active_id = get_active_pid(con)
                profiles = [dict(p) for p in cur.execute('SELECT * FROM profiles ORDER BY id ASC').fetchall()]
                self.send_json({"profiles": profiles, "active_id": active_id})

            # 2. Stats (Per-Tab Binge Banners & Active Profile)
            elif path == "/api/stats":
                pid = get_active_pid(con)
                active_p = cur.execute('SELECT * FROM profiles WHERE id = ?', (pid,)).fetchone()
                
                ep_stats = cur.execute('''
                SELECT 
                    COUNT(*) as watched_eps,
                    COALESCE(SUM(pe.rewatch_count), 0) as total_ep_rewatches,
                    COALESCE(SUM(e.runtime * (1 + pe.rewatch_count)), 0) as total_ep_min
                FROM profile_episodes pe
                JOIN episodes e ON e.id = pe.episode_id
                WHERE pe.profile_id = ? AND pe.is_watched = 1
                ''', (pid,)).fetchone()
                
                m_stats = cur.execute('''
                SELECT 
                    COUNT(*) as watched_movies,
                    COALESCE(SUM(pm.rewatch_count), 0) as total_m_rewatches,
                    COALESCE(SUM(m.runtime * (1 + pm.rewatch_count)), 0) as total_m_min
                FROM profile_movies pm
                JOIN movies m ON m.id = pm.movie_id
                WHERE pm.profile_id = ? AND pm.is_watched = 1
                ''', (pid,)).fetchone()
                
                show_count = cur.execute('SELECT COUNT(*) FROM shows').fetchone()[0]
                total_ep_count = cur.execute('SELECT COUNT(*) FROM episodes').fetchone()[0]
                total_m_count = cur.execute('SELECT COUNT(*) FROM movies').fetchone()[0]
                
                def breakdown(total_min):
                    m = total_min // 43200
                    r = total_min % 43200
                    d = r // 1440
                    r = r % 1440
                    h = r // 60
                    mins = r % 60
                    return {"total_minutes": total_min, "months": m, "days": d, "hours": h, "minutes": mins}
                
                s_min = ep_stats['total_ep_min'] or 0
                m_min = m_stats['total_m_min'] or 0
                comb_min = s_min + m_min
                
                res = {
                    "total_minutes": comb_min,
                    "months": comb_min // 43200,
                    "days": (comb_min % 43200) // 1440,
                    "hours": ((comb_min % 43200) % 1440) // 60,
                    "minutes": comb_min % 60,
                    "series_time": breakdown(s_min),
                    "movies_time": breakdown(m_min),
                    "total_shows": show_count,
                    "total_episodes": total_ep_count,
                    "watched_episodes": ep_stats['watched_eps'] or 0,
                    "episode_rewatches": ep_stats['total_ep_rewatches'] or 0,
                    "total_movies": total_m_count,
                    "watched_movies": m_stats['watched_movies'] or 0,
                    "movie_rewatches": m_stats['total_m_rewatches'] or 0,
                    "active_profile": dict(active_p) if active_p else {"id": 1, "name": "Dororo", "avatar": "👑"}
                }
                self.send_json(res)

            # 3. Shows List (with Next Episode info for active profile)
            elif path == "/api/shows":
                pid = get_active_pid(con)
                shows = cur.execute('''
                SELECT s.*, 
                    (SELECT COUNT(*) FROM profile_episodes pe WHERE pe.show_id = s.id AND pe.profile_id = ? AND pe.is_watched = 1) as watched_eps,
                    (SELECT COUNT(*) FROM episodes e WHERE e.show_id = s.id) as total_eps
                FROM shows s
                ORDER BY s.title ASC
                ''', (pid,)).fetchall()
                
                result = []
                for s in shows:
                    s_dict = dict(s)
                    next_ep = cur.execute('''
                    SELECT e.id, e.season_number, e.episode_number, e.title, e.air_date, e.runtime,
                           pe.reaction, pe.personal_note
                    FROM episodes e
                    LEFT JOIN profile_episodes pe ON pe.episode_id = e.id AND pe.profile_id = ?
                    WHERE e.show_id = ? AND COALESCE(pe.is_watched, 0) = 0
                    ORDER BY e.season_number ASC, e.episode_number ASC
                    LIMIT 1
                    ''', (pid, s['id'])).fetchone()
                    s_dict['next_episode'] = dict(next_ep) if next_ep else None
                    result.append(s_dict)
                    
                self.send_json(result)
                
            # 4. Single Show with All Seasons and Episodes for active profile
            elif path.startswith("/api/shows/"):
                pid = get_active_pid(con)
                show_id = int(path.split("/")[-1])
                show = cur.execute('SELECT * FROM shows WHERE id = ?', (show_id,)).fetchone()
                if not show:
                    self.send_json({"error": "Show not found"}, 404)
                    return
                    
                s_dict = dict(show)
                seasons = cur.execute('''
                SELECT * FROM seasons WHERE show_id = ? ORDER BY season_number ASC
                ''', (show_id,)).fetchall()
                
                s_dict['seasons'] = []
                for sn in seasons:
                    sn_dict = dict(sn)
                    eps = cur.execute('''
                    SELECT e.*,
                           COALESCE(pe.is_watched, 0) as is_watched,
                           COALESCE(pe.rewatch_count, 0) as rewatch_count,
                           COALESCE(pe.reaction, '') as reaction,
                           COALESCE(pe.personal_note, '') as personal_note,
                           pe.watched_at
                    FROM episodes e
                    LEFT JOIN profile_episodes pe ON pe.episode_id = e.id AND pe.profile_id = ?
                    WHERE e.show_id = ? AND e.season_number = ? 
                    ORDER BY e.episode_number ASC
                    ''', (pid, show_id, sn['season_number'])).fetchall()
                    sn_dict['episodes'] = [dict(ep) for ep in eps]
                    s_dict['seasons'].append(sn_dict)
                    
                self.send_json(s_dict)
                
            # 5. Movies List for active profile
            elif path == "/api/movies":
                pid = get_active_pid(con)
                movies = cur.execute('''
                SELECT m.*,
                       COALESCE(pm.is_watched, 0) as is_watched,
                       COALESCE(pm.rewatch_count, 0) as rewatch_count,
                       COALESCE(pm.reaction, '') as reaction,
                       COALESCE(pm.personal_note, '') as personal_note,
                       COALESCE(pm.status, m.status) as user_status,
                       pm.watched_at
                FROM movies m
                LEFT JOIN profile_movies pm ON pm.movie_id = m.id AND pm.profile_id = ?
                ORDER BY m.id DESC
                ''', (pid,)).fetchall()
                self.send_json([dict(m) for m in movies])

            # 6. Online Metadata & Anime Search (Level 2 + Anime)
            elif path == "/api/search":
                q = params.get('q', [''])[0].strip()
                target_type = params.get('type', ['shows'])[0]
                
                if not q:
                    self.send_json([])
                    return
                    
                results = []
                if target_type == 'movies':
                    tmdb_row = cur.execute("SELECT value FROM settings WHERE key='tmdb_api_key'").fetchone()
                    tmdb_key = tmdb_row[0] if tmdb_row else None
                    results = metadata.search_movies_open(q, tmdb_key)
                    anime_res = [a for a in metadata.search_anime_jikan(q) if a.get('type') == 'movie']
                    results.extend(anime_res)
                else:
                    results = metadata.search_tvmaze_shows(q)
                    anime_res = [a for a in metadata.search_anime_jikan(q) if a.get('type') == 'show']
                    results.extend(anime_res)
                    
                self.send_json(results)

            # 7. Release Calendar (Strictly Future Releases)
            elif path == "/api/calendar":
                pid = get_active_pid(con)
                upcoming = cur.execute('''
                SELECT e.*, s.title as show_title, s.poster_url as show_poster, s.network as show_network
                FROM episodes e
                JOIN shows s ON e.show_id = s.id
                LEFT JOIN profile_episodes pe ON pe.episode_id = e.id AND pe.profile_id = ?
                WHERE e.air_date IS NOT NULL 
                  AND e.air_date != '' 
                  AND date(e.air_date) >= date('now')
                  AND COALESCE(pe.is_watched, 0) = 0
                ORDER BY e.air_date ASC, s.title ASC
                LIMIT 50
                ''', (pid,)).fetchall()
                
                upcoming_movies = cur.execute('''
                SELECT m.id, m.title as show_title, m.poster_url as show_poster, 'Movie' as show_network,
                       CAST(m.release_year AS TEXT) as air_date, m.overview, 0 as season_number, 0 as episode_number,
                       m.title
                FROM movies m
                LEFT JOIN profile_movies pm ON pm.movie_id = m.id AND pm.profile_id = ?
                WHERE m.release_year >= CAST(strftime('%Y', 'now') AS INTEGER)
                  AND COALESCE(pm.is_watched, 0) = 0
                ORDER BY m.release_year ASC
                LIMIT 20
                ''', (pid,)).fetchall()
                
                combined_cal = [dict(row) for row in upcoming]
                for m in upcoming_movies:
                    md = dict(m)
                    md['is_movie'] = True
                    combined_cal.append(md)
                    
                self.send_json(combined_cal)

            # 8. Time Sync (Network NTP with Hardware Clock Fallback)
            elif path == "/api/time/sync":
                synced = False
                source = "system_hardware_clock"
                now_dt = datetime.now()
                try:
                    req = urllib.request.Request("http://worldtimeapi.org/api/ip", headers={"User-Agent": metadata.USER_AGENT})
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        data = json.loads(resp.read().decode('utf-8'))
                        now_dt = datetime.fromisoformat(data.get("datetime")[:19])
                        synced = True
                        source = "network_ntp"
                except Exception:
                    synced = False
                    source = "system_hardware_clock"

                self.send_json({
                    "synced": synced,
                    "source": source,
                    "current_iso": now_dt.isoformat(),
                    "date": now_dt.strftime("%Y-%m-%d"),
                    "time": now_dt.strftime("%H:%M:%S")
                })

            # 9. Badges & Milestones (For active profile)
            elif path == "/api/badges":
                pid = get_active_pid(con)
                badges = gamification.calculate_badges(con, profile_id=pid)
                self.send_json(badges)

            # 10. Media Storage Stats & Cache Mode & Download Preview Size
            elif path == "/api/media/stats":
                stats = metadata.get_media_storage_stats()
                mode_row = cur.execute("SELECT value FROM settings WHERE key='cache_mode'").fetchone()
                stats['cache_mode'] = mode_row[0] if mode_row else 'stream'
                stats['pending'] = metadata.get_pending_download_stats(con)
                self.send_json(stats)

            # 11. Settings
            elif path == "/api/settings":
                settings_rows = cur.execute('SELECT key, value FROM settings').fetchall()
                res = {row['key']: row['value'] for row in settings_rows}
                self.send_json(res)
                
            # 12. Full Database Export (JSON)
            elif path == "/api/backup":
                shows = [dict(s) for s in cur.execute('SELECT * FROM shows').fetchall()]
                episodes = [dict(e) for e in cur.execute('SELECT * FROM episodes').fetchall()]
                movies = [dict(m) for m in cur.execute('SELECT * FROM movies').fetchall()]
                profiles = [dict(p) for p in cur.execute('SELECT * FROM profiles').fetchall()]
                profile_episodes = [dict(pe) for pe in cur.execute('SELECT * FROM profile_episodes').fetchall()]
                profile_movies = [dict(pm) for pm in cur.execute('SELECT * FROM profile_movies').fetchall()]
                
                export_data = {
                    "app": "Plotline",
                    "version": "1.1.0",
                    "exported_at": datetime.now().isoformat(),
                    "profiles": profiles,
                    "profile_episodes": profile_episodes,
                    "profile_movies": profile_movies,
                    "shows": shows,
                    "episodes": episodes,
                    "movies": movies
                }
                self.send_json(export_data)

            # 13. User Profile Get
            elif path == "/api/user/profile":
                pid = get_active_pid(con)
                p = cur.execute('SELECT * FROM profiles WHERE id = ?', (pid,)).fetchone()
                if p:
                    self.send_json(dict(p))
                else:
                    self.send_json({"id": 1, "name": "Dororo", "avatar": "👑"})

            # 14. Featured Titles for Discover Tab
            elif path == "/api/discover/featured":
                featured = metadata.get_featured_titles()
                self.send_json(featured)
                
            else:
                self.send_json({"error": "Endpoint not found"}, 404)
        finally:
            con.close()

    def handle_api_post(self, path, data):
        con = get_db()
        cur = con.cursor()
        
        try:
            # 1. Profile Management (Multi-Profile Engine)
            if path == "/api/profiles/add":
                name = (data.get("name") or "New Profile").strip()
                avatar = (data.get("avatar") or "👤").strip()
                now_str = datetime.now().isoformat()
                cur.execute("INSERT INTO profiles (name, avatar, is_active, created_at) VALUES (?, ?, 0, ?)", (name, avatar, now_str))
                new_id = cur.lastrowid
                con.commit()
                self.send_json({"success": True, "id": new_id, "name": name, "avatar": avatar})

            elif path == "/api/profiles/switch":
                pid = int(data.get("profile_id", 1))
                cur.execute("UPDATE profiles SET is_active = 0")
                cur.execute("UPDATE profiles SET is_active = 1 WHERE id = ?", (pid,))
                con.commit()
                self.send_json({"success": True, "active_id": pid})

            elif path == "/api/profiles/delete":
                pid = int(data.get("profile_id", 0))
                total_p = cur.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
                if total_p <= 1:
                    self.send_json({"error": "Cannot delete the only remaining profile"}, 400)
                    return
                cur.execute("DELETE FROM profile_episodes WHERE profile_id = ?", (pid,))
                cur.execute("DELETE FROM profile_movies WHERE profile_id = ?", (pid,))
                cur.execute("DELETE FROM profiles WHERE id = ?", (pid,))
                con.commit()
                
                active = cur.execute("SELECT id FROM profiles WHERE is_active = 1").fetchone()
                if not active:
                    first_p = cur.execute("SELECT id FROM profiles ORDER BY id ASC LIMIT 1").fetchone()[0]
                    cur.execute("UPDATE profiles SET is_active = 1 WHERE id = ?", (first_p,))
                    con.commit()
                self.send_json({"success": True})

            elif path == "/api/profiles/update":
                pid = int(data.get("profile_id", 0))
                name = (data.get("name") or "").strip()
                avatar = (data.get("avatar") or "").strip()
                if name and avatar:
                    cur.execute("UPDATE profiles SET name = ?, avatar = ? WHERE id = ?", (name, avatar, pid))
                elif name:
                    cur.execute("UPDATE profiles SET name = ? WHERE id = ?", (name, pid))
                elif avatar:
                    cur.execute("UPDATE profiles SET avatar = ? WHERE id = ?", (avatar, pid))
                con.commit()
                self.send_json({"success": True})

            # 2. Toggle Episode Watched (For Active Profile)
            elif path.startswith("/api/episodes/") and path.endswith("/toggle"):
                ep_id = int(path.split("/")[-2])
                pid = get_active_pid(con)
                now_str = datetime.now().isoformat()
                
                pe = cur.execute('SELECT is_watched FROM profile_episodes WHERE profile_id = ? AND episode_id = ?', (pid, ep_id)).fetchone()
                if pe:
                    new_status = 0 if pe['is_watched'] == 1 else 1
                    watched_at = now_str if new_status == 1 else None
                    cur.execute('UPDATE profile_episodes SET is_watched = ?, watched_at = ? WHERE profile_id = ? AND episode_id = ?', 
                                (new_status, watched_at, pid, ep_id))
                else:
                    ep_row = cur.execute('SELECT show_id FROM episodes WHERE id = ?', (ep_id,)).fetchone()
                    if not ep_row:
                        self.send_json({"error": "Episode not found"}, 404)
                        return
                    show_id = ep_row[0]
                    new_status = 1
                    cur.execute('INSERT INTO profile_episodes (profile_id, episode_id, show_id, is_watched, watched_at) VALUES (?, ?, ?, 1, ?)',
                                (pid, ep_id, show_id, now_str))
                
                cur.execute('UPDATE episodes SET is_watched = ?, watched_at = ? WHERE id = ?', (new_status, now_str if new_status == 1 else None, ep_id))
                con.commit()
                self.send_json({"success": True, "new_status": new_status, "episode_id": ep_id})

            # 3. Episode Reaction & Personal Note (For Active Profile)
            elif path.startswith("/api/episodes/") and path.endswith("/note"):
                ep_id = int(path.split("/")[-2])
                pid = get_active_pid(con)
                reaction = data.get("reaction", "")
                note = data.get("note", "")
                pe = cur.execute('SELECT id FROM profile_episodes WHERE profile_id = ? AND episode_id = ?', (pid, ep_id)).fetchone()
                if pe:
                    cur.execute('UPDATE profile_episodes SET reaction = ?, personal_note = ? WHERE profile_id = ? AND episode_id = ?',
                                (reaction, note, pid, ep_id))
                else:
                    ep_row = cur.execute('SELECT show_id FROM episodes WHERE id = ?', (ep_id,)).fetchone()
                    show_id = ep_row[0] if ep_row else 0
                    cur.execute('INSERT INTO profile_episodes (profile_id, episode_id, show_id, is_watched, reaction, personal_note) VALUES (?, ?, ?, 0, ?, ?)',
                                (pid, ep_id, show_id, reaction, note))
                cur.execute('UPDATE episodes SET reaction = ?, personal_note = ? WHERE id = ?', (reaction, note, ep_id))
                con.commit()
                self.send_json({"success": True, "episode_id": ep_id})
                
            # 4. Rewatch Count for Episode (For Active Profile)
            elif path.startswith("/api/episodes/") and path.endswith("/rewatch"):
                ep_id = int(path.split("/")[-2])
                pid = get_active_pid(con)
                delta = int(data.get("delta", 1))
                pe = cur.execute('SELECT rewatch_count FROM profile_episodes WHERE profile_id = ? AND episode_id = ?', (pid, ep_id)).fetchone()
                if pe:
                    cur.execute('UPDATE profile_episodes SET rewatch_count = MAX(0, rewatch_count + ?) WHERE profile_id = ? AND episode_id = ?',
                                (delta, pid, ep_id))
                else:
                    ep_row = cur.execute('SELECT show_id FROM episodes WHERE id = ?', (ep_id,)).fetchone()
                    show_id = ep_row[0] if ep_row else 0
                    cur.execute('INSERT INTO profile_episodes (profile_id, episode_id, show_id, is_watched, rewatch_count) VALUES (?, ?, ?, 1, ?)',
                                (pid, ep_id, show_id, max(0, delta)))
                cur.execute('UPDATE episodes SET rewatch_count = MAX(0, rewatch_count + ?) WHERE id = ?', (delta, ep_id))
                con.commit()
                new_val = cur.execute('SELECT rewatch_count FROM profile_episodes WHERE profile_id = ? AND episode_id = ?', (pid, ep_id)).fetchone()[0]
                self.send_json({"success": True, "rewatch_count": new_val})
                
            # 5. Mark Entire Season Watched / Unwatched (For Active Profile)
            elif path.startswith("/api/seasons/mark_all"):
                show_id = int(data.get("show_id"))
                season_num = int(data.get("season_number"))
                status = int(data.get("is_watched", 1))
                pid = get_active_pid(con)
                now_str = datetime.now().isoformat() if status == 1 else None
                
                eps = cur.execute('SELECT id FROM episodes WHERE show_id = ? AND season_number = ?', (show_id, season_num)).fetchall()
                for ep in eps:
                    ep_id = ep['id']
                    cur.execute('''
                    INSERT INTO profile_episodes (profile_id, episode_id, show_id, is_watched, watched_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(profile_id, episode_id) DO UPDATE SET is_watched = excluded.is_watched, watched_at = excluded.watched_at
                    ''', (pid, ep_id, show_id, status, now_str))
                    
                cur.execute('UPDATE episodes SET is_watched = ?, watched_at = ? WHERE show_id = ? AND season_number = ?', (status, now_str, show_id, season_num))
                con.commit()
                self.send_json({"success": True, "show_id": show_id, "season_number": season_num, "is_watched": status})
                
            # 6. Toggle Movie Watched (For Active Profile)
            elif path.startswith("/api/movies/") and path.endswith("/toggle"):
                m_id = int(path.split("/")[-2])
                pid = get_active_pid(con)
                now_str = datetime.now().isoformat()
                
                pm = cur.execute('SELECT is_watched FROM profile_movies WHERE profile_id = ? AND movie_id = ?', (pid, m_id)).fetchone()
                if pm:
                    new_status = 0 if pm['is_watched'] == 1 else 1
                    watched_at = now_str if new_status == 1 else None
                    status_txt = "Watched" if new_status == 1 else "Plan to Watch"
                    cur.execute('UPDATE profile_movies SET is_watched = ?, status = ?, watched_at = ? WHERE profile_id = ? AND movie_id = ?',
                                (new_status, status_txt, watched_at, pid, m_id))
                else:
                    new_status = 1
                    cur.execute('INSERT INTO profile_movies (profile_id, movie_id, is_watched, status, watched_at) VALUES (?, ?, 1, "Watched", ?)',
                                (pid, m_id, now_str))
                
                cur.execute('UPDATE movies SET is_watched = ?, status = ?, watched_at = ? WHERE id = ?',
                            (new_status, "Watched" if new_status == 1 else "Plan to Watch", now_str if new_status == 1 else None, m_id))
                con.commit()
                self.send_json({"success": True, "new_status": new_status, "movie_id": m_id})

            # 7. Movie Reaction and Note (For Active Profile)
            elif path.startswith("/api/movies/") and path.endswith("/note"):
                m_id = int(path.split("/")[-2])
                pid = get_active_pid(con)
                reaction = data.get("reaction", "")
                note = data.get("note", "")
                
                pm = cur.execute('SELECT id FROM profile_movies WHERE profile_id = ? AND movie_id = ?', (pid, m_id)).fetchone()
                if pm:
                    cur.execute('UPDATE profile_movies SET reaction = ?, personal_note = ? WHERE profile_id = ? AND movie_id = ?',
                                (reaction, note, pid, m_id))
                else:
                    cur.execute('INSERT INTO profile_movies (profile_id, movie_id, is_watched, status, reaction, personal_note) VALUES (?, ?, 0, "Plan to Watch", ?, ?)',
                                (pid, m_id, reaction, note))
                cur.execute('UPDATE movies SET reaction = ?, personal_note = ? WHERE id = ?', (reaction, note, m_id))
                con.commit()
                self.send_json({"success": True, "movie_id": m_id})

            # 8. Movie Rewatch (For Active Profile)
            elif path.startswith("/api/movies/") and path.endswith("/rewatch"):
                m_id = int(path.split("/")[-2])
                pid = get_active_pid(con)
                delta = int(data.get("delta", 1))
                
                pm = cur.execute('SELECT rewatch_count FROM profile_movies WHERE profile_id = ? AND movie_id = ?', (pid, m_id)).fetchone()
                if pm:
                    cur.execute('UPDATE profile_movies SET rewatch_count = MAX(0, rewatch_count + ?) WHERE profile_id = ? AND movie_id = ?',
                                (delta, pid, m_id))
                else:
                    cur.execute('INSERT INTO profile_movies (profile_id, movie_id, is_watched, status, rewatch_count) VALUES (?, ?, 1, "Watched", ?)',
                                (pid, m_id, max(0, delta)))
                cur.execute('UPDATE movies SET rewatch_count = MAX(0, rewatch_count + ?) WHERE id = ?', (delta, m_id))
                con.commit()
                new_val = cur.execute('SELECT rewatch_count FROM profile_movies WHERE profile_id = ? AND movie_id = ?', (pid, m_id)).fetchone()[0]
                self.send_json({"success": True, "rewatch_count": new_val})

            # 9. Import Show from TVMaze (Level 2 with Hybrid Cache)
            elif path == "/api/shows/import_tvmaze":
                tvmaze_id = data.get("id")
                title = data.get("title", "").strip()
                remote_poster = data.get("poster_url", "")
                overview = data.get("overview", "")
                network = data.get("network", "TV")
                runtime = int(data.get("runtime", 45))

                if not title or not tvmaze_id:
                    self.send_json({"error": "Invalid show payload"}, 400)
                    return

                mode_row = cur.execute("SELECT value FROM settings WHERE key='cache_mode'").fetchone()
                cache_mode = mode_row[0] if mode_row else 'stream'
                local_poster = metadata.cache_image(remote_poster, "posters", cache_mode=cache_mode)
                episodes = metadata.fetch_tvmaze_episodes(tvmaze_id)
                
                seasons_set = set()
                for ep in episodes:
                    seasons_set.add(ep.get("season", 1))

                total_seasons = max(seasons_set) if seasons_set else 1
                total_episodes = len(episodes)

                cur.execute('''
                INSERT INTO shows (tvdb_id, title, overview, poster_url, network, status, total_seasons, total_episodes, runtime_per_episode, created_at)
                VALUES (?, ?, ?, ?, ?, 'Watching', ?, ?, ?, ?)
                ''', (
                    tvmaze_id,
                    title,
                    overview,
                    local_poster,
                    network,
                    total_seasons,
                    total_episodes,
                    runtime,
                    datetime.now().isoformat()
                ))
                show_id = cur.lastrowid

                for s_num in sorted(list(seasons_set)):
                    cur.execute('''
                    INSERT OR IGNORE INTO seasons (show_id, season_number, title, episode_count)
                    VALUES (?, ?, ?, ?)
                    ''', (show_id, s_num, f"Season {s_num}", 0))

                for ep in episodes:
                    s_num = ep.get("season", 1)
                    e_num = ep.get("number", 1)
                    ep_title = ep.get("name") or f"Episode {e_num}"
                    ep_overview = metadata.clean_html_tags(ep.get("summary"))
                    ep_airdate = ep.get("airdate")
                    ep_runtime = ep.get("runtime") or runtime

                    cur.execute('''
                    INSERT OR IGNORE INTO episodes (show_id, season_number, episode_number, title, overview, air_date, runtime, is_watched)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                    ''', (show_id, s_num, e_num, ep_title, ep_overview, ep_airdate, ep_runtime))

                cur.execute('''
                UPDATE seasons SET episode_count = (
                    SELECT COUNT(*) FROM episodes WHERE episodes.show_id = seasons.show_id AND episodes.season_number = seasons.season_number
                ) WHERE show_id = ?
                ''', (show_id,))

                con.commit()
                self.send_json({"success": True, "show_id": show_id, "title": title, "episodes_count": total_episodes})

            # 10. Import Anime from Jikan/MyAnimeList
            elif path == "/api/shows/import_jikan":
                title = data.get("title", "").strip()
                if not title:
                    self.send_json({"error": "Title required"}, 400)
                    return
                mal_id = data.get("mal_id")
                remote_poster = data.get("poster_url", "")
                overview = data.get("overview", "")
                network = data.get("network", "TV (Anime)")
                runtime = int(data.get("runtime", 24))
                total_eps = int(data.get("total_episodes", 12))

                mode_row = cur.execute("SELECT value FROM settings WHERE key='cache_mode'").fetchone()
                cache_mode = mode_row[0] if mode_row else 'stream'
                local_poster = metadata.cache_image(remote_poster, "posters", cache_mode=cache_mode)

                cur.execute('''
                INSERT INTO shows (tvdb_id, title, overview, poster_url, network, status, total_seasons, total_episodes, runtime_per_episode, created_at)
                VALUES (?, ?, ?, ?, ?, 'Watching', 1, ?, ?, ?)
                ''', (f"mal-{mal_id}", title, overview, local_poster, network, total_eps, runtime, datetime.now().isoformat()))
                show_id = cur.lastrowid

                cur.execute('''
                INSERT INTO seasons (show_id, season_number, title, episode_count)
                VALUES (?, 1, 'Season 1', ?)
                ''', (show_id, total_eps))

                for ep_num in range(1, total_eps + 1):
                    cur.execute('''
                    INSERT INTO episodes (show_id, season_number, episode_number, title, runtime, is_watched)
                    VALUES (?, 1, ?, ?, ?, 0)
                    ''', (show_id, ep_num, f"Episode {ep_num}", runtime))

                con.commit()
                self.send_json({"success": True, "show_id": show_id, "title": title, "episodes_count": total_eps})

            # 11. Add / Import Movie
            elif path == "/api/movies/add" or path == "/api/movies/import_online":
                title = data.get("title", "").strip()
                if not title:
                    self.send_json({"error": "Title required"}, 400)
                    return
                year = int(data.get("release_year", 2024))
                runtime = int(data.get("runtime", 120))
                overview = data.get("overview", "")
                remote_poster = data.get("poster_url", "")
                status = data.get("status", "Plan to Watch")
                is_watched = 1 if status == "Watched" else 0
                pid = get_active_pid(con)

                mode_row = cur.execute("SELECT value FROM settings WHERE key='cache_mode'").fetchone()
                cache_mode = mode_row[0] if mode_row else 'stream'
                local_poster = metadata.cache_image(remote_poster, "posters", cache_mode=cache_mode)

                now_str = datetime.now().isoformat()
                cur.execute('''
                INSERT INTO movies (title, overview, poster_url, release_year, runtime, is_watched, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (title, overview, local_poster, year, runtime, is_watched, status, now_str))
                m_id = cur.lastrowid
                
                cur.execute('''
                INSERT INTO profile_movies (profile_id, movie_id, is_watched, status, watched_at)
                VALUES (?, ?, ?, ?, ?)
                ''', (pid, m_id, is_watched, status, now_str if is_watched == 1 else None))

                con.commit()
                self.send_json({"success": True, "id": m_id})

            # 12. Local Media Folder Scanner
            elif path == "/api/scanner/scan":
                folder_path = data.get("folder_path", "").strip()
                res = gamification.scan_local_folder(folder_path, con)
                self.send_json(res)

            # 13. Cache All Posters to Disk (Offline Download with Size Estimation)
            elif path == "/api/media/cache_all":
                cached_count = 0
                shows = cur.execute("SELECT id, poster_url FROM shows WHERE poster_url LIKE 'http%'").fetchall()
                for s in shows:
                    local_p = metadata.cache_image(s['poster_url'], 'posters', force_download=True)
                    cur.execute("UPDATE shows SET poster_url = ? WHERE id = ?", (local_p, s['id']))
                    cached_count += 1
                
                movies = cur.execute("SELECT id, poster_url FROM movies WHERE poster_url LIKE 'http%'").fetchall()
                for m in movies:
                    local_p = metadata.cache_image(m['poster_url'], 'posters', force_download=True)
                    cur.execute("UPDATE movies SET poster_url = ? WHERE id = ?", (local_p, m['id']))
                    cached_count += 1
                    
                con.commit()
                self.send_json({"success": True, "cached_count": cached_count})

            # 14. Switch Cache Mode Setting
            elif path == "/api/media/cache_mode":
                mode = data.get("mode", "stream")
                cur.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('cache_mode', ?, ?)", (mode, datetime.now().isoformat()))
                con.commit()
                self.send_json({"success": True, "cache_mode": mode})

            # 15. Multi-Platform Migration Importers
            elif path == "/api/import/letterboxd":
                csv_content = data.get("csv_content", "")
                imported = importers.import_letterboxd_csv(csv_content, con)
                self.send_json({"success": True, "imported_movies": imported})

            elif path == "/api/import/trakt":
                json_content = data.get("json_content", "")
                res = importers.import_trakt_history_json(json_content, con)
                self.send_json({"success": True, "result": res})

            elif path == "/api/import/tvtime":
                json_content = data.get("json_content", "")
                res = importers.import_tvtime_json(json_content, con)
                self.send_json({"success": True, "result": res})

            # 16. Save Settings
            elif path == "/api/settings":
                for k, v in data.items():
                    cur.execute('INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)', (k, str(v), datetime.now().isoformat()))
                con.commit()
                self.send_json({"success": True})

            # 17. User Profile Update
            elif path == "/api/user/profile":
                pid = get_active_pid(con)
                name = data.get("name", "").strip() or "Dororo"
                avatar = data.get("avatar", "").strip() or "👑"
                cur.execute('UPDATE profiles SET name = ?, avatar = ? WHERE id = ?', (name, avatar, pid))
                con.commit()
                self.send_json({"success": True, "name": name, "avatar": avatar})

            # 18. Manual Add Show
            elif path == "/api/shows/add":
                title = data.get("title", "").strip()
                if not title:
                    self.send_json({"error": "Title required"}, 400)
                    return
                network = data.get("network", "TV")
                seasons_cnt = int(data.get("seasons_count", 1))
                eps_per_season = int(data.get("episodes_per_season", 10))
                runtime = int(data.get("runtime", 45))
                poster_url = data.get("poster_url", "")
                overview = data.get("overview", "")
                
                mode_row = cur.execute("SELECT value FROM settings WHERE key='cache_mode'").fetchone()
                cache_mode = mode_row[0] if mode_row else 'stream'
                local_poster = metadata.cache_image(poster_url, "posters", cache_mode=cache_mode)

                cur.execute('''
                INSERT INTO shows (title, overview, poster_url, network, status, total_seasons, total_episodes, runtime_per_episode, created_at)
                VALUES (?, ?, ?, ?, 'Watching', ?, ?, ?, ?)
                ''', (title, overview, local_poster, network, seasons_cnt, seasons_cnt * eps_per_season, runtime, datetime.now().isoformat()))
                show_id = cur.lastrowid
                
                for sn in range(1, seasons_cnt + 1):
                    cur.execute('''
                    INSERT INTO seasons (show_id, season_number, title, episode_count)
                    VALUES (?, ?, ?, ?)
                    ''', (show_id, sn, f"Season {sn}", eps_per_season))
                    
                    for en in range(1, eps_per_season + 1):
                        cur.execute('''
                        INSERT INTO episodes (show_id, season_number, episode_number, title, runtime, is_watched)
                        VALUES (?, ?, ?, ?, ?, 0)
                        ''', (show_id, sn, en, f"Episode {en}", runtime))
                        
                con.commit()
                self.send_json({"success": True, "id": show_id})

            # 19. Media Server Scrobbler Webhook (Level 5: Jellyfin, Plex, Emby)
            elif path == "/api/scrobble/webhook":
                pid = get_active_pid(con)
                event = data.get("event") or data.get("NotificationType", "")
                is_scrobble = False
                item_type = ""
                show_title = ""
                season_num = 1
                ep_num = 1
                movie_title = ""

                # Jellyfin format
                if "NotificationType" in data or "ItemType" in data:
                    item_type = data.get("ItemType", "").lower()
                    played_to_end = data.get("PlayedToCompletion", True)
                    if played_to_end:
                        is_scrobble = True
                    show_title = data.get("SeriesName", "")
                    season_num = int(data.get("SeasonNumber", 1))
                    ep_num = int(data.get("EpisodeNumber", 1))
                    movie_title = data.get("Name", "") if item_type == "movie" else ""

                # Plex format
                elif "event" in data and "Metadata" in data:
                    if data.get("event") == "media.scrobble":
                        is_scrobble = True
                        meta = data.get("Metadata", {})
                        item_type = meta.get("type", "").lower()
                        if item_type == "episode":
                            show_title = meta.get("grandparentTitle", "")
                            season_num = int(meta.get("parentIndex", 1))
                            ep_num = int(meta.get("index", 1))
                        elif item_type == "movie":
                            movie_title = meta.get("title", "")

                # Generic / Direct format
                elif "type" in data:
                    item_type = data.get("type", "").lower()
                    is_scrobble = True
                    show_title = data.get("show_title", "")
                    season_num = int(data.get("season", 1))
                    ep_num = int(data.get("episode", 1))
                    movie_title = data.get("movie_title", "")

                if not is_scrobble:
                    self.send_json({"ignored": True, "reason": "Not a scrobble completion event"})
                    return

                now_str = datetime.now().isoformat()

                # Handle episode scrobble
                if item_type == "episode" and show_title:
                    show_row = cur.execute('SELECT id FROM shows WHERE LOWER(title) = ?', (show_title.lower(),)).fetchone()
                    if not show_row:
                        show_row = cur.execute('SELECT id FROM shows WHERE LOWER(title) LIKE ?', (f"%{show_title.lower()}%",)).fetchone()

                    if show_row:
                        show_id = show_row[0]
                        ep_row = cur.execute('''
                            SELECT id FROM episodes 
                            WHERE show_id = ? AND season_number = ? AND episode_number = ?
                        ''', (show_id, season_num, ep_num)).fetchone()

                        if ep_row:
                            ep_id = ep_row[0]
                            pe = cur.execute('SELECT is_watched, rewatch_count FROM profile_episodes WHERE profile_id = ? AND episode_id = ?', (pid, ep_id)).fetchone()
                            if pe and pe['is_watched'] == 1:
                                cur.execute('UPDATE profile_episodes SET rewatch_count = rewatch_count + 1 WHERE profile_id = ? AND episode_id = ?', (pid, ep_id))
                            elif pe:
                                cur.execute('UPDATE profile_episodes SET is_watched = 1, watched_at = ? WHERE profile_id = ? AND episode_id = ?', (now_str, pid, ep_id))
                            else:
                                cur.execute('INSERT INTO profile_episodes (profile_id, episode_id, show_id, is_watched, watched_at) VALUES (?, ?, ?, 1, ?)', (pid, ep_id, show_id, now_str))
                                
                            cur.execute('UPDATE episodes SET is_watched = 1, watched_at = ? WHERE id = ?', (now_str, ep_id))
                            con.commit()
                            self.send_json({"success": True, "action": "episode_scrobbled", "show": show_title, "season": season_num, "episode": ep_num})
                            return
                        else:
                            self.send_json({"warning": "Episode not found in show", "show_id": show_id}, 404)
                            return
                    else:
                        self.send_json({"warning": "Show not found in library", "show": show_title}, 404)
                        return

                # Handle movie scrobble
                elif item_type == "movie" and movie_title:
                    m_row = cur.execute('SELECT id FROM movies WHERE LOWER(title) = ?', (movie_title.lower(),)).fetchone()
                    if not m_row:
                        m_row = cur.execute('SELECT id FROM movies WHERE LOWER(title) LIKE ?', (f"%{movie_title.lower()}%",)).fetchone()
                    
                    if m_row:
                        m_id = m_row[0]
                        pm = cur.execute('SELECT is_watched, rewatch_count FROM profile_movies WHERE profile_id = ? AND movie_id = ?', (pid, m_id)).fetchone()
                        if pm and pm['is_watched'] == 1:
                            cur.execute('UPDATE profile_movies SET rewatch_count = rewatch_count + 1 WHERE profile_id = ? AND movie_id = ?', (pid, m_id))
                        elif pm:
                            cur.execute('UPDATE profile_movies SET is_watched = 1, status = "Watched", watched_at = ? WHERE profile_id = ? AND movie_id = ?', (now_str, pid, m_id))
                        else:
                            cur.execute('INSERT INTO profile_movies (profile_id, movie_id, is_watched, status, watched_at) VALUES (?, ?, 1, "Watched", ?)', (pid, m_id, now_str))
                            
                        cur.execute('UPDATE movies SET is_watched = 1, status = "Watched", watched_at = ? WHERE id = ?', (now_str, m_id))
                        con.commit()
                        self.send_json({"success": True, "action": "movie_scrobbled", "movie": movie_title})
                        return
                    else:
                        self.send_json({"warning": "Movie not found in library", "movie": movie_title}, 404)
                        return

                self.send_json({"warning": "Invalid payload format"}, 400)

            else:
                self.send_json({"error": "Unknown endpoint"}, 404)
        finally:
            con.close()

def main():
    os.makedirs(WEB_DIR, exist_ok=True)
    os.makedirs(MEDIA_DIR, exist_ok=True)
    with socketserver.TCPServer(("", PORT), PlotlineHandler) as httpd:
        print(f"Plotline Server running at http://localhost:{PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    main()
