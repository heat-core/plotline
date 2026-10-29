import sqlite3
import os
import re
from datetime import datetime

VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.m4v'}

def calculate_badges(con, profile_id=1):
    cur = con.cursor()
    
    # 1. Total watched episodes for this profile
    ep_count = cur.execute('''
    SELECT COUNT(*) FROM profile_episodes WHERE profile_id = ? AND is_watched = 1
    ''', (profile_id,)).fetchone()[0] or 0
    
    # 2. Total watched movies for this profile
    movie_count = cur.execute('''
    SELECT COUNT(*) FROM profile_movies WHERE profile_id = ? AND is_watched = 1
    ''', (profile_id,)).fetchone()[0] or 0
    
    # 3. Total rewatches for this profile
    ep_rewatches = cur.execute('''
    SELECT SUM(rewatch_count) FROM profile_episodes WHERE profile_id = ?
    ''', (profile_id,)).fetchone()[0] or 0
    m_rewatches = cur.execute('''
    SELECT SUM(rewatch_count) FROM profile_movies WHERE profile_id = ?
    ''', (profile_id,)).fetchone()[0] or 0
    total_rewatches = ep_rewatches + m_rewatches
    
    # 4. Total shows tracked in library
    show_count = cur.execute('SELECT COUNT(*) FROM shows').fetchone()[0] or 0

    # 5. Anime count heuristic for this profile
    anime_count = cur.execute('''
    SELECT COUNT(*) FROM profile_episodes pe
    JOIN episodes e ON pe.episode_id = e.id
    JOIN shows s ON e.show_id = s.id
    WHERE pe.profile_id = ? AND pe.is_watched = 1 AND (
        LOWER(s.title) LIKE '%anime%' OR LOWER(s.title) LIKE '%pokemon%' OR 
        LOWER(s.title) LIKE '%reincarnated%' OR LOWER(s.title) LIKE '%mushoku%' OR
        LOWER(s.title) LIKE '%classroom%' OR LOWER(s.title) LIKE '%sword art%' OR
        LOWER(s.title) LIKE '%link click%'
    )
    ''', (profile_id,)).fetchone()[0] or 0

    badges = [
        {
            "id": "century_club",
            "title": "باشگاه صدتایی‌ها",
            "title_en": "Century Club",
            "icon": "💯",
            "desc": "تماشای حداقل ۱۰۰ قسمت از سریال‌ها",
            "desc_en": "Watch at least 100 TV episodes",
            "unlocked": ep_count >= 100,
            "progress": min(ep_count, 100),
            "goal": 100
        },
        {
            "id": "series_royalty",
            "title": "سلطان سریال",
            "title_en": "Series Royalty",
            "icon": "👑",
            "desc": "تماشای بیش از ۵۰۰ قسمت سریال",
            "desc_en": "Watch over 500 TV episodes",
            "unlocked": ep_count >= 500,
            "progress": min(ep_count, 500),
            "goal": 500
        },
        {
            "id": "millennium_master",
            "title": "استاد هزاره",
            "title_en": "Millennium Master",
            "icon": "🌌",
            "desc": "تماشای بیش از ۱,۰۰۰ قسمت سریال و انیمه",
            "desc_en": "Watch over 1,000 episodes of shows and anime",
            "unlocked": ep_count >= 1000,
            "progress": min(ep_count, 1000),
            "goal": 1000
        },
        {
            "id": "cinephile",
            "title": "عاشق سینما",
            "title_en": "Cinephile",
            "icon": "🍿",
            "desc": "تماشای حداقل ۵ فیلم سینمایی",
            "desc_en": "Watch at least 5 feature films",
            "unlocked": movie_count >= 5,
            "progress": min(movie_count, 5),
            "goal": 5
        },
        {
            "id": "anime_sensei",
            "title": "استاد انیمه",
            "title_en": "Anime Sensei",
            "icon": "⛩️",
            "desc": "تماشای بیش از ۵۰ قسمت انیمه ژاپنی",
            "desc_en": "Watch over 50 episodes of anime",
            "unlocked": anime_count >= 50,
            "progress": min(anime_count, 50),
            "goal": 50
        },
        {
            "id": "rewatch_fanatic",
            "title": "عاشق بازبینی",
            "title_en": "Rewatch Fanatic",
            "icon": "🔁",
            "desc": "حداقل ۵ بار بازبینی فیلم یا قسمت‌ها",
            "desc_en": "Rewatch episodes or movies at least 5 times",
            "unlocked": total_rewatches >= 5,
            "progress": min(total_rewatches, 5),
            "goal": 5
        },
        {
            "id": "collector",
            "title": "آرشیودار حرفه‌ای",
            "title_en": "Media Collector",
            "icon": "📚",
            "desc": "ردیابی حداقل ۱۰ سریال فعال در پلات‌لاین",
            "desc_en": "Track at least 10 active shows in Plotline",
            "unlocked": show_count >= 10,
            "progress": min(show_count, 10),
            "goal": 10
        },
        {
            "id": "marathoner",
            "title": "دونده ماراتن",
            "title_en": "The Marathoner",
            "icon": "🏃",
            "desc": "تماشای بی‌وقفه و متمرکز چند فصل سریال",
            "desc_en": "Power through multiple seasons in binge sessions",
            "unlocked": ep_count >= 200,
            "progress": min(ep_count, 200),
            "goal": 200
        }
    ]

    return badges

def clean_media_filename(filename):
    """
    Cleans release tags like 1080p, x265, BluRay from filenames.
    """
    base = os.path.splitext(filename)[0]
    # Replace dots and underscores with spaces
    cleaned = base.replace('.', ' ').replace('_', ' ').replace('-', ' ')
    # Remove common video noise tags
    noise_patterns = [
        r'\b1080p\b', r'\b720p\b', r'\b2160p\b', r'\b4k\b', r'\bbluray\b', r'\bweb-dl\b',
        r'\bwebrip\b', r'\bhdtv\b', r'\bx264\b', r'\bx265\b', r'\bhevc\b', r'\b10bit\b',
        r'\baac\b', r'\byify\b', r'\byts\b', r'\brls\b', r'\bdvdrip\b', r'\bproper\b'
    ]
    for pattern in noise_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
    # Extract possible year
    year_match = re.search(r'\b(19\d\d|20\d\d)\b', cleaned)
    year = int(year_match.group(1)) if year_match else None
    if year:
        # Title is usually before year
        cleaned = cleaned[:cleaned.find(str(year))].strip()

    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned, year

def scan_local_folder(folder_path, con):
    """
    Scans a user's directory on PC/NAS, finds untracked video files, and suggests them.
    """
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        return {"error": "پوشه یافت نشد یا دسترسی مجاز نیست."}

    cur = con.cursor()
    # Get all movie titles already tracked
    existing_movies = {r[0].lower() for r in cur.execute('SELECT title FROM movies').fetchall()}
    existing_shows = {r[0].lower() for r in cur.execute('SELECT title FROM shows').fetchall()}

    found_files = []
    
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                full_path = os.path.join(root, f)
                size_mb = round(os.path.getsize(full_path) / (1024 * 1024), 1)
                
                # Check if file size is plausible for movie or episode (> 150 MB)
                if size_mb > 100:
                    cleaned_title, year = clean_media_filename(f)
                    if len(cleaned_title) >= 2:
                        is_tracked = (cleaned_title.lower() in existing_movies) or (cleaned_title.lower() in existing_shows)
                        found_files.append({
                            "raw_filename": f,
                            "full_path": full_path,
                            "cleaned_title": cleaned_title,
                            "year": year or 2024,
                            "size_mb": size_mb,
                            "is_already_tracked": is_tracked
                        })

    return {"total_scanned": len(found_files), "items": found_files[:40]}
