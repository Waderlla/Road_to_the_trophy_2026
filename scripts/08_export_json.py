import json
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bracket as bracket_mod
from db import get_connection
from standings import rank_group, rank_third_places

ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = ROOT / "docs" / "data"

TEAM_NAME_PL = {
    "Algeria": "Algieria",
    "Argentina": "Argentyna",
    "Australia": "Australia",
    "Austria": "Austria",
    "Belgium": "Belgia",
    "Bosnia and Herzegovina": "Bośnia i Hercegowina",
    "Brazil": "Brazylia",
    "Canada": "Kanada",
    "Cape Verde": "Wyspy Zielonego Przylądka",
    "Colombia": "Kolumbia",
    "Croatia": "Chorwacja",
    "Curacao": "Curaçao",
    "Czechia": "Czechy",
    "DR Congo": "DR Kongo",
    "Ecuador": "Ekwador",
    "Egypt": "Egipt",
    "England": "Anglia",
    "France": "Francja",
    "Germany": "Niemcy",
    "Ghana": "Ghana",
    "Haiti": "Haiti",
    "Iran": "Iran",
    "Iraq": "Irak",
    "Ivory Coast": "Wybrzeże Kości Słoniowej",
    "Japan": "Japonia",
    "Jordan": "Jordania",
    "Mexico": "Meksyk",
    "Morocco": "Maroko",
    "Netherlands": "Holandia",
    "New Zealand": "Nowa Zelandia",
    "Norway": "Norwegia",
    "Panama": "Panama",
    "Paraguay": "Paragwaj",
    "Portugal": "Portugalia",
    "Qatar": "Katar",
    "Saudi Arabia": "Arabia Saudyjska",
    "Scotland": "Szkocja",
    "Senegal": "Senegal",
    "South Africa": "Republika Południowej Afryki",
    "South Korea": "Korea Południowa",
    "Spain": "Hiszpania",
    "Sweden": "Szwecja",
    "Switzerland": "Szwajcaria",
    "Tunisia": "Tunezja",
    "Turkiye": "Turcja",
    "Uruguay": "Urugwaj",
    "USA": "Stany Zjednoczone",
    "Uzbekistan": "Uzbekistan",
}


TEAM_ISO_CODE = {
    "Algeria": "dz", "Argentina": "ar", "Australia": "au", "Austria": "at",
    "Belgium": "be", "Bosnia and Herzegovina": "ba", "Brazil": "br", "Canada": "ca",
    "Cape Verde": "cv", "Colombia": "co", "Croatia": "hr", "Curacao": "cw",
    "Czechia": "cz", "DR Congo": "cd", "Ecuador": "ec", "Egypt": "eg",
    "England": "gb-eng", "France": "fr", "Germany": "de", "Ghana": "gh",
    "Haiti": "ht", "Iran": "ir", "Iraq": "iq", "Ivory Coast": "ci",
    "Japan": "jp", "Jordan": "jo", "Mexico": "mx", "Morocco": "ma",
    "Netherlands": "nl", "New Zealand": "nz", "Norway": "no", "Panama": "pa",
    "Paraguay": "py", "Portugal": "pt", "Qatar": "qa", "Saudi Arabia": "sa",
    "Scotland": "gb-sct", "Senegal": "sn", "South Africa": "za", "South Korea": "kr",
    "Spain": "es", "Sweden": "se", "Switzerland": "ch", "Tunisia": "tn",
    "Turkiye": "tr", "Uruguay": "uy", "USA": "us", "Uzbekistan": "uz",
}


TEAM_CODE = {
    "Algeria": "ALG", "Argentina": "ARG", "Australia": "AUS", "Austria": "AUT",
    "Belgium": "BEL", "Bosnia and Herzegovina": "BIH", "Brazil": "BRA", "Canada": "CAN",
    "Cape Verde": "CPV", "Colombia": "COL", "Croatia": "CRO", "Curacao": "CUW",
    "Czechia": "CZE", "DR Congo": "COD", "Ecuador": "ECU", "Egypt": "EGY",
    "England": "ENG", "France": "FRA", "Germany": "GER", "Ghana": "GHA",
    "Haiti": "HAI", "Iran": "IRN", "Iraq": "IRQ", "Ivory Coast": "CIV",
    "Japan": "JPN", "Jordan": "JOR", "Mexico": "MEX", "Morocco": "MAR",
    "Netherlands": "NED", "New Zealand": "NZL", "Norway": "NOR", "Panama": "PAN",
    "Paraguay": "PAR", "Portugal": "POR", "Qatar": "QAT", "Saudi Arabia": "KSA",
    "Scotland": "SCO", "Senegal": "SEN", "South Africa": "RSA", "South Korea": "KOR",
    "Spain": "ESP", "Sweden": "SWE", "Switzerland": "SUI", "Tunisia": "TUN",
    "Turkiye": "TUR", "Uruguay": "URU", "USA": "USA", "Uzbekistan": "UZB",
}


STAT_COLUMNS = [
    "goals", "shots_total", "shots_on_goal", "shots_off_goal", "shots_blocked",
    "shots_inside_box", "shots_outside_box", "possession_pct", "passes_total",
    "passes_accurate", "passes_pct", "fouls", "corners", "offsides",
    "yellow_cards", "red_cards", "goalkeeper_saves", "expected_goals", "goals_prevented",
]


def to_jsonable(value):
    if hasattr(value, "__float__") and not isinstance(value, (int, float, bool)):
        return round(float(value), 2)
    return value


def export_teams(cur):
    cur.execute(
        """
        SELECT team_id, name, group_name, logo_url,
               fifa_rank, fifa_rank_points, fifa_rank_date,
               coach_name, captain_name, average_age
        FROM teams
        """
    )
    teams = {}
    for tid, name, group, logo, fifa_rank, fifa_points, fifa_date, coach, captain, average_age in cur.fetchall():
        teams[str(tid)] = {
            "name": TEAM_NAME_PL.get(name, name),
            "code": TEAM_CODE.get(name, name[:3].upper()),
            "group": group,
            "logo_url": logo,
            "iso": TEAM_ISO_CODE.get(name),
            "fifa_rank": fifa_rank,
            "fifa_rank_points": fifa_points,
            "fifa_rank_date": fifa_date.isoformat() if fifa_date else None,
            "coach_name": coach,
            "captain_name": captain,
            "average_age": to_jsonable(average_age),
        }
    return teams


def export_strength_by_date(cur):
    cur.execute(
        """
        SELECT calc_date, team_id, matches_played, attack, defense, control,
               efficiency, discipline, form, strength
        FROM daily_strength
        """
    )
    by_date = {}
    for row in cur.fetchall():
        calc_date = row[0].isoformat()
        by_date.setdefault(calc_date, {})[row[1]] = {
            "matches_played": row[2],
            "attack": to_jsonable(row[3]),
            "defense": to_jsonable(row[4]),
            "control": to_jsonable(row[5]),
            "efficiency": to_jsonable(row[6]),
            "discipline": to_jsonable(row[7]),
            "form": to_jsonable(row[8]),
            "strength": to_jsonable(row[9]),
        }
    return by_date


def export_probability_by_date(cur):
    cur.execute(
        "SELECT calc_date, team_id, champion_probability, rank, p_r32, p_r16, p_qf, p_sf, p_final "
        "FROM daily_probability"
    )
    by_date = {}
    for calc_date, team_id, probability, rank, p_r32, p_r16, p_qf, p_sf, p_final in cur.fetchall():
        by_date.setdefault(calc_date.isoformat(), {})[team_id] = {
            "probability": to_jsonable(probability),
            "rank": rank,
            "p_r32": to_jsonable(p_r32),
            "p_r16": to_jsonable(p_r16),
            "p_qf": to_jsonable(p_qf),
            "p_sf": to_jsonable(p_sf),
            "p_final": to_jsonable(p_final),
        }
    return by_date


FINISHED_STATUSES = ("FT", "AET", "PEN")


def export_base_rate_by_date(cur):
    """Srednia liczba goli/druzyne/mecz w turnieju do danego dnia - potrzebne
    frontendowi do liczenia prognoz meczow (ten sam model Poissona, przeniesiony
    do JS)."""
    cur.execute("SELECT DISTINCT calc_date FROM daily_strength ORDER BY calc_date")
    dates = [r[0] for r in cur.fetchall()]
    by_date = {}
    for d in dates:
        cur.execute(
            """
            SELECT AVG(goals)::float FROM (
                SELECT home_goals AS goals FROM matches
                WHERE match_date::date <= %(d)s AND status IN %(statuses)s
                UNION ALL
                SELECT away_goals AS goals FROM matches
                WHERE match_date::date <= %(d)s AND status IN %(statuses)s
            ) g
            """,
            {"d": d, "statuses": FINISHED_STATUSES},
        )
        by_date[d.isoformat()] = round(cur.fetchone()[0] or 1.3, 3)
    return by_date


MAX_OPPONENTS_PER_STAGE = 6
MIN_OPPONENT_PROBABILITY = 0.01


def export_opponent_distribution_by_date(cur):
    # Bez ograniczenia rozklad przeciwnikow potrafi miec dziesiatki wpisow na
    # etap (dlugi ogon szans ponizej 1%) i mocno rozdmuchuje plik eksportu -
    # zostawiamy tylko kilka najbardziej prawdopodobnych.
    cur.execute(
        "SELECT calc_date, team_id, stage, opponent_id, probability FROM daily_opponent_distribution "
        "WHERE probability >= %s ORDER BY calc_date, team_id, stage, probability DESC",
        (MIN_OPPONENT_PROBABILITY,),
    )
    by_date = {}
    for calc_date, team_id, stage, opponent_id, probability in cur.fetchall():
        team_map = by_date.setdefault(calc_date.isoformat(), {}).setdefault(team_id, {})
        bucket = team_map.setdefault(stage, [])
        if len(bucket) < MAX_OPPONENTS_PER_STAGE:
            bucket.append({"opponent_id": opponent_id, "probability": to_jsonable(probability)})
    return by_date


def export_matches_by_date(cur):
    cur.execute(
        f"""
        SELECT m.match_id, m.match_date, m.home_team_id, m.away_team_id,
               m.home_goals, m.away_goals, m.stage, m.status, m.winner_team_id,
               {', '.join('sh.' + c + ' AS h_' + c for c in STAT_COLUMNS)},
               {', '.join('sa.' + c + ' AS a_' + c for c in STAT_COLUMNS)}
        FROM matches m
        LEFT JOIN team_match_stats sh ON sh.match_id = m.match_id AND sh.team_id = m.home_team_id
        LEFT JOIN team_match_stats sa ON sa.match_id = m.match_id AND sa.team_id = m.away_team_id
        ORDER BY m.match_date
        """
    )
    columns = [c.name for c in cur.description]
    by_date = {}
    for row in cur.fetchall():
        record = dict(zip(columns, row))
        calc_date = record["match_date"].date().isoformat()
        home_stats = {c: to_jsonable(record[f"h_{c}"]) for c in STAT_COLUMNS if record[f"h_{c}"] is not None}
        away_stats = {c: to_jsonable(record[f"a_{c}"]) for c in STAT_COLUMNS if record[f"a_{c}"] is not None}
        by_date.setdefault(calc_date, []).append({
            "home_team_id": record["home_team_id"],
            "away_team_id": record["away_team_id"],
            "kickoff": record["match_date"].isoformat(),
            "home_goals": record["home_goals"],
            "away_goals": record["away_goals"],
            "stage": record["stage"],
            "status": record["status"],
            "winner_team_id": record["winner_team_id"],
            "home_stats": home_stats,
            "away_stats": away_stats,
        })
    return by_date


STAGE_ORDER = ["R32", "R16", "QF", "SF", "final"]
STAGE_SLOTS = {
    "R16": bracket_mod.R16_SLOTS,
    "QF": bracket_mod.QF_SLOTS,
    "SF": bracket_mod.SF_SLOTS,
}


def compute_group_positions(all_group_matches, groups_by_name, calc_date):
    """Deterministyczna (nie-symulacyjna) rekonstrukcja realnych tabel grup -
    tylko dla grup, ktore maja juz WSZYSTKIE 6 meczow rozegranych do calc_date.
    Uzywana do pokazania prawdziwej drabinki (nie prognozy), wiec stala
    (seedowana) losowosc przy remisach wystarczy - to tylko wyswietlanie.

    Zwraca tez group_eliminated - druzyny NA PEWNO odpadle juz w fazie
    grupowej (4. miejsce w zakonczonej grupie zawsze odpada; 3. miejsce
    odpada dopiero gdy wszystkie 12 grup sie skonczylo i nie zalapalo sie
    w 8 najlepszych trzecich miejsc). To realna, deterministyczna eliminacja
    - nie ma nic wspolnego z zaszumionym wynikiem symulacji Monte Carlo."""
    decided = [
        (h, a, hg, ag) for h, a, hg, ag, d, status in all_group_matches
        if d <= calc_date and status in FINISHED_STATUSES
    ]

    position = {}
    third_place_by_group = {}
    group_eliminated = set()
    all_complete = True
    for grp, team_ids in groups_by_name.items():
        grp_matches = [m for m in decided if m[0] in team_ids and m[1] in team_ids]
        if len(grp_matches) < 6:
            all_complete = False
            continue
        rng = random.Random(42)
        order = rank_group(team_ids, grp_matches, rng)
        for pos, tid in enumerate(order):
            position[f"{pos + 1}{grp}"] = tid
        third_place_by_group[grp] = order[2]
        group_eliminated.add(order[3])

    if all_complete:
        rng = random.Random(42)
        best_thirds = rank_third_places(third_place_by_group, decided, rng)
        qualifying_thirds = set(best_thirds[:8])
        for i, tid in enumerate(best_thirds[:8]):
            position[f"3rd-rank-{i + 1}"] = tid
        for tid in third_place_by_group.values():
            if tid not in qualifying_thirds:
                group_eliminated.add(tid)

    return position, group_eliminated


def compute_bracket_by_date(cur, all_dates):
    # ORDER BY jest tu konieczne, nie kosmetyczne: bez niego kolejnosc
    # decyduje o tym, ktora druzyna wygrywa losowanie przy remisie punktowym
    # (patrz standings.py), a Postgres bez ORDER BY nie gwarantuje kolejnosci
    # wierszy - kazdy zapis w tabeli teams (np. import kolejnego meczu) mogl
    # ja po cichu zmienic i przestawic pary w drabince miedzy uruchomieniami.
    cur.execute("SELECT team_id, group_name FROM teams ORDER BY team_id")
    groups_by_name = {}
    for tid, grp in cur.fetchall():
        groups_by_name.setdefault(grp, []).append(tid)

    cur.execute(
        "SELECT home_team_id, away_team_id, home_goals, away_goals, match_date::date, status "
        "FROM matches WHERE stage = 'group'"
    )
    all_group_matches = cur.fetchall()

    cur.execute(
        "SELECT home_team_id, away_team_id, home_goals, away_goals, winner_team_id, stage, "
        "match_date::date, status "
        "FROM matches WHERE stage = ANY(%s)",
        (STAGE_ORDER + ["third_place"],),
    )
    knockout_matches = cur.fetchall()

    # Realny terminarz (scheduled_fixtures, zaimportowany z 04b_import_schedule.py) -
    # jedyne zrodlo daty dla slotow drabinki, ktore jeszcze nie zostaly rozegrane.
    # Dla kazdego wiersza budujemy "zestaw kandydatow" po obu stronach: pojedyncza
    # znana druzyna (home/away_team_id) albo lista mozliwych druzyn odczytana z
    # etykiety FotMob typu "Argentina/Cape Verde" (home/away_candidate_ids,
    # wypelniane przez 04b_import_schedule.py). Wiersze bez zadnej z tych dwoch
    # (np. czysty placeholder "Winner QF 1") maja side_set = None i sa dopasowywane
    # pozycyjnie (wedlug kolejnosci fotmob_match_id), bo to jedyna informacja jaka
    # zostaje, gdy nawet FotMob nie znal jeszcze zadnej z realnych druzyn.
    cur.execute(
        "SELECT fotmob_match_id, stage, home_team_id, away_team_id, "
        "home_candidate_ids, away_candidate_ids, match_date "
        "FROM scheduled_fixtures ORDER BY fotmob_match_id"
    )
    scheduled_by_stage = {}
    for fmid, stage, h_id, a_id, h_cand, a_cand, d in cur.fetchall():
        side_a = frozenset([h_id]) if h_id is not None else (frozenset(h_cand) if h_cand else None)
        side_b = frozenset([a_id]) if a_id is not None else (frozenset(a_cand) if a_cand else None)
        scheduled_by_stage.setdefault(stage, []).append(
            {"fotmob_match_id": fmid, "side_a": side_a, "side_b": side_b, "date": d}
        )

    # Prawdziwy przeciwnik z 1/16 finalu wg terminarza (wszystkie 16 par ma tu
    # obie druzyny rozstrzygniete). Gdy dwie trzecie miejsca maja identyczny
    # bilans (pkt/roznica/bramki), FIFA rozstrzyga losowaniem, ktorego nasz
    # kod nie moze odtworzyc - w takim wypadku ufamy realnemu terminarzowi,
    # a nie wlasnemu (zaseedowanemu, ale wciaz zgadywanemu) losowaniu.
    real_r32_opponent = {}
    for row in scheduled_by_stage.get("R32", []):
        if row["side_a"] and row["side_b"] and len(row["side_a"]) == 1 and len(row["side_b"]) == 1:
            a = next(iter(row["side_a"]))
            b = next(iter(row["side_b"]))
            real_r32_opponent[a] = b
            real_r32_opponent[b] = a

    by_date = {}
    eliminated_by_date = {}
    for calc_date in all_dates:
        position, group_eliminated = compute_group_positions(all_group_matches, groups_by_name, calc_date)

        real_result = {}
        knockout_eliminated = set()
        for h, a, hg, ag, winner, stage, d, status in knockout_matches:
            has_confirmed_score = hg is not None and ag is not None and winner is not None
            if d <= calc_date and (status in FINISHED_STATUSES or has_confirmed_score):
                real_result[(frozenset((h, a)), stage)] = {
                    "home_team_id": h, "away_team_id": a,
                    "home_goals": hg, "away_goals": ag, "winner_team_id": winner,
                }
                if winner is not None:
                    knockout_eliminated.add(a if winner == h else h)

        eliminated_by_date[calc_date.isoformat()] = group_eliminated | knockout_eliminated

        # Kopia dostepnych wierszy terminarza na ten dzien - dopasowane wiersze sa
        # z niej usuwane, zeby jeden mecz terminarza nie zostal przypisany dwa razy.
        remaining_by_stage = {s: list(rows) for s, rows in scheduled_by_stage.items()}

        def find_scheduled_date(stage, cand_a, cand_b):
            rows = remaining_by_stage.get(stage)
            if not rows or cand_a is None or cand_b is None:
                return None
            for i, row in enumerate(rows):
                if row["side_a"] is None or row["side_b"] is None:
                    continue
                # Podzbior, nie rownosc: gdy zwyciezca jest juz znany (cand to
                # pojedyncza druzyna), wiersz terminarza moze wciaz trzymac
                # szerszy zestaw kandydatow sprzed rozstrzygniecia (np. "Portugal/
                # Croatia"), bo import nie wraca do niego po fakcie.
                if (cand_a <= row["side_a"] and cand_b <= row["side_b"]) or (
                    cand_a <= row["side_b"] and cand_b <= row["side_a"]
                ):
                    rows.pop(i)
                    return row["date"]
            return None

        SLOT_FALLBACK_INDEX = {
            # Kolejnosc w scheduled_fixtures dla tych rund jest kolejnoscia
            # terminarza, a nie zawsze kolejnoscia rysowanej drabinki.
            # Tu jawnie mowimy, ktory wiersz terminarza nalezy do ktorego
            # wizualnego slotu cwiercfinalu.
            "QF": [0, 2, 1, 3],
            "SF": [0, 1],
            "final": [0],
            "third_place": [0],
        }

        def apply_slot_date(stage, slot_index, entry):
            """Data/godzina nalezy do slotu drabinki, a nie do aktualnie
            przewidywanej pary druzyn. Dzieki temu kafelek nie przeskakuje
            z 11 lipca na 10 lipca tylko dlatego, ze po nowych wynikach
            zmienila sie prognozowana sciezka druzyny."""
            fallback_order = SLOT_FALLBACK_INDEX.get(stage)
            if fallback_order is None or slot_index >= len(fallback_order):
                return False
            rows = scheduled_by_stage.get(stage, [])
            schedule_index = fallback_order[slot_index]
            if schedule_index >= len(rows):
                return False
            scheduled_date = rows[schedule_index]["date"]
            entry["date"] = scheduled_date.date().isoformat()
            entry["kickoff"] = scheduled_date.isoformat()
            return True

        def resolve_stage(stage, pairs, cand_pairs):
            # Dwa przebiegi: najpierw dopasowanie po znanych druzynach/kandydatach
            # (jednoznaczne), dopiero potem - dla tego, co zostalo nieoznaczone -
            # dopasowanie pozycyjne wzgledem pozostalych wierszy terminarza w tej
            # samej rundzie. Gdyby zrobic to w jednym przebiegu, wczesniejszy slot
            # bez kandydatow moglby "podkrasc" wiersz terminarza nalezacy pozycyjnie
            # do pozniejszego slotu, ktory ma jeszcze nieprzetworzone kandydaty.
            entries = []
            needs_positional = []
            for slot_index, ((team_a, team_b), (cand_a, cand_b)) in enumerate(zip(pairs, cand_pairs)):
                if team_a is None or team_b is None:
                    entry = {"team_a": team_a, "team_b": team_b, "result": None}
                    scheduled_date = find_scheduled_date(stage, cand_a, cand_b)
                    if scheduled_date is not None:
                        entry["date"] = scheduled_date.date().isoformat()
                        entry["kickoff"] = scheduled_date.isoformat()
                    elif not apply_slot_date(stage, slot_index, entry):
                        needs_positional.append(entry)
                    entries.append(entry)
                    continue
                result = real_result.get((frozenset((team_a, team_b)), stage))
                entry = {"team_a": team_a, "team_b": team_b, "result": result}
                scheduled_date = find_scheduled_date(stage, frozenset([team_a]), frozenset([team_b]))
                if scheduled_date is not None:
                    entry["date"] = scheduled_date.date().isoformat()
                    entry["kickoff"] = scheduled_date.isoformat()
                elif result is None:
                    apply_slot_date(stage, slot_index, entry)
                else:
                    apply_slot_date(stage, slot_index, entry)
                entries.append(entry)

            rows = remaining_by_stage.get(stage, [])
            for entry in needs_positional:
                if not rows:
                    break
                scheduled_date = rows.pop(0)["date"]
                entry["date"] = scheduled_date.date().isoformat()
                entry["kickoff"] = scheduled_date.isoformat()
            return entries

        r32_pairs = []
        for a, b in bracket_mod.R32_PAIRS:
            team_a, team_b = position.get(a), position.get(b)
            if team_a is not None and team_b is not None:
                real_opponent = real_r32_opponent.get(team_a)
                if real_opponent is not None and real_opponent != team_b:
                    team_b = real_opponent
            r32_pairs.append((team_a, team_b))
        stage_entries = {
            "R32": resolve_stage("R32", r32_pairs, [(None, None)] * len(r32_pairs))
        }

        prev_winners = [
            e["result"]["winner_team_id"] if e["result"] else None
            for e in stage_entries["R32"]
        ]
        for stage in ("R16", "QF", "SF"):
            prev_entries = stage_entries[STAGE_ORDER[STAGE_ORDER.index(stage) - 1]]
            pairs = [
                (prev_winners[a] if a < len(prev_winners) else None,
                 prev_winners[b] if b < len(prev_winners) else None)
                for a, b in STAGE_SLOTS[stage]
            ]
            cand_pairs = [
                (entry_candidates(prev_entries, a), entry_candidates(prev_entries, b))
                for a, b in STAGE_SLOTS[stage]
            ]
            stage_entries[stage] = resolve_stage(stage, pairs, cand_pairs)
            prev_winners = [
                e["result"]["winner_team_id"] if e["result"] else None
                for e in stage_entries[stage]
            ]

        final_pair = (
            prev_winners[0] if len(prev_winners) > 0 else None,
            prev_winners[1] if len(prev_winners) > 1 else None,
        )
        final_cand_pair = (
            entry_candidates(stage_entries["SF"], 0),
            entry_candidates(stage_entries["SF"], 1),
        )
        stage_entries["final"] = resolve_stage("final", [final_pair], [final_cand_pair])

        # Mecz o 3. miejsce - grają przegrani obu polfinalow (nie zwyciezcy).
        sf_losers = []
        for e in stage_entries["SF"]:
            if e["result"]:
                winner = e["result"]["winner_team_id"]
                sf_losers.append(e["team_b"] if winner == e["team_a"] else e["team_a"])
            else:
                sf_losers.append(None)
        third_place_pair = (
            sf_losers[0] if len(sf_losers) > 0 else None,
            sf_losers[1] if len(sf_losers) > 1 else None,
        )
        third_place_cand_pair = (
            entry_candidates(stage_entries["SF"], 0),
            entry_candidates(stage_entries["SF"], 1),
        )
        stage_entries["third_place"] = resolve_stage(
            "third_place", [third_place_pair], [third_place_cand_pair]
        )

        by_date[calc_date.isoformat()] = stage_entries

    return by_date, eliminated_by_date


def entry_candidates(entries, idx):
    """Zestaw mozliwych druzyn danego slotu poprzedniej rundy - uzywany do
    dopasowania terminarza, gdy zwyciezca tego slotu jest jeszcze nieznany."""
    if idx >= len(entries):
        return None
    entry = entries[idx]
    if entry["team_a"] is not None and entry["team_b"] is not None:
        return frozenset((entry["team_a"], entry["team_b"]))
    return None


def build_calendar(strength_by_date, probability_by_date, matches_by_date, base_rate_by_date, opponents_by_date, bracket_by_date, eliminated_by_date):
    all_dates = sorted(set(strength_by_date) | set(probability_by_date) | set(matches_by_date))
    calendar = []
    for calc_date in all_dates:
        strength = strength_by_date.get(calc_date, {})
        probability = probability_by_date.get(calc_date, {})
        opponents = opponents_by_date.get(calc_date, {})

        eliminated = eliminated_by_date.get(calc_date, set())
        prediction = []
        for team_id, prob_info in probability.items():
            entry = {"team_id": team_id, **prob_info}
            entry.update(strength.get(team_id, {}))
            entry["opponents"] = opponents.get(team_id, {})
            entry["real_eliminated"] = team_id in eliminated
            prediction.append(entry)
        prediction.sort(key=lambda e: e["rank"])

        calendar.append({
            "date": calc_date,
            "base_rate": base_rate_by_date.get(calc_date, 1.3),
            "prediction": prediction,
            "matches": matches_by_date.get(calc_date, []),
            "bracket": bracket_by_date.get(calc_date, {}),
        })
    return calendar


def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            teams = export_teams(cur)
            strength_by_date = export_strength_by_date(cur)
            probability_by_date = export_probability_by_date(cur)
            matches_by_date = export_matches_by_date(cur)
            base_rate_by_date = export_base_rate_by_date(cur)
            opponents_by_date = export_opponent_distribution_by_date(cur)
            all_dates = sorted(set(strength_by_date) | set(probability_by_date) | set(matches_by_date))
            date_objs = [date.fromisoformat(d) for d in all_dates]
            bracket_by_date, eliminated_by_date = compute_bracket_by_date(cur, date_objs)
    finally:
        conn.close()

    calendar = build_calendar(strength_by_date, probability_by_date, matches_by_date, base_rate_by_date, opponents_by_date, bracket_by_date, eliminated_by_date)
    latest_date = max(probability_by_date) if probability_by_date else None

    (EXPORT_DIR / "teams.json").write_text(
        json.dumps(teams, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (EXPORT_DIR / "calendar.json").write_text(
        json.dumps({"latest_date": latest_date, "days": calendar}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Wyeksportowano {len(teams)} druzyn i {len(calendar)} dni do {EXPORT_DIR}")


if __name__ == "__main__":
    main()
