import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from api_client import get
from db import get_connection

WARSAW = ZoneInfo("Europe/Warsaw")

# API-Football "round" (tekst) -> nasz kanoniczny etap turnieju (ten sam,
# ktorego uzywa 04_import_fotmob_html.py)
STAGE_KEYWORDS = [
    ("Group Stage", "group"),
    ("Round of 32", "R32"),
    ("Round of 16", "R16"),
    ("Quarter", "QF"),
    ("Semi", "SF"),
    ("3rd Place", "third_place"),
    ("Final", "final"),
]


def normalize_stage(round_text):
    if not round_text:
        return None
    for keyword, stage in STAGE_KEYWORDS:
        if keyword.lower() in round_text.lower():
            return stage
    return round_text


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def date_already_final(cur, d):
    cur.execute(
        """
        SELECT count(*),
               count(*) FILTER (WHERE status NOT IN ('FT','AET','PEN'))
        FROM matches
        WHERE match_date::date = %s AND source = 'api'
        """,
        (d,),
    )
    total, unfinished = cur.fetchone()
    return total > 0 and unfinished == 0


def upsert_team(cur, api_team_id, name, logo_url):
    # Najpierw szukamy po api_team_id - API-Football i FotMob czasem inaczej
    # nazywaja te sama druzyne (np. "Congo DR" vs "DR Congo"), wiec dopasowanie
    # samej nazwy potrafi utworzyc duplikat. Gdy api_team_id juz jest znany,
    # zawsze trafiamy w ten sam wiersz bez wzgledu na to, jak API tego dnia
    # zapisze nazwe.
    cur.execute("SELECT team_id FROM teams WHERE api_team_id = %s", (api_team_id,))
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute(
        """
        INSERT INTO teams (name, api_team_id, logo_url)
        VALUES (%s, %s, %s)
        ON CONFLICT (name) DO UPDATE SET
            api_team_id = EXCLUDED.api_team_id,
            logo_url = EXCLUDED.logo_url
        RETURNING team_id
        """,
        (name, api_team_id, logo_url),
    )
    return cur.fetchone()[0]


def manual_html_duplicate_exists(cur, home_team_id, away_team_id, fixture_date_str):
    # Ten sam mecz mogl juz zostac wczesniej wgrany recznie z FotMob (source =
    # 'manual_html', np. gdy uzupelnialysmy zaleglosci) - bez tego sprawdzenia
    # codzienny fetch tworzylby dla niego drugi, zdublowany wiersz.
    match_date = datetime.fromisoformat(fixture_date_str)
    local_date = match_date.astimezone(WARSAW).date()
    cur.execute(
        """
        SELECT 1 FROM matches
        WHERE home_team_id = %s AND away_team_id = %s
        AND match_date::date = %s AND source = 'manual_html'
        """,
        (home_team_id, away_team_id, local_date),
    )
    return cur.fetchone() is not None


def upsert_match(cur, m, home_team_id, away_team_id):
    fixture = m["fixture"]
    teams = m["teams"]
    goals = m["goals"]
    league = m["league"]

    winner_team_id = None
    if teams["home"].get("winner") is True:
        winner_team_id = home_team_id
    elif teams["away"].get("winner") is True:
        winner_team_id = away_team_id

    cur.execute(
        """
        INSERT INTO matches (
            api_fixture_id, match_date, round, stage,
            home_team_id, away_team_id,
            home_goals, away_goals, winner_team_id,
            status, status_long, source
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'api')
        ON CONFLICT (api_fixture_id) DO UPDATE SET
            home_goals = EXCLUDED.home_goals,
            away_goals = EXCLUDED.away_goals,
            winner_team_id = EXCLUDED.winner_team_id,
            status = EXCLUDED.status,
            status_long = EXCLUDED.status_long,
            stage = EXCLUDED.stage
        """,
        (
            fixture["id"], fixture["date"], league.get("round"), normalize_stage(league.get("round")),
            home_team_id, away_team_id,
            goals["home"], goals["away"], winner_team_id,
            fixture["status"]["short"], fixture["status"]["long"],
        ),
    )


def main():
    # Darmowy plan API-Football udostepnia tylko waskie okno dat wokol "dzisiaj"
    # (blad "Free plans do not have access to this date" poza tym oknem), wiec
    # przy codziennej automatyzacji nie ma sensu odpytywac calego zakresu turnieju -
    # starsze dni i tak zawsze zostana odrzucone i tylko zmarnuja limit zapytan.
    end = date.today()
    start = max(date.fromisoformat(config.TOURNAMENT_START), end - timedelta(days=3))

    conn = get_connection()
    fetched = 0
    skipped = 0
    try:
        with conn.cursor() as cur:
            for d in daterange(start, end):
                if date_already_final(cur, d):
                    skipped += 1
                    continue

                print(f"Pobieram mecze z dnia {d.isoformat()}...")
                data = get("fixtures", {"date": d.isoformat()})

                if data.get("errors"):
                    print("  Pomijam ten dzien z powodu bledu API.")
                    continue

                wc_matches = [f for f in data["response"] if f["league"]["id"] == config.LEAGUE_ID]

                for m in wc_matches:
                    home_team_id = upsert_team(cur, m["teams"]["home"]["id"], m["teams"]["home"]["name"], m["teams"]["home"]["logo"])
                    away_team_id = upsert_team(cur, m["teams"]["away"]["id"], m["teams"]["away"]["name"], m["teams"]["away"]["logo"])
                    if manual_html_duplicate_exists(cur, home_team_id, away_team_id, m["fixture"]["date"]):
                        continue
                    upsert_match(cur, m, home_team_id, away_team_id)

                conn.commit()
                print(f"  zapisano {len(wc_matches)} meczow MS 2026 do bazy")
                fetched += 1
    finally:
        conn.close()

    print(f"\nGotowe. Pobrano/zaktualizowano {fetched} dni, pominieto {skipped} (juz kompletne w bazie).")


if __name__ == "__main__":
    main()
