#!/usr/bin/env python3
"""
Plotline — Offline-first TV & Movie Tracker
Main entry point and CLI runner.
"""

import sys
import os
import argparse
import webbrowser

def main():
    parser = argparse.ArgumentParser(
        description="Plotline: Self-hosted, offline-first TV and movie tracker with exact binge stats."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 'start' command (default)
    start_parser = subparsers.add_parser("start", help="Start the local Plotline web server")
    start_parser.add_argument("--port", type=int, default=8765, help="Port to run server on (default: 8765)")
    start_parser.add_argument("--no-browser", action="store_true", help="Do not automatically open the browser")

    # 'rescue' command
    rescue_parser = subparsers.add_parser("rescue", help="Rescue data from a TV Time .imazingapp container")
    rescue_parser.add_argument("archive", type=str, help="Path to .imazingapp archive")

    # 'backup' command
    backup_parser = subparsers.add_parser("backup", help="Export full database to JSON")
    backup_parser.add_argument("--out", type=str, default="plotline_backup.json", help="Output file path")

    args = parser.parse_args()

    if args.command == "rescue":
        import importers
        import database
        db_path = database.get_db_path()
        con = database.init_db(db_path)
        with open(args.archive, "r", encoding="utf-8") as fp:
            data = fp.read()
        res = importers.import_tvtime_json(data, con)
        con.close()
        print(f"[Success] History restored into Plotline database: {res}")

    elif args.command == "backup":
        import sqlite3, json
        import database
        db_path = database.get_db_path()
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        shows = [dict(s) for s in cur.execute('SELECT * FROM shows').fetchall()]
        eps = [dict(e) for e in cur.execute('SELECT * FROM episodes').fetchall()]
        movies = [dict(m) for m in cur.execute('SELECT * FROM movies').fetchall()]
        con.close()
        export_data = {"app": "Plotline", "shows": shows, "episodes": eps, "movies": movies}
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        print(f"[Success] Database exported to {args.out}")

    else:
        # Default: start server
        port = getattr(args, "port", 8765)
        no_browser = getattr(args, "no-browser", False)
        
        import server
        server.PORT = port
        
        print(f"===================================================")
        print(f"  Plotline Server starting at http://localhost:{port}")
        print(f"  Press Ctrl+C to stop the server.")
        print(f"===================================================")
        
        if not no_browser:
            webbrowser.open(f"http://localhost:{port}")
            
        import socketserver
        with socketserver.TCPServer(("", port), server.PlotlineHandler) as httpd:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\n[Plotline] Server stopped cleanly.")

if __name__ == "__main__":
    main()
