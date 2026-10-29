import urllib.request
import urllib.parse
import json
import os
import hashlib
import re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, "data", "media")
POSTERS_DIR = os.path.join(MEDIA_DIR, "posters")
BACKDROPS_DIR = os.path.join(MEDIA_DIR, "backdrops")

os.makedirs(POSTERS_DIR, exist_ok=True)
os.makedirs(BACKDROPS_DIR, exist_ok=True)

USER_AGENT = "Plotline/1.0 (Self-Hosted Media Tracker)"

def clean_html_tags(text):
    if not text:
        return ""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()

def cache_image(url, subfolder="posters", force_download=False, cache_mode="stream"):
    """
    Hybrid Image Handler:
    - If cache_mode is 'stream' and not force_download: returns original remote URL (saves disk space).
    - If cache_mode is 'download' or force_download: downloads image to disk for 100% offline access.
    """
    if not url or not url.startswith("http"):
        return url

    if cache_mode == "stream" and not force_download:
        return url

    try:
        ext = ".jpg"
        if ".png" in url.lower():
            ext = ".png"
        elif ".webp" in url.lower():
            ext = ".webp"

        url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
        filename = f"{url_hash}{ext}"
        target_dir = os.path.join(MEDIA_DIR, subfolder)
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, filename)

        if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
            return f"/media/{subfolder}/{filename}"

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=8) as resp:
            content = resp.read()
            with open(target_path, "wb") as f:
                f.write(content)

        return f"/media/{subfolder}/{filename}"
    except Exception as e:
        return url

def get_media_storage_stats():
    """
    Calculates total cached files and disk space used.
    """
    total_bytes = 0
    total_files = 0
    if os.path.exists(MEDIA_DIR):
        for root, dirs, files in os.walk(MEDIA_DIR):
            for f in files:
                p = os.path.join(root, f)
                total_bytes += os.path.getsize(p)
                total_files += 1

    mb = round(total_bytes / (1024 * 1024), 2)
    return {"total_files": total_files, "total_mb": mb}

def get_pending_download_stats(con):
    """
    Calculates number of uncached posters in library and estimated download size in MB.
    """
    cur = con.cursor()
    shows_uncached = cur.execute("SELECT COUNT(*) FROM shows WHERE poster_url LIKE 'http%'").fetchone()[0] or 0
    movies_uncached = cur.execute("SELECT COUNT(*) FROM movies WHERE poster_url LIKE 'http%'").fetchone()[0] or 0
    total_uncached = shows_uncached + movies_uncached
    # Average compressed poster is ~180 KB (0.18 MB)
    estimated_mb = round(total_uncached * 0.18, 1)
    return {
        "uncached_count": total_uncached,
        "shows_uncached": shows_uncached,
        "movies_uncached": movies_uncached,
        "estimated_mb": estimated_mb
    }

def search_anime_jikan(query):
    """
    Searches MyAnimeList database via Jikan API v4.
    Free, no API key required.
    Integrates seamlessly into shows and movies without a separate tab.
    """
    if not query or len(query.strip()) < 2:
        return []

    encoded = urllib.parse.quote(query.strip())
    url = f"https://api.jikan.moe/v4/anime?q={encoded}&limit=8"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        results = []
        for item in data.get("data", []):
            is_movie = (item.get("type") or "").lower() == "movie"
            img_dict = item.get("images", {}).get("jpg", {})
            poster_url = img_dict.get("large_image_url") or img_dict.get("image_url") or ""
            aired_from = (item.get("aired", {}).get("from") or "")[:4]
            runtime_raw = item.get("duration") or ""
            runtime_mins = 24
            if "min" in runtime_raw:
                try:
                    runtime_mins = int(re.search(r'(\d+)\s*min', runtime_raw).group(1))
                except:
                    pass

            results.append({
                "source": "jikan",
                "mal_id": item.get("mal_id"),
                "type": "movie" if is_movie else "show",
                "title": item.get("title") or item.get("title_english") or "Anime",
                "genres": [g.get("name") for g in item.get("genres", [])],
                "network": "TV (Anime)" if not is_movie else "Anime Movie",
                "premiered": aired_from,
                "release_year": aired_from or "2024",
                "rating": item.get("score"),
                "overview": clean_html_tags(item.get("synopsis")),
                "poster_url": poster_url,
                "runtime": runtime_mins,
                "total_episodes": item.get("episodes") or 12
            })
        return results
    except Exception as e:
        print(f"[Plotline Metadata] Note: Jikan API lookup skipped ({e})")
        return []

def search_tvmaze_shows(query):
    if not query or len(query.strip()) < 2:
        return []

    encoded = urllib.parse.quote(query.strip())
    url = f"https://api.tvmaze.com/search/shows?q={encoded}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        results = []
        for item in data:
            show = item.get("show", {})
            img = show.get("image") or {}
            poster_url = img.get("medium") or img.get("original") or ""

            results.append({
                "source": "tvmaze",
                "id": show.get("id"),
                "title": show.get("name"),
                "genres": show.get("genres", []),
                "network": (show.get("network") or show.get("webChannel") or {}).get("name", "TV"),
                "status": show.get("status"),
                "premiered": show.get("premiered", ""),
                "rating": (show.get("rating") or {}).get("average"),
                "overview": clean_html_tags(show.get("summary")),
                "poster_url": poster_url,
                "runtime": show.get("runtime") or show.get("averageRuntime") or 45
            })
        return results
    except Exception as e:
        print(f"[Plotline Metadata] Error searching TVMaze: {e}")
        return []

def fetch_tvmaze_episodes(show_id):
    url = f"https://api.tvmaze.com/shows/{show_id}/episodes"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            episodes = json.loads(resp.read().decode('utf-8'))
        return episodes
    except Exception as e:
        print(f"[Plotline Metadata] Error fetching episodes for show {show_id}: {e}")
        return []

def search_movies_open(query, tmdb_api_key=None):
    if not query or len(query.strip()) < 2:
        return []

    if tmdb_api_key:
        try:
            encoded = urllib.parse.quote(query.strip())
            url = f"https://api.themoviedb.org/3/search/movie?api_key={tmdb_api_key}&query={encoded}&language=fa-IR"
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            
            results = []
            for m in data.get("results", []):
                p_path = m.get("poster_path")
                b_path = m.get("backdrop_path")
                results.append({
                    "source": "tmdb",
                    "id": m.get("id"),
                    "title": m.get("title") or m.get("original_title"),
                    "release_year": (m.get("release_date") or "2024")[:4],
                    "overview": m.get("overview") or "",
                    "poster_url": f"https://image.tmdb.org/t/p/w500{p_path}" if p_path else "",
                    "backdrop_url": f"https://image.tmdb.org/t/p/w1280{b_path}" if b_path else "",
                    "rating": m.get("vote_average"),
                    "runtime": 120
                })
            return results
        except Exception as e:
            print(f"[Plotline Metadata] Error searching TMDB: {e}")

    return [
        {
            "source": "manual",
            "id": None,
            "title": query.strip().title(),
            "release_year": datetime.now().year,
            "overview": f"Movie entry for {query.strip().title()}",
            "poster_url": "",
            "runtime": 120
        }
    ]

def get_featured_titles():
    """
    Returns popular/trending starter titles for the Discover tab.
    """
    return [
        {
            "type": "show",
            "source": "tvmaze",
            "id": 169,
            "title": "Breaking Bad",
            "genres": ["Drama", "Crime", "Thriller"],
            "network": "AMC",
            "premiered": "2008-01-20",
            "rating": 9.5,
            "overview": "A high school chemistry teacher diagnosed with inoperable lung cancer turns to manufacturing and selling methamphetamine.",
            "poster_url": "https://static.tvmaze.com/uploads/images/medium_portrait/0/2400.jpg",
            "runtime": 47
        },
        {
            "type": "show",
            "source": "tvmaze",
            "id": 43534,
            "title": "Arcane",
            "genres": ["Animation", "Action", "Fantasy"],
            "network": "Netflix",
            "premiered": "2021-11-06",
            "rating": 9.0,
            "overview": "Set in the utopian region of Piltover and the oppressed underground of Zaun, the story follows the origins of two iconic League champions.",
            "poster_url": "https://static.tvmaze.com/uploads/images/medium_portrait/531/1328906.jpg",
            "runtime": 41
        },
        {
            "type": "show",
            "source": "tvmaze",
            "id": 36711,
            "title": "Shōgun",
            "genres": ["Drama", "History", "War"],
            "network": "FX",
            "premiered": "2024-02-27",
            "rating": 8.7,
            "overview": "Lord Yoshii Toranaga discovers secrets that could tip the scales of power in feudal Japan when a mysterious European ship is found marooned.",
            "poster_url": "https://static.tvmaze.com/uploads/images/medium_portrait/504/1262446.jpg",
            "runtime": 60
        },
        {
            "type": "show",
            "source": "tvmaze",
            "id": 2993,
            "title": "Stranger Things",
            "genres": ["Drama", "Fantasy", "Science-Fiction"],
            "network": "Netflix",
            "premiered": "2016-07-15",
            "rating": 8.6,
            "overview": "When a young boy vanishes, a small town uncovers a mystery involving secret experiments, terrifying supernatural forces and one strange little girl.",
            "poster_url": "https://static.tvmaze.com/uploads/images/medium_portrait/394/987114.jpg",
            "runtime": 51
        },
        {
            "type": "movie",
            "source": "tmdb",
            "id": 157336,
            "title": "Interstellar",
            "release_year": "2014",
            "overview": "A team of explorers travel through a wormhole in space in an attempt to ensure humanity's survival.",
            "poster_url": "https://image.tmdb.org/t/p/w500/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg",
            "rating": 8.4,
            "runtime": 169
        },
        {
            "type": "movie",
            "source": "tmdb",
            "id": 693134,
            "title": "Dune: Part Two",
            "release_year": "2024",
            "overview": "Follow the mythic journey of Paul Atreides as he unites with Chani and the Fremen while on a path of revenge.",
            "poster_url": "https://image.tmdb.org/t/p/w500/1pdfLvkbY9ohJlCjQH2CZjjYVvJ.jpg",
            "rating": 8.2,
            "runtime": 166
        }
    ]
