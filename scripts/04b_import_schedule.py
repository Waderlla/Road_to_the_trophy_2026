"""Importuje oficjalny terminarz turnieju z zapisanej strony FotMob
"fixtures" (lista WSZYSTKICH meczow, nie pojedynczy mecz jak w
04_import_fotmob_html.py). To jedyne zrodlo prawdziwych dat/godzin dla
przyszlych etapow (cwiercfinal, polfinal, finalu) - nawet zanim znane sa
konkretne druzyny, FotMob juz zna dokladny termin kazdego slotu drabinki."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import get_connection

ROOT = Path(__file__).resolve().parent.parent
HTML_DIR = ROOT / "data" / "fixtures_schedule"

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)

# FotMob "round" (tekst) -> nasz kanoniczny etap turnieju (ten sam, ktorego
# uzywa 04_import_fotmob_html.py / 02_fetch_fixtures.py).
STAGE_MAP = {
    "1/16": "R32",
    "1/8": "R16",
    "1/4": "QF",
    "1/2": "SF",
    "bronze": "third_place",
    "final": "final",
}


def normalize_stage(round_value):
    return STAGE_MAP.get(round_value, "group")


def extract_matches(html_path):
    html_text = html_path.read_text(encoding="utf-8", errors="ignore")
    m = NEXT_DATA_RE.search(html_text)
    if not m:
        return None
    data = json.loads(m.group(1))
    return data["props"]["pageProps"]["fixtures"]["allMatches"]


def resolve_candidates(name, name_to_id):
    """Zwraca team_id, jesli etykieta to pojedyncza znana druzyna, w
    przeciwnym razie probuje rozbic etykiete typu "Argentina/Cape Verde"
    (FotMob tak opisuje slot, gdy poprzedni mecz jeszcze nie mial zwyciezcy)
    na liste kandydatow (team_id kazdej z mozliwych druzyn)."""
    direct_id = name_to_id.get(name)
    if direct_id is not None:
        return direct_id, None
    if "/" in name:
        parts = [p.strip() for p in name.split("/")]
        ids = [name_to_id[p] for p in parts if p in name_to_id]
        if ids and len(ids) == len(parts):
            return None, ids
    return None, None


def upsert_fixture(cur, name_to_id, m):
    home_name = m["home"]["name"]
    away_name = m["away"]["name"]
    home_id, home_candidates = resolve_candidates(home_name, name_to_id)
    away_id, away_candidates = resolve_candidates(away_name, name_to_id)
    round_value = m.get("round")
    stage = normalize_stage(round_value)

    cur.execute(
        """
        INSERT INTO scheduled_fixtures (
            fotmob_match_id, round, stage, home_team_id, away_team_id,
            home_label, away_label, match_date,
            home_candidate_ids, away_candidate_ids
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (fotmob_match_id) DO UPDATE SET
            round = EXCLUDED.round,
            stage = EXCLUDED.stage,
            home_team_id = EXCLUDED.home_team_id,
            away_team_id = EXCLUDED.away_team_id,
            home_label = EXCLUDED.home_label,
            away_label = EXCLUDED.away_label,
            match_date = EXCLUDED.match_date,
            home_candidate_ids = EXCLUDED.home_candidate_ids,
            away_candidate_ids = EXCLUDED.away_candidate_ids
        """,
        (
            int(m["id"]), round_value, stage, home_id, away_id,
            home_name, away_name, m["status"]["utcTime"],
            home_candidates, away_candidates,
        ),
    )
    return home_id is not None and away_id is not None


def main():
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    html_files = sorted(HTML_DIR.glob("*.html"))

    if not html_files:
        print(f"Brak plikow HTML w {HTML_DIR}. Zapisz tam strone terminarza FotMob (Ctrl+S) i uruchom ponownie.")
        return

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT team_id, name FROM teams")
            name_to_id = {name: tid for tid, name in cur.fetchall()}

            total, matched = 0, 0
            for html_path in html_files:
                print(f"Przetwarzam {html_path.name}...")
                matches = extract_matches(html_path)
                if matches is None:
                    print("  [BLAD] nie znaleziono __NEXT_DATA__ w pliku.")
                    continue

                for m in matches:
                    if upsert_fixture(cur, name_to_id, m):
                        matched += 1
                    total += 1
                conn.commit()
                print(f"  OK: zapisano {len(matches)} pozycji terminarza.")
    finally:
        conn.close()

    print(f"\nGotowe. Terminarz: {total} meczow, w tym {matched} z rozstrzygnietymi obiema druzynami.")


if __name__ == "__main__":
    main()
