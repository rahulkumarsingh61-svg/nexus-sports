from flask import Flask, render_template, jsonify
import requests
from bs4 import BeautifulSoup
import sqlite3
import time
from datetime import datetime, timezone

app = Flask(__name__)
DB_FILE = "cricket.db"
THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id TEXT PRIMARY KEY,
            series TEXT,
            status TEXT,
            stage TEXT,
            timestamp INTEGER,
            venue TEXT,
            date_str TEXT,
            team_a_name TEXT,
            team_a_score TEXT,
            team_b_name TEXT,
            team_b_score TEXT,
            live_text TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/matches")
def api_matches():
    matches = []
    seen = set()

    try:
        url = "https://m.cricbuzz.com/api/cricket-match/live-matches"
        res = requests.get(url, headers=HEADERS, timeout=10)
        data = res.json()
        
        for tm in data.get("typeMatches", []):
            for sm in tm.get("seriesMatches", []):
                series_name = sm.get("seriesAdWrapper", {}).get("seriesName", "Cricket Series")
                for m in sm.get("seriesAdWrapper", {}).get("matches", []):
                    info = m.get("matchInfo", {})
                    m_id = "cb-" + str(info.get("matchId"))
                    if m_id in seen: continue
                    seen.add(m_id)

                    state = info.get("state")
                    status = "past"
                    if state in ["In Progress", "Rain", "Stumps"]: status = "live"
                    elif state in ["Upcoming", "preview", "Toss"]: status = "future"

                    sc = m.get("matchScore", {})
                    s1 = sc.get("team1Score", {}).get("inngs1", {})
                    s2 = sc.get("team2Score", {}).get("inngs1", {})
                    score_a = f"{s1.get('runs')}/{s1.get('wickets', 10)}" if s1.get("runs") is not None else "-"
                    score_b = f"{s2.get('runs')}/{s2.get('wickets', 10)}" if s2.get("runs") is not None else "-"

                    home = info.get("team1", {}).get("teamName", "Team 1")
                    away = info.get("team2", {}).get("teamName", "Team 2")
                    start_ts = int(info.get("startDate", time.time() * 1000))

                    match_obj = {
                        "id": m_id,
                        "sport": "cricket",
                        "status": status,
                        "stage": info.get("matchDesc", ""),
                        "timestamp": start_ts,
                        "isStumpsOrDelayed": state in ["Stumps", "Rain"],
                        "series": series_name,
                        "venue": info.get("venueInfo", {}).get("ground", "Cricket Ground"),
                        "dateStr": datetime.fromtimestamp(start_ts / 1000, timezone.utc).strftime("%b %d, %Y, %I:%M %p"),
                        "teamA": {"name": home, "score": score_a, "logo": f"https://images.cricbuzz.com/i1/c{info.get('team1', {}).get('imageId', 0)}/i.jpg"},
                        "teamB": {"name": away, "score": score_b, "logo": f"https://images.cricbuzz.com/i1/c{info.get('team2', {}).get('imageId', 0)}/i.jpg"},
                        "liveText": info.get("status", "Live In Play")
                    }
                    matches.append(match_obj)

                    if status == "past":
                        save_to_db(match_obj)
    except Exception as e:
        print("Error:", e)

    for m in load_from_db():
        if m["id"] not in seen:
            seen.add(m["id"])
            matches.append(m)

    matches.sort(key=lambda x: x["timestamp"], reverse=True)
    return jsonify({"success": True, "count": len(matches), "matches": matches})

def save_to_db(m):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
        m["id"], m["series"], m["status"], m["stage"], m["timestamp"],
        m["venue"], m["dateStr"], m["teamA"]["name"], m["teamA"]["score"],
        m["teamB"]["name"], m["teamB"]["score"], m["liveText"]
    ))
    conn.commit()
    conn.close()

def load_from_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    since = int((time.time() * 1000) - THIRTY_DAYS_MS)
    cur.execute("SELECT * FROM matches WHERE timestamp >= ?", (since,))
    rows = cur.fetchall()
    conn.close()

    return [{
        "id": r[0], "sport": "cricket", "status": r[2], "stage": r[3],
        "timestamp": r[4], "venue": r[5], "dateStr": r[6],
        "teamA": {"name": r[7], "score": r[8], "logo": "https://flagcdn.com/w40/un.png"},
        "teamB": {"name": r[9], "score": r[10], "logo": "https://flagcdn.com/w40/un.png"},
        "liveText": r[11], "series": r[1], "isStumpsOrDelayed": False
    } for r in rows]

if __name__ == "__main__":
    app.run(port=5000)
