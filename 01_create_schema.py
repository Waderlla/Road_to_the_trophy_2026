import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import get_connection

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    team_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    api_team_id INTEGER UNIQUE,
    group_name TEXT,
    logo_url TEXT
);

CREATE TABLE IF NOT EXISTS matches (
    match_id SERIAL PRIMARY KEY,
    api_fixture_id BIGINT UNIQUE,
    match_date TIMESTAMPTZ NOT NULL,
    round TEXT,
    home_team_id INTEGER REFERENCES teams(team_id),
    away_team_id INTEGER REFERENCES teams(team_id),
    home_goals INTEGER,
    away_goals INTEGER,
    winner_team_id INTEGER REFERENCES teams(team_id),
    status TEXT,
    status_long TEXT,
    source TEXT NOT NULL DEFAULT 'api',
    stage TEXT
);

CREATE TABLE IF NOT EXISTS team_match_stats (
    match_id INTEGER REFERENCES matches(match_id),
    team_id INTEGER REFERENCES teams(team_id),
    goals INTEGER,
    shots_total INTEGER,
    shots_on_goal INTEGER,
    shots_off_goal INTEGER,
    shots_blocked INTEGER,
    shots_inside_box INTEGER,
    shots_outside_box INTEGER,
    possession_pct NUMERIC,
    passes_total INTEGER,
    passes_accurate INTEGER,
    passes_pct NUMERIC,
    fouls INTEGER,
    corners INTEGER,
    offsides INTEGER,
    yellow_cards INTEGER,
    red_cards INTEGER,
    goalkeeper_saves INTEGER,
    expected_goals NUMERIC,
    goals_prevented NUMERIC,
    PRIMARY KEY (match_id, team_id)
);

CREATE TABLE IF NOT EXISTS daily_strength (
    calc_date DATE NOT NULL,
    team_id INTEGER REFERENCES teams(team_id),
    matches_played INTEGER NOT NULL,
    attack NUMERIC NOT NULL,
    defense NUMERIC NOT NULL,
    control NUMERIC NOT NULL,
    efficiency NUMERIC NOT NULL,
    discipline NUMERIC NOT NULL,
    form NUMERIC NOT NULL,
    strength NUMERIC NOT NULL,
    PRIMARY KEY (calc_date, team_id)
);

CREATE TABLE IF NOT EXISTS daily_probability (
    calc_date DATE NOT NULL,
    team_id INTEGER REFERENCES teams(team_id),
    champion_probability NUMERIC NOT NULL,
    rank INTEGER NOT NULL,
    PRIMARY KEY (calc_date, team_id)
);

CREATE TABLE IF NOT EXISTS daily_opponent_distribution (
    calc_date DATE NOT NULL,
    team_id INTEGER REFERENCES teams(team_id),
    stage TEXT NOT NULL,
    opponent_id INTEGER REFERENCES teams(team_id),
    probability NUMERIC NOT NULL,
    PRIMARY KEY (calc_date, team_id, stage, opponent_id)
);

-- Oficjalny terminarz pobrany ze strony FotMob z listą WSZYSTKICH meczow
-- turnieju (nie pojedynczego meczu) - jedyne miejsce, gdzie mamy prawdziwe
-- daty/godziny dla przyszlych etapow (cwiercfinal, polfinal, finalu), nawet
-- zanim beda znane konkretne druzyny (home/away_team_id zostaja NULL, a
-- home/away_label trzyma oryginalna etykiete FotMob, np. "Winner QF 1").
CREATE TABLE IF NOT EXISTS scheduled_fixtures (
    fotmob_match_id BIGINT PRIMARY KEY,
    round TEXT NOT NULL,
    stage TEXT NOT NULL,
    home_team_id INTEGER REFERENCES teams(team_id),
    away_team_id INTEGER REFERENCES teams(team_id),
    home_label TEXT NOT NULL,
    away_label TEXT NOT NULL,
    match_date TIMESTAMPTZ NOT NULL
);
"""


MIGRATIONS = """
ALTER TABLE matches ADD COLUMN IF NOT EXISTS stage TEXT;
ALTER TABLE daily_probability ADD COLUMN IF NOT EXISTS p_r32 NUMERIC;
ALTER TABLE daily_probability ADD COLUMN IF NOT EXISTS p_r16 NUMERIC;
ALTER TABLE daily_probability ADD COLUMN IF NOT EXISTS p_qf NUMERIC;
ALTER TABLE daily_probability ADD COLUMN IF NOT EXISTS p_sf NUMERIC;
ALTER TABLE daily_probability ADD COLUMN IF NOT EXISTS p_final NUMERIC;
-- Gdy FotMob jeszcze nie znal zwyciezcy wczesniejszego meczu, etykieta
-- zawiera obie mozliwe druzyny rozdzielone "/", np. "Argentina/Cape Verde".
-- Te kolumny trzymaja rozwiazane team_id obu kandydatow z takiej etykiety,
-- zeby 08_export_json.py mogl dopasowac terminarz do drabinki bez zgadywania.
ALTER TABLE scheduled_fixtures ADD COLUMN IF NOT EXISTS home_candidate_ids INTEGER[];
ALTER TABLE scheduled_fixtures ADD COLUMN IF NOT EXISTS away_candidate_ids INTEGER[];
-- Dane ze stron zespolow FotMob (data/team_pages/, 04c_import_team_pages.py):
-- ranking FIFA (API-Football nie ma takiego endpointu w ogole) i obecny trener
-- (API-Football ma /coachs, ale wymaga api_team_id, ktorego nie mamy dla kazdej
-- druzyny - czesc meczow szla przez recznny import, nie przez API).
ALTER TABLE teams ADD COLUMN IF NOT EXISTS fifa_rank INTEGER;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS fifa_rank_points INTEGER;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS fifa_rank_date DATE;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS coach_name TEXT;
-- Kapitan nie jest stala cecha druzyny w danych FotMob - jedyne miejsce, gdzie
-- sie pojawia, to sklad najnowszego rozegranego meczu (isCaptain).
ALTER TABLE teams ADD COLUMN IF NOT EXISTS captain_name TEXT;
-- Srednia wieku zawodnikow z aktualnego skladu FotMob (bez sztabu).
ALTER TABLE teams ADD COLUMN IF NOT EXISTS average_age NUMERIC(4,1);
"""


def main():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)
            cur.execute(MIGRATIONS)
        conn.commit()
        print("Schemat utworzony: teams, matches, team_match_stats.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
