import random
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from psycopg2.extras import execute_values

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bracket
import config
from db import get_connection
from poisson_model import expected_goals, match_result_probabilities
from standings import rank_group, rank_third_places

FINISHED_STATUSES = ("FT", "AET", "PEN")
KNOCKOUT_STAGES = ("R32", "R16", "QF", "SF", "final", "third_place")
N_SIMULATIONS = 10000
RECOMPUTE_EXISTING = True

# etykieta 1/16 finalu -> etykieta jej przeciwnika w tej samej parze (obie
# strony), zbudowane z bracket.R32_PAIRS - potrzebne do apply_real_r32_swaps.
PARTNER_LABEL = {}
for _label_a, _label_b in bracket.R32_PAIRS:
    PARTNER_LABEL[_label_a] = _label_b
    PARTNER_LABEL[_label_b] = _label_a


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def fetch_base_rate(cur, calc_date):
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
        {"d": calc_date, "statuses": FINISHED_STATUSES},
    )
    return cur.fetchone()[0] or 1.3


def load_teams(cur):
    # ORDER BY zapewnia stala kolejnosc druzyn w kazdej grupie - bez tego
    # losowanie przy remisach w standings.py moglo cicho zmieniac wynik
    # miedzy uruchomieniami, bo Postgres bez ORDER BY nie gwarantuje kolejnosci.
    cur.execute("SELECT team_id, name, group_name FROM teams ORDER BY team_id")
    teams, groups = {}, {}
    for tid, name, grp in cur.fetchall():
        teams[tid] = name
        groups.setdefault(grp, []).append(tid)
    return teams, groups


def load_group_matches(cur):
    cur.execute(
        "SELECT home_team_id, away_team_id, home_goals, away_goals, match_date, status "
        "FROM matches WHERE stage = 'group'"
    )
    return cur.fetchall()


def load_strength(cur, calc_date):
    cur.execute(
        "SELECT team_id, attack, defense FROM daily_strength WHERE calc_date = %s",
        (calc_date,),
    )
    return {tid: {"attack": float(a), "defense": float(d)} for tid, a, d in cur.fetchall()}


def load_known_knockout_results(cur, calc_date):
    """dict: (frozenset({home,away}), stage) -> winner_team_id - tylko dla
    meczow pucharowych ktore naprawde juz sie odbyly do calc_date wlacznie.
    Bez tego symulacja "na dzisiaj" losowalaby na nowo mecze, ktore juz
    naprawde sie rozegraly."""
    cur.execute(
        """
        SELECT home_team_id, away_team_id, winner_team_id, stage
        FROM matches
        WHERE stage = ANY(%s) AND match_date::date <= %s AND status IN %s
        """,
        (list(KNOCKOUT_STAGES), calc_date, FINISHED_STATUSES),
    )
    return {
        (frozenset((home_id, away_id)), stage): winner_id
        for home_id, away_id, winner_id, stage in cur.fetchall()
    }


def load_real_r32_opponent(cur):
    """dict: team_id -> team_id, tylko dla par 1/16 finalu, gdzie oficjalny
    terminarz FotMob (scheduled_fixtures) zna juz OBIE druzyny wprost (nie
    kandydatow) - realny, potwierdzony wynik losowania FIFA. Uzywane do
    korekty pary w symulacji, gdy nasz wlasny tie-break trzecich miejsc
    przydzieli druzyne do innego slotu niz sie naprawde wydarzylo."""
    cur.execute(
        "SELECT home_team_id, away_team_id FROM scheduled_fixtures "
        "WHERE stage = 'R32' AND home_team_id IS NOT NULL AND away_team_id IS NOT NULL"
    )
    real_r32_opponent = {}
    for home_id, away_id in cur.fetchall():
        real_r32_opponent[home_id] = away_id
        real_r32_opponent[away_id] = home_id
    return real_r32_opponent


def apply_real_r32_swaps(position, real_r32_opponent):
    """Zwraca kopie 'position', w ktorej kazda para druzyn ze znanego,
    naprawde rozegranego 1/16 finalu faktycznie stoi naprzeciw siebie w tej
    samej parze - przez ZAMIANE etykiet (slotow), a nie podmiane jednej
    strony pary. Podmiana samej jednej strony zdublowalaby przeciwnika (bylby
    naraz w swoim naturalnym slocie i wstawiony w cudzy), co zawyzalo p_r16 i
    dalsze etapy ponad p_r32. Zamiana zachowuje niezmiennik: kazda druzyna w
    dokladnie jednym slocie.

    Uzywac TYLKO gdy caly etap grupowy jest juz naprawde rozstrzygniety
    (fixed_position) - dla wczesniejszych dni z nierozstrzygnietymi meczami
    grupowymi ten konkretny, realny remis (np. Ekwador/Ghana) moze jeszcze w
    ogole nie zaistniec w danej hipotetycznej symulacji."""
    position = dict(position)
    label_by_team = {tid: label for label, tid in position.items()}
    handled = set()
    for team_a, team_b in real_r32_opponent.items():
        if team_a in handled or team_b in handled:
            continue
        handled.add(team_a)
        handled.add(team_b)

        label_a = label_by_team.get(team_a)
        label_b = label_by_team.get(team_b)
        if label_a is None or label_b is None:
            continue

        partner_label = PARTNER_LABEL.get(label_a)
        if partner_label is None or position.get(partner_label) == team_b:
            continue

        displaced = position.get(partner_label)
        position[partner_label] = team_b
        position[label_b] = displaced
        if displaced is not None:
            label_by_team[displaced] = label_b
        label_by_team[team_b] = partner_label

    return position


def resolve_knockout_match(team_a, team_b, stage, known_knockout, strength, base_rate, rng, prob_cache):
    key = (frozenset((team_a, team_b)), stage)
    real_winner = known_knockout.get(key)
    if real_winner is not None:
        return real_winner

    cache_key = frozenset((team_a, team_b))
    cached = prob_cache.get(cache_key)
    if cached is None:
        a, b = sorted((team_a, team_b))
        p_a, p_draw, p_b = match_result_probabilities(
            strength[a]["attack"], strength[a]["defense"],
            strength[b]["attack"], strength[b]["defense"],
            base_rate,
        )
        cached = (a, b, p_a, p_draw, p_b)
        prob_cache[cache_key] = cached

    a, b, p_a, p_draw, p_b = cached
    # W fazie pucharowej remis rozstrzyga dogrywka/karne - upraszczamy do
    # podzielenia szansy remisowej po polowie (bez dodatkowej przewagi ponad
    # regularna sile obu druzyn).
    effective_p_a = p_a + p_draw / 2
    return a if rng.random() < effective_p_a else b


def simulate_bracket(position, strength, base_rate, known_knockout, rng, prob_cache):
    """Zwraca kto dotarl do kazdego etapu w tej jednej symulacji (1/16, 1/8,
    cwiercfinal, polfinal), z kim graly (pary) na kazdym etapie, oraz kto
    zostal mistrzem.

    'position' musi miec juz zastosowana ewentualna korekte real_r32_opponent
    (patrz apply_real_r32_swaps) - tu zakladamy, ze kazda druzyna jest w
    dokladnie jednym slocie i pary sa gotowe do rozegrania."""
    r32_pairs = [(position[a], position[b]) for a, b in bracket.R32_PAIRS]
    r32_winners = [
        resolve_knockout_match(a, b, "R32", known_knockout, strength, base_rate, rng, prob_cache)
        for a, b in r32_pairs
    ]
    r16_pairs = [(r32_winners[a], r32_winners[b]) for a, b in bracket.R16_SLOTS]
    r16_winners = [
        resolve_knockout_match(a, b, "R16", known_knockout, strength, base_rate, rng, prob_cache)
        for a, b in r16_pairs
    ]
    qf_pairs = [(r16_winners[a], r16_winners[b]) for a, b in bracket.QF_SLOTS]
    qf_winners = [
        resolve_knockout_match(a, b, "QF", known_knockout, strength, base_rate, rng, prob_cache)
        for a, b in qf_pairs
    ]
    sf_pairs = [(qf_winners[a], qf_winners[b]) for a, b in bracket.SF_SLOTS]
    sf_winners = [
        resolve_knockout_match(a, b, "SF", known_knockout, strength, base_rate, rng, prob_cache)
        for a, b in sf_pairs
    ]
    final_pair = (sf_winners[0], sf_winners[1])
    champion = resolve_knockout_match(final_pair[0], final_pair[1], "final", known_knockout, strength, base_rate, rng, prob_cache)

    return {
        "r32": r32_winners,   # ci ktorzy WYGRALI 1/16 (czyli graja w 1/8)
        "r16": r16_winners,   # ci ktorzy WYGRALI 1/8 (graja w cwiercfinale)
        "qf": qf_winners,     # graja w polfinale
        "sf": sf_winners,     # graja w finale
        "champion": champion,
        "pairs": {
            "R32": r32_pairs, "R16": r16_pairs, "QF": qf_pairs, "SF": sf_pairs, "final": [final_pair],
        },
    }


def simulate_day(calc_date, teams, groups, group_matches, strength, base_rate, known_knockout, rng, real_r32_opponent):
    counts = {tid: {"r32": 0, "r16": 0, "qf": 0, "sf": 0, "final": 0, "champion": 0} for tid in teams}
    # opponent_counts[team_id][stage][opponent_id] = w ilu symulacjach team_id
    # zmierzyl sie z opponent_id na danym etapie (uzywane do "mozliwi rywale").
    opponent_counts = {tid: {"R32": {}, "R16": {}, "QF": {}, "SF": {}, "final": {}} for tid in teams}

    decided, undecided = [], []
    for home_id, away_id, home_goals, away_goals, match_date, status in group_matches:
        if match_date.date() <= calc_date and status in FINISHED_STATUSES:
            decided.append((home_id, away_id, home_goals, away_goals))
        else:
            undecided.append((home_id, away_id))

    # Wektoryzacja: lambda jest stala dla danego dnia, wiec losujemy od razu
    # N_SIMULATIONS wynikow na kazdy nierozstrzygniety mecz grupowy.
    undecided_goals = []
    for home_id, away_id in undecided:
        lam_h = expected_goals(strength[home_id]["attack"], strength[away_id]["defense"], base_rate)
        lam_a = expected_goals(strength[away_id]["attack"], strength[home_id]["defense"], base_rate)
        gh = np.random.poisson(lam_h, N_SIMULATIONS)
        ga = np.random.poisson(lam_a, N_SIMULATIONS)
        undecided_goals.append((home_id, away_id, gh, ga))

    # Jesli faza grupowa jest juz w calosci realnie rozstrzygnieta (brak
    # nierozstrzygnietych meczow grupowych), tabele grup sa identyczne w
    # kazdej symulacji - liczymy je WIEC RAZ, a nie przy kazdej z 10 000
    # iteracji. Bez tego losowe rozstrzyganie remisow w rankingu trzecich
    # miejsc (rank_third_places) potrafilo przy okazji "przetasowac" parowanie
    # w drabince inaczej niz naprawde sie wydarzylo, przez co juz wyeliminowana
    # druzyna czasem i tak "awansowala" w czesci symulacji.
    fixed_position = None
    if not undecided:
        position = {}
        third_place_by_group = {}
        for grp, team_ids in groups.items():
            grp_matches = [m for m in decided if m[0] in team_ids and m[1] in team_ids]
            order = rank_group(team_ids, grp_matches, rng)
            for pos, tid in enumerate(order):
                position[f"{pos + 1}{grp}"] = tid
            third_place_by_group[grp] = order[2]
        best_thirds = rank_third_places(third_place_by_group, decided, rng)
        for rank_idx, tid in enumerate(best_thirds[:8]):
            position[f"3rd-rank-{rank_idx + 1}"] = tid
        fixed_position = apply_real_r32_swaps(position, real_r32_opponent)

    progress_step = max(1, N_SIMULATIONS // 5)
    for i in range(N_SIMULATIONS):
        if i > 0 and i % progress_step == 0:
            print(f"    ...{i}/{N_SIMULATIONS} symulacji", flush=True)

        if fixed_position is not None:
            position = fixed_position
        else:
            sim_matches = list(decided)
            for home_id, away_id, gh, ga in undecided_goals:
                sim_matches.append((home_id, away_id, int(gh[i]), int(ga[i])))

            position = {}
            third_place_by_group = {}
            for grp, team_ids in groups.items():
                grp_matches = [m for m in sim_matches if m[0] in team_ids and m[1] in team_ids]
                order = rank_group(team_ids, grp_matches, rng)
                for pos, tid in enumerate(order):
                    position[f"{pos + 1}{grp}"] = tid
                third_place_by_group[grp] = order[2]

            best_thirds = rank_third_places(third_place_by_group, sim_matches, rng)
            for rank_idx, tid in enumerate(best_thirds[:8]):
                position[f"3rd-rank-{rank_idx + 1}"] = tid

        prob_cache = {}
        result = simulate_bracket(position, strength, base_rate, known_knockout, rng, prob_cache)

        # "reached R32" = zakwalifikowal sie do 1/16 (dokladnie 32 z 48 druzyn
        # w kazdej symulacji) - tylko druzyny faktycznie przypisane do etykiet
        # uzywanych w R32_PAIRS (position zawiera tez 3./4. miejsca w grupach
        # i odrzucone trzecie miejsca, ktorych NIE liczymy jako awans).
        for label_a, label_b in bracket.R32_PAIRS:
            counts[position[label_a]]["r32"] += 1
            counts[position[label_b]]["r32"] += 1
        for tid in result["r32"]:
            counts[tid]["r16"] += 1
        for tid in result["r16"]:
            counts[tid]["qf"] += 1
        for tid in result["qf"]:
            counts[tid]["sf"] += 1
        for tid in result["sf"]:
            counts[tid]["final"] += 1
        counts[result["champion"]]["champion"] += 1

        for stage, pairs in result["pairs"].items():
            for team_a, team_b in pairs:
                opponent_counts[team_a][stage][team_b] = opponent_counts[team_a][stage].get(team_b, 0) + 1
                opponent_counts[team_b][stage][team_a] = opponent_counts[team_b][stage].get(team_a, 0) + 1

    return counts, opponent_counts


def upsert_daily_probability(cur, calc_date, team_id, probability, rank, stage_probs):
    cur.execute(
        """
        INSERT INTO daily_probability (
            calc_date, team_id, champion_probability, rank, p_r32, p_r16, p_qf, p_sf, p_final
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (calc_date, team_id) DO UPDATE SET
            champion_probability = EXCLUDED.champion_probability,
            rank = EXCLUDED.rank,
            p_r32 = EXCLUDED.p_r32,
            p_r16 = EXCLUDED.p_r16,
            p_qf = EXCLUDED.p_qf,
            p_sf = EXCLUDED.p_sf,
            p_final = EXCLUDED.p_final
        """,
        (calc_date, team_id, probability, rank, *stage_probs),
    )


def upsert_opponent_distributions_bulk(cur, rows):
    """Jeden zbiorczy INSERT zamiast setek/tysiecy pojedynczych zapytan -
    przy szerokiej drabince (wczesne dni turnieju) liczba kombinacji
    druzyna/etap/przeciwnik jest duza, a pojedyncze execute() na kazda z nich
    bylo glownym powodem spowolnienia symulacji."""
    if not rows:
        return
    execute_values(
        cur,
        """
        INSERT INTO daily_opponent_distribution (calc_date, team_id, stage, opponent_id, probability)
        VALUES %s
        ON CONFLICT (calc_date, team_id, stage, opponent_id) DO UPDATE SET
            probability = EXCLUDED.probability
        """,
        rows,
    )


# Ile razy dana druzyna dotarla do danego etapu (mianownik przy liczeniu
# "z kim moze zagrac, JESLI tam dotrze") - klucze z 'counts' odpowiadajace
# kluczom etapow w 'opponent_counts'.
STAGE_REACHED_KEY = {"R32": "r32", "R16": "r16", "QF": "qf", "SF": "sf", "final": "final"}


def process_day(cur, calc_date, teams, groups, group_matches, rng, real_r32_opponent):
    strength = load_strength(cur, calc_date)
    if not strength:
        return False

    cur.execute("DELETE FROM daily_opponent_distribution WHERE calc_date = %s", (calc_date,))

    base_rate = fetch_base_rate(cur, calc_date)
    known_knockout = load_known_knockout_results(cur, calc_date)

    counts, opponent_counts = simulate_day(calc_date, teams, groups, group_matches, strength, base_rate, known_knockout, rng, real_r32_opponent)

    ranked = sorted(counts.items(), key=lambda kv: kv[1]["champion"], reverse=True)
    opponent_rows = []
    for rank, (team_id, c) in enumerate(ranked, start=1):
        stage_probs = (
            c["r32"] / N_SIMULATIONS, c["r16"] / N_SIMULATIONS, c["qf"] / N_SIMULATIONS,
            c["sf"] / N_SIMULATIONS, c["final"] / N_SIMULATIONS,
        )
        upsert_daily_probability(cur, calc_date, team_id, c["champion"] / N_SIMULATIONS, rank, stage_probs)

        for stage, reached_key in STAGE_REACHED_KEY.items():
            reached_count = c[reached_key]
            if reached_count == 0:
                continue
            for opponent_id, opp_count in opponent_counts[team_id][stage].items():
                opponent_rows.append((calc_date, team_id, stage, opponent_id, opp_count / reached_count))

    upsert_opponent_distributions_bulk(cur, opponent_rows)
    return True


def main():
    start = date.fromisoformat(config.TOURNAMENT_START)
    rng = random.Random()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT CURRENT_DATE")
            today = cur.fetchone()[0]

            teams, groups = load_teams(cur)
            group_matches = load_group_matches(cur)
            real_r32_opponent = load_real_r32_opponent(cur)

            all_days = list(daterange(start, today))
            total = len(all_days)
            days = 0
            run_start = time.time()

            for idx, d in enumerate(all_days, start=1):
                cur.execute("SELECT COUNT(*) FROM daily_probability WHERE calc_date = %s", (d,))
                already_done = cur.fetchone()[0]
                if not RECOMPUTE_EXISTING and already_done >= len(teams) and d != today:
                    print(f"[{idx}/{total}] {d}: juz policzone, pomijam.", flush=True)
                    continue

                print(f"[{idx}/{total}] Symuluje dzien {d} ({N_SIMULATIONS} powtorzen)...", flush=True)
                t0 = time.time()
                if process_day(cur, d, teams, groups, group_matches, rng, real_r32_opponent):
                    conn.commit()
                    days += 1
                    elapsed = time.time() - t0
                    total_elapsed = time.time() - run_start
                    print(f"[{idx}/{total}] {d}: gotowe w {elapsed:.1f}s (lacznie {total_elapsed/60:.1f} min).", flush=True)
    finally:
        conn.close()

    print(f"\nGotowe. Przeliczono prawdopodobienstwa mistrzostwa dla {days} dni.")


if __name__ == "__main__":
    main()
