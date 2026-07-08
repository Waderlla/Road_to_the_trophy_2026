import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import get_connection

ROOT = Path(__file__).resolve().parent.parent
HTML_DIR = ROOT / "data" / "historical_html"

WARSAW = ZoneInfo("Europe/Warsaw")

# FotMob leagueRoundName -> nasz kanoniczny etap turnieju
STAGE_MAP = {
    "1/16": "R32",
    "1/8": "R16",
    "1/4": "QF",
    "1/2": "SF",
    "Final": "final",
    "3rd Place": "third_place",
}

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)

# klucz FotMob -> kolumna w team_match_stats
KEY_MAP = {
    "BallPossesion": "possession_pct",
    "total_shots": "shots_total",
    "ShotsOnTarget": "shots_on_goal",
    "ShotsOffTarget": "shots_off_goal",
    "blocked_shots": "shots_blocked",
    "shots_inside_box": "shots_inside_box",
    "shots_outside_box": "shots_outside_box",
    "passes": "passes_total",
    "fouls": "fouls",
    "corners": "corners",
    "Offsides": "offsides",
    "yellow_cards": "yellow_cards",
    "red_cards": "red_cards",
    "keeper_saves": "goalkeeper_saves",
    "expected_goals": "expected_goals",
}


def parse_main_value(raw):
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)", str(raw))
    return float(m.group(1)) if m else None


def parse_percent(raw):
    if raw is None:
        return None
    m = re.search(r"\((\d+)%\)", str(raw))
    return float(m.group(1)) if m else None


def extract_next_data(html_text):
    m = NEXT_DATA_RE.search(html_text)
    if not m:
        return None
    return json.loads(m.group(1))


def parse_match(data):
    page_props = data["props"]["pageProps"]
    general = page_props["general"]
    header = page_props["header"]

    home_name = general["homeTeam"]["name"]
    away_name = general["awayTeam"]["name"]

    # FotMob zapisuje grupe w nazwie ligi, np. "World Cup Grp. C"; dla fazy
    # pucharowej tego nie ma, wiec group zostanie None.
    group_match = re.search(r"Grp\.\s*([A-Z])", general.get("leagueName") or "")
    group = group_match.group(1) if group_match else None
    stage = "group" if group else STAGE_MAP.get(general.get("leagueRoundName"), general.get("leagueRoundName"))

    home_goals = header["teams"][0]["score"]
    away_goals = header["teams"][1]["score"]

    # Przy remisie po dogrywce o zwyciezcy decyduja karne - FotMob podaje
    # nazwe druzyny, ktora je przegrala (whoLostOnPenalties), bez tego
    # remisowy wynik nie pozwolilby ustalic, kto naprawde awansowal dalej.
    penalty_loser_name = header["status"].get("whoLostOnPenalties") or None

    # FotMob zwraca np. "Pen" (mala litera) dla karnych, a reszta kodu wszedzie
    # porownuje status wielkimi literami ("FT","AET","PEN") - bez ujednolicenia
    # takie mecze byly po cichu traktowane jako nierozstrzygniete.
    status_short = header["status"]["reason"]["short"].upper()
    match_date = datetime.fromisoformat(general["matchTimeUTCDate"].replace("Z", "+00:00"))

    stat_groups = page_props["content"]["stats"]["Periods"]["All"]["stats"]
    home_stats, away_stats = {}, {}
    for stat_group in stat_groups:
        for item in stat_group.get("stats", []):
            key = item.get("key")
            values = item.get("stats")
            if not values or values[0] is None:
                continue
            home_raw, away_raw = values[0], values[1]

            if key == "accurate_passes":
                home_stats["passes_accurate"] = parse_main_value(home_raw)
                away_stats["passes_accurate"] = parse_main_value(away_raw)
                home_stats["passes_pct"] = parse_percent(home_raw)
                away_stats["passes_pct"] = parse_percent(away_raw)
                continue

            column = KEY_MAP.get(key)
            if not column:
                continue
            home_stats[column] = parse_main_value(home_raw)
            away_stats[column] = parse_main_value(away_raw)

    return {
        "home_name": home_name,
        "away_name": away_name,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "status": status_short,
        "match_date": match_date,
        "group": group,
        "stage": stage,
        "penalty_loser_name": penalty_loser_name,
        "home_stats": home_stats,
        "away_stats": away_stats,
    }


def upsert_team(cur, name, group=None):
    cur.execute(
        """
        INSERT INTO teams (name, group_name) VALUES (%s, %s)
        ON CONFLICT (name) DO UPDATE SET
            group_name = COALESCE(EXCLUDED.group_name, teams.group_name)
        RETURNING team_id
        """,
        (name, group),
    )
    return cur.fetchone()[0]


def resolve_winner(home_id, away_id, home_goals, away_goals, home_name, away_name, penalty_loser_name):
    if home_goals > away_goals:
        return home_id
    if away_goals > home_goals:
        return away_id
    # remis w regulaminowym czasie - o zwyciestwie zdecydowaly karne
    if penalty_loser_name == home_name:
        return away_id
    if penalty_loser_name == away_name:
        return home_id
    return None


def find_or_create_match(
    cur, match_date, home_id, away_id, home_goals, away_goals, status, stage,
    home_name, away_name, penalty_loser_name,
):
    winner_team_id = resolve_winner(home_id, away_id, home_goals, away_goals, home_name, away_name, penalty_loser_name)

    # match_date::date w bazie liczy sie wg sesyjnej strefy czasowej (Europe/Warsaw,
    # patrz db.py) - trzeba porownywac dzien tez wg tej strefy, inaczej mecze kolo
    # polnocy UTC daja inny dzien i tworza duplikaty zamiast trafiac w istniejacy rekord.
    local_date = match_date.astimezone(WARSAW).date()
    cur.execute(
        """
        SELECT match_id FROM matches
        WHERE home_team_id = %s AND away_team_id = %s
        AND match_date::date = %s AND source = 'manual_html'
        """,
        (home_id, away_id, local_date),
    )
    row = cur.fetchone()
    if row:
        match_id = row[0]
        cur.execute(
            """UPDATE matches SET home_goals = %s, away_goals = %s, status = %s, stage = %s,
               winner_team_id = %s WHERE match_id = %s""",
            (home_goals, away_goals, status, stage, winner_team_id, match_id),
        )
        return match_id

    cur.execute(
        """
        INSERT INTO matches (
            match_date, home_team_id, away_team_id,
            home_goals, away_goals, winner_team_id, status, source, stage
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'manual_html', %s)
        RETURNING match_id
        """,
        (match_date, home_id, away_id, home_goals, away_goals, winner_team_id, status, stage),
    )
    return cur.fetchone()[0]


def upsert_stats(cur, match_id, team_id, goals, stats):
    if not stats:
        return
    columns = ["goals"] + list(stats.keys())
    values = [goals] + list(stats.values())
    placeholders = ", ".join(["%s"] * len(values))
    col_list = ", ".join(columns)
    update_list = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns)

    cur.execute(
        f"""
        INSERT INTO team_match_stats (match_id, team_id, {col_list})
        VALUES (%s, %s, {placeholders})
        ON CONFLICT (match_id, team_id) DO UPDATE SET {update_list}
        """,
        [match_id, team_id] + values,
    )


def process_html_file(cur, html_path):
    html_text = html_path.read_text(encoding="utf-8", errors="ignore")
    data = extract_next_data(html_text)
    if not data:
        print(f"  [BLAD] nie znaleziono __NEXT_DATA__ w {html_path.name}")
        return False

    match = parse_match(data)
    home_id = upsert_team(cur, match["home_name"], match["group"])
    away_id = upsert_team(cur, match["away_name"], match["group"])
    match_id = find_or_create_match(
        cur, match["match_date"], home_id, away_id,
        match["home_goals"], match["away_goals"], match["status"], match["stage"],
        match["home_name"], match["away_name"], match["penalty_loser_name"],
    )
    upsert_stats(cur, match_id, home_id, match["home_goals"], match["home_stats"])
    upsert_stats(cur, match_id, away_id, match["away_goals"], match["away_stats"])

    print(
        f"  OK: {match['home_name']} {match['home_goals']}-{match['away_goals']} "
        f"{match['away_name']} ({match['match_date'].date()}) "
        f"[{len(match['home_stats'])} pol statystyk]"
    )
    return True


def main():
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    html_files = sorted(HTML_DIR.glob("*.html"))

    if not html_files:
        print(f"Brak plikow HTML w {HTML_DIR}. Zapisz tam strony meczow (Ctrl+S) i uruchom ponownie.")
        return

    conn = get_connection()
    ok, failed = 0, 0
    try:
        with conn.cursor() as cur:
            for html_path in html_files:
                print(f"Przetwarzam {html_path.name}...")
                try:
                    if process_html_file(cur, html_path):
                        conn.commit()
                        ok += 1
                    else:
                        conn.rollback()
                        failed += 1
                except Exception as e:
                    conn.rollback()
                    print(f"  [BLAD] {type(e).__name__}: {e}")
                    failed += 1
    finally:
        conn.close()

    print(f"\nGotowe. Zaimportowano {ok} meczow, {failed} nieudanych.")


if __name__ == "__main__":
    main()
