"""Importuje strony zespolow FotMob (zapisane recznie z Ctrl+S do
data/team_pages/) - jedyne zrodlo, ktore ma ranking FIFA (API-Football w ogole
nie ma takiego endpointu) i aktualnego trenera dla kazdej druzyny (API-Football
ma /coachs, ale wymaga api_team_id, ktorego nie mamy dla wszystkich druzyn).

Kazda strona zespolu zawiera w danych PELNA tabele rankingu FIFA wszystkich
druzyn na dany dzien (nie tylko wlasnej druzyny) - wiec wystarczy jeden plik,
zeby zaktualizowac ranking wszystkich 48 druzyn na raz; przetwarzanie wielu
plikow jest wiec nadmiarowe, ale nieszkodliwe."""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import get_connection

# Konsola Windows domyslnie uzywa cp1250/cp437, ktore nie znaja wszystkich
# znakow w nazwiskach (np. norweskiego "a" z kolkiem) - bez tego print() wywala
# caly import w polowie, gdy trafi na pierwsze nietypowe nazwisko.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
HTML_DIR = ROOT / "data" / "team_pages"

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)
TEAM_KEY_RE = re.compile(r"^team-\d+$")


def extract_team_data(html_path):
    html_text = html_path.read_text(encoding="utf-8", errors="ignore")
    m = NEXT_DATA_RE.search(html_text)
    if not m:
        return None
    data = json.loads(m.group(1))
    fallback = data["props"]["pageProps"].get("fallback", {})
    for key, value in fallback.items():
        if TEAM_KEY_RE.match(key):
            return value
    return None


def upsert_fifa_ranking(cur, ranks, rank_date):
    # Jedno zapytanie z VALUES zamiast 48 osobnych UPDATE-ow na kazdy plik -
    # przy ~30 plikach to byloby ponad 1400 osobnych rundtripow do bazy.
    rows = [(e["rank"], e["totalPoints"], rank_date, e["name"]) for e in ranks]
    cur.execute(
        """
        UPDATE teams AS t SET
            fifa_rank = v.rank::int,
            fifa_rank_points = v.points::int,
            fifa_rank_date = v.rank_date::date
        FROM (VALUES %s) AS v(rank, points, rank_date, name)
        WHERE t.name = v.name
        """.replace("%s", ",".join(["(%s,%s,%s,%s)"] * len(rows))),
        [item for row in rows for item in row],
    )
    return cur.rowcount


def upsert_coach(cur, team_name, coach_name):
    cur.execute(
        "UPDATE teams SET coach_name = %s WHERE name = %s",
        (coach_name, team_name),
    )
    return cur.rowcount


def find_captain(lineup_stats):
    """FotMob nie trzyma kapitana jako stalej cechy druzyny - jedyne miejsce,
    gdzie sie pojawia, to skladu (isCaptain) najnowszego rozegranego meczu."""
    if not lineup_stats:
        return None
    for player in lineup_stats.get("starters", []):
        if player.get("isCaptain"):
            return player["name"]
    return None


def upsert_captain(cur, team_name, captain_name):
    cur.execute(
        "UPDATE teams SET captain_name = %s WHERE name = %s",
        (captain_name, team_name),
    )
    return cur.rowcount


def calculate_average_age(squad_data):
    """Liczy srednia wieku zawodnikow aktualnego skladu, bez trenerow."""
    ages = []
    for group in (squad_data or {}).get("squad", []):
        if group.get("title") == "coach":
            continue
        for player in group.get("members", []):
            age = player.get("age")
            if isinstance(age, (int, float)):
                ages.append(age)
    return round(sum(ages) / len(ages), 1) if ages else None


def upsert_average_age(cur, team_name, average_age):
    cur.execute(
        "UPDATE teams SET average_age = %s WHERE name = %s",
        (average_age, team_name),
    )
    return cur.rowcount


def main():
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    html_files = sorted(HTML_DIR.glob("*.html"))

    if not html_files:
        print(f"Brak plikow HTML w {HTML_DIR}. Zapisz tam strony zespolow (Ctrl+S) i uruchom ponownie.")
        return

    conn = get_connection()
    ranking_updated_total = 0
    coach_updated_total = 0
    captain_updated_total = 0
    average_age_updated_total = 0
    ranking_date_seen = None
    try:
        with conn.cursor() as cur:
            for html_path in html_files:
                print(f"Przetwarzam {html_path.name}...")
                team = extract_team_data(html_path)
                if team is None:
                    print("  [BLAD] nie znaleziono danych zespolu w __NEXT_DATA__.")
                    continue

                team_name = team["details"]["name"]

                fifa_ranking = team["details"].get("fifaRanking")
                if fifa_ranking:
                    # FotMob podaje date jako "DD.MM.RRRR" (polski format) - bez
                    # jawnego przeliczenia na ISO Postgres domyslnie odczytuje ja
                    # jako MM.DD.RRRR i myli dzien z miesiacem.
                    rank_date = datetime.strptime(
                        fifa_ranking["rankings"]["periodName"], "%d.%m.%Y"
                    ).date().isoformat()
                    ranks = fifa_ranking["rankings"]["ranks"]
                    n = upsert_fifa_ranking(cur, ranks, rank_date)
                    ranking_updated_total += n
                    ranking_date_seen = rank_date
                    print(f"  Ranking FIFA ({rank_date}): zaktualizowano {n} druzyn.")

                coach_history = team.get("overview", {}).get("coachHistory")
                if coach_history:
                    current_coach = coach_history[-1]["name"]
                    n = upsert_coach(cur, team_name, current_coach)
                    coach_updated_total += n
                    print(f"  Trener {team_name}: {current_coach}")
                else:
                    print(f"  [UWAGA] brak coachHistory dla {team_name}.")

                captain_name = find_captain(team.get("overview", {}).get("lastLineupStats"))
                if captain_name:
                    n = upsert_captain(cur, team_name, captain_name)
                    captain_updated_total += n
                    print(f"  Kapitan {team_name}: {captain_name}")
                else:
                    print(f"  [UWAGA] brak kapitana w ostatnim skladzie {team_name}.")

                average_age = calculate_average_age(team.get("squad"))
                if average_age is not None:
                    n = upsert_average_age(cur, team_name, average_age)
                    average_age_updated_total += n
                    print(f"  Srednia wieku {team_name}: {average_age}")
                else:
                    print(f"  [UWAGA] brak wieku zawodnikow {team_name}.")

                conn.commit()
    finally:
        conn.close()

    print(
        f"\nGotowe. Ranking FIFA na dzien {ranking_date_seen}: "
        f"{ranking_updated_total} aktualizacji. Trenerzy: {coach_updated_total} druzyn. "
        f"Kapitanowie: {captain_updated_total} druzyn. "
        f"Srednia wieku: {average_age_updated_total} druzyn."
    )


if __name__ == "__main__":
    main()
