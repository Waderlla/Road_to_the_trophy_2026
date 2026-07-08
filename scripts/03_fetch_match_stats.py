import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from api_client import get
from db import get_connection

FINISHED_STATUSES = ("FT", "AET", "PEN")


def stat_value(stats_list, key, default=None):
    for s in stats_list:
        if s["type"] == key:
            return s["value"]
    return default


def to_int(value, default=0):
    if value is None:
        return default
    if isinstance(value, str) and value.endswith("%"):
        value = value[:-1]
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def to_float(value, default=None):
    if value is None:
        return default
    if isinstance(value, str) and value.endswith("%"):
        value = value[:-1]
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def upsert_stats(cur, match_id, team_id, goals, stats_list):
    cur.execute(
        """
        INSERT INTO team_match_stats (
            match_id, team_id, goals,
            shots_total, shots_on_goal, shots_off_goal, shots_blocked,
            shots_inside_box, shots_outside_box,
            possession_pct, passes_total, passes_accurate, passes_pct,
            fouls, corners, offsides, yellow_cards, red_cards,
            goalkeeper_saves, expected_goals, goals_prevented
        ) VALUES (%s,%s,%s, %s,%s,%s,%s, %s,%s, %s,%s,%s,%s, %s,%s,%s,%s,%s, %s,%s,%s)
        ON CONFLICT (match_id, team_id) DO UPDATE SET
            goals = EXCLUDED.goals,
            shots_total = EXCLUDED.shots_total,
            shots_on_goal = EXCLUDED.shots_on_goal,
            possession_pct = EXCLUDED.possession_pct
        """,
        (
            match_id, team_id, goals,
            to_int(stat_value(stats_list, "Total Shots")),
            to_int(stat_value(stats_list, "Shots on Goal")),
            to_int(stat_value(stats_list, "Shots off Goal")),
            to_int(stat_value(stats_list, "Blocked Shots")),
            to_int(stat_value(stats_list, "Shots insidebox")),
            to_int(stat_value(stats_list, "Shots outsidebox")),
            to_float(stat_value(stats_list, "Ball Possession")),
            to_int(stat_value(stats_list, "Total passes")),
            to_int(stat_value(stats_list, "Passes accurate")),
            to_float(stat_value(stats_list, "Passes %")),
            to_int(stat_value(stats_list, "Fouls")),
            to_int(stat_value(stats_list, "Corner Kicks")),
            to_int(stat_value(stats_list, "Offsides")),
            to_int(stat_value(stats_list, "Yellow Cards")),
            to_int(stat_value(stats_list, "Red Cards")),
            to_int(stat_value(stats_list, "Goalkeeper Saves")),
            to_float(stat_value(stats_list, "expected_goals")),
            to_float(stat_value(stats_list, "goals_prevented")),
        ),
    )


def main():
    conn = get_connection()
    fetched = 0
    skipped = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.match_id, m.api_fixture_id, m.home_team_id, m.away_team_id,
                       m.home_goals, m.away_goals, t_home.api_team_id, t_away.api_team_id
                FROM matches m
                JOIN teams t_home ON t_home.team_id = m.home_team_id
                JOIN teams t_away ON t_away.team_id = m.away_team_id
                WHERE m.status IN %s AND m.source = 'api'
                AND NOT EXISTS (
                    SELECT 1 FROM team_match_stats s WHERE s.match_id = m.match_id
                )
                ORDER BY m.match_id
                """,
                (FINISHED_STATUSES,),
            )
            rows = cur.fetchall()

            for match_id, api_fixture_id, home_id, away_id, home_goals, away_goals, home_api_team_id, away_api_team_id in rows:
                print(f"Pobieram statystyki meczu {api_fixture_id}...")
                data = get("fixtures/statistics", {"fixture": api_fixture_id})

                if data.get("errors") or not data.get("response"):
                    print("  Pomijam - brak danych lub blad API.")
                    skipped += 1
                    continue

                goals_by_api_team = {home_api_team_id: home_goals, away_api_team_id: away_goals}
                team_id_by_api = {home_api_team_id: home_id, away_api_team_id: away_id}

                for team_stats in data["response"]:
                    api_tid = team_stats["team"]["id"]
                    tid = team_id_by_api.get(api_tid)
                    upsert_stats(cur, match_id, tid, goals_by_api_team.get(api_tid), team_stats["statistics"])

                conn.commit()
                fetched += 1
    finally:
        conn.close()

    print(f"\nGotowe. Pobrano statystyki {fetched} meczow, pominieto {skipped}.")


if __name__ == "__main__":
    main()
