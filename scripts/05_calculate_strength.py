import statistics
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from db import get_connection

FINISHED_STATUSES = ("FT", "AET", "PEN")

# Wagi Strength (etap 2 metodologii w DOKUMENTACJA.md)
STRENGTH_WEIGHTS = {
    "attack": 0.30,
    "defense": 0.30,
    "efficiency": 0.15,
    "control": 0.15,
    "form": 0.05,
    "discipline": 0.05,
}

FORM_MATCHES = 3
FORM_WEIGHTS = [0.5, 0.3, 0.2]  # najnowszy mecz wazy najwiecej

# Przy niewielu rozegranych meczach skala 0-100 wzgledem calego turnieju
# potrafi byc skrajna (np. jedyna druzyna z wynikiem po 1. dniu wyglada jak
# pewniak). SHRINKAGE_K to liczba "wirtualnych" meczow przedturniejowego priora
# (z rankingu FIFA), ktore dokladamy do kazdej druzyny - im mniej realnych
# meczow, tym mocniej wynik jest ciagniety w strone oceny sprzed turnieju.
SHRINKAGE_K = 3

# Przed pierwszym meczem nie traktujemy wszystkich druzyn identycznie. Jako
# lokalny, kompletny i stabilny prior wykorzystujemy punkty rankingu FIFA
# zaimportowane ze stron FotMob. Skala jest celowo waska: ranking ma ustawic
# sensowny start, ale nie ma przykryc realnych wynikow turnieju.
FIFA_PRIOR_ZSCORE_WIDTH = 8.0
FIFA_PRIOR_MIN = 35.0
FIFA_PRIOR_MAX = 72.0

# Skutecznosc strzelecka (gole/strzaly) jest bardzo szumna przy malej liczbie
# strzalow (2 strzaly, 2 gole = "najlepszy atak swiata" po 1 meczu). Zamiast
# liczyc surowy procent, dokladamy K_SHOTS "wirtualnych" strzalow o srednim,
# typowym dla pilki noznej wskazniku skutecznosci (bayesowskie wygladzanie).
EFFICIENCY_SHOTS_PRIOR = 0.11
EFFICIENCY_SOG_PRIOR = 0.30
K_SHOTS = 15

# Mnoznik jakosci przeciwnika przy budowie Attack/Defense: gole strzelone
# slabej obronie licza sie mniej, gole strzelone mocnej obronie - wiecej (i
# analogicznie w druga strone dla goli straconych). Ograniczamy mnoznik, zeby
# skrajne (blisko 0) wartosci Attack/Defense przeciwnika nie dawaly absurdow.
OPPONENT_ADJUSTMENT_MIN = 0.4
OPPONENT_ADJUSTMENT_MAX = 2.5


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def fetch_team_matches(cur, calc_date):
    """Zwraca dict: team_id -> lista zakonczonych meczow (z data <= calc_date,
    bez wgladu w przyszlosc), kazdy ze statystykami wlasnymi i przeciwnika."""
    cur.execute(
        """
        WITH team_matches AS (
            SELECT m.match_id, m.match_date,
                   m.home_team_id AS team_id, m.away_team_id AS opp_id,
                   m.home_goals AS gf, m.away_goals AS ga
            FROM matches m
            WHERE m.match_date::date <= %(d)s AND m.status IN %(statuses)s
            UNION ALL
            SELECT m.match_id, m.match_date,
                   m.away_team_id AS team_id, m.home_team_id AS opp_id,
                   m.away_goals AS gf, m.home_goals AS ga
            FROM matches m
            WHERE m.match_date::date <= %(d)s AND m.status IN %(statuses)s
        )
        SELECT tm.team_id, tm.opp_id, tm.match_date, tm.gf, tm.ga,
               s_own.shots_total, s_own.shots_on_goal, s_own.possession_pct,
               s_own.passes_total, s_own.passes_pct, s_own.fouls,
               s_own.yellow_cards, s_own.red_cards,
               s_opp.shots_total AS opp_shots_total,
               s_opp.shots_on_goal AS opp_shots_on_goal,
               s_opp.expected_goals AS opp_xg
        FROM team_matches tm
        LEFT JOIN team_match_stats s_own ON s_own.match_id = tm.match_id AND s_own.team_id = tm.team_id
        LEFT JOIN team_match_stats s_opp ON s_opp.match_id = tm.match_id AND s_opp.team_id = tm.opp_id
        ORDER BY tm.team_id, tm.match_date
        """,
        {"d": calc_date, "statuses": FINISHED_STATUSES},
    )
    columns = [c.name for c in cur.description]
    matches_by_team = {}
    for row in cur.fetchall():
        record = dict(zip(columns, row))
        matches_by_team.setdefault(record["team_id"], []).append(record)
    return matches_by_team


def fetch_prior_strength_history(cur, calc_date):
    """Zwraca dict: team_id -> lista (calc_date, attack, defense) ze WSZYSTKICH
    dni PRZED biezacym dniem przetwarzania - uzywane do ustalenia, jak silna
    byla druzyna PRZED danym jej meczem (zeby wazyc gole jakoscia rywala bez
    zagladania w przyszlosc)."""
    cur.execute(
        "SELECT team_id, calc_date, attack, defense FROM daily_strength WHERE calc_date < %s ORDER BY team_id, calc_date",
        (calc_date,),
    )
    history = {}
    for team_id, cdate, attack, defense in cur.fetchall():
        history.setdefault(team_id, []).append((cdate, float(attack), float(defense)))
    return history


def fetch_team_priors(cur):
    """Przedturniejowy prior 0-100 z punktow rankingu FIFA.

    Zwraca indeksy w tej samej skali co daily_strength. Nie probujemy z rankingu
    zgadywac wszystkiego: dyscyplina zostaje neutralna, a kontrola jest lekko
    przyciagnieta do 50, bo ranking FIFA najlepiej opisuje ogolna sile, nie styl.
    """
    cur.execute("SELECT team_id, fifa_rank_points FROM teams ORDER BY team_id")
    rows = cur.fetchall()
    points = {team_id: float(fifa_points) for team_id, fifa_points in rows if fifa_points is not None}
    mean = statistics.mean(points.values()) if points else 1500.0
    stdev = statistics.pstdev(points.values()) if len(points) > 1 else 1.0

    priors = {}
    for team_id, fifa_points in rows:
        value = float(fifa_points) if fifa_points is not None else mean
        z = 0.0 if stdev == 0 else (value - mean) / stdev
        strength_prior = clip(50.0 + z * FIFA_PRIOR_ZSCORE_WIDTH, FIFA_PRIOR_MIN, FIFA_PRIOR_MAX)
        control_prior = 50.0 + (strength_prior - 50.0) * 0.75
        priors[team_id] = {
            "attack": strength_prior,
            "defense": strength_prior,
            "control": control_prior,
            "efficiency": strength_prior,
            "discipline": 50.0,
            "form": strength_prior,
        }
        priors[team_id]["strength"] = sum(
            STRENGTH_WEIGHTS[k] * priors[team_id][k]
            for k in ("attack", "defense", "control", "efficiency", "discipline", "form")
        )

    return priors


def prior_strength_for(history, priors, team_id, before_date):
    """Najnowsza znana Attack/Defense danej druzyny sprzed 'before_date'.
    Jesli brak historii (pierwszy mecz turnieju danej druzyny) - prior FIFA."""
    prior = priors.get(team_id, {})
    fallback = (prior.get("attack", 50.0), prior.get("defense", 50.0))
    entries = history.get(team_id)
    if not entries:
        return fallback
    result = fallback
    for cdate, attack, defense in entries:
        if cdate < before_date:
            result = (attack, defense)
        else:
            break
    return result


def clip(value, lo, hi):
    return max(lo, min(hi, value))


def zscore_scale(values, invert=False):
    """Skaluje slownik team_id -> wartosc do 0-100 na podstawie odleglosci od
    sredniej w odchyleniach standardowych (zamiast min-max). Dzieki temu gdy
    wszystkie druzyny sa podobne, wyniki zostaja blisko 50 - min-max sztucznie
    rozciagalby nawet minimalne roznice na cala skale 0-100."""
    vals = list(values.values())
    mean = statistics.mean(vals)
    stdev = statistics.pstdev(vals)
    result = {}
    for team_id, v in values.items():
        z = 0.0 if stdev == 0 else (v - mean) / stdev
        scaled = clip(50 + z * (100 / 6), 0, 100)  # +-3 odchylenia ~ 0-100
        result[team_id] = 100 - scaled if invert else scaled
    return result


def compute_indices(matches_by_team, prior_history, priors):
    """Z per-meczowych statystyk (dict team_id -> lista meczow) liczy piec
    skladowych indeksow (0-100) dla kazdej druzyny, wazac gole jakoscia
    przeciwnika sprzed danego meczu."""
    team_ids = list(matches_by_team.keys())

    raw = {
        "goals_for_pg": {}, "goals_against_pg": {}, "shots_pg": {}, "sog_pg": {},
        "possession": {}, "pass_pct": {}, "passes_pg": {},
        "conversion": {}, "conversion_ot": {},
        "fouls_pg": {}, "cards_pg": {}, "clean_sheet_rate": {},
        "opp_shots_pg": {}, "opp_sog_pg": {}, "opp_xg_pg": {},
    }

    for tid in team_ids:
        matches = matches_by_team[tid]
        mp = len(matches)

        adj_gf_sum = adj_ga_sum = 0.0
        st_sum = sog_sum = pos_sum = passes_sum = pass_pct_sum = fouls_sum = 0.0
        yc_sum = rc_sum = clean_sheets = 0
        opp_st_sum = opp_sog_sum = opp_xg_sum = 0.0
        total_shots = total_sog = total_goals = 0.0

        for m in matches:
            opp_attack, opp_defense = prior_strength_for(prior_history, priors, m["opp_id"], m["match_date"].date())

            # Gole przeciwko slabej obronie licza sie mniej, przeciwko mocnej -
            # wiecej; analogicznie stracone gole przeciwko slabemu atakowi
            # licza sie bardziej dotkliwie niz przeciwko atakowi elitarnemu.
            defense_factor = clip(opp_defense / 50, OPPONENT_ADJUSTMENT_MIN, OPPONENT_ADJUSTMENT_MAX)
            attack_factor = clip(50 / opp_attack if opp_attack else 1.0, OPPONENT_ADJUSTMENT_MIN, OPPONENT_ADJUSTMENT_MAX)

            adj_gf_sum += m["gf"] * defense_factor
            adj_ga_sum += m["ga"] * attack_factor

            st_sum += m["shots_total"] or 0
            sog_sum += m["shots_on_goal"] or 0
            pos_sum += float(m["possession_pct"] or 0)
            passes_sum += m["passes_total"] or 0
            pass_pct_sum += float(m["passes_pct"] or 0)
            fouls_sum += m["fouls"] or 0
            yc_sum += m["yellow_cards"] or 0
            rc_sum += m["red_cards"] or 0
            clean_sheets += 1 if m["ga"] == 0 else 0
            opp_st_sum += m["opp_shots_total"] or 0
            opp_sog_sum += m["opp_shots_on_goal"] or 0
            opp_xg_sum += float(m["opp_xg"] or 0)

            total_shots += m["shots_total"] or 0
            total_sog += m["shots_on_goal"] or 0
            total_goals += m["gf"]

        raw["goals_for_pg"][tid] = adj_gf_sum / mp
        raw["goals_against_pg"][tid] = adj_ga_sum / mp
        raw["shots_pg"][tid] = st_sum / mp
        raw["sog_pg"][tid] = sog_sum / mp
        raw["possession"][tid] = pos_sum / mp
        raw["pass_pct"][tid] = pass_pct_sum / mp
        raw["passes_pg"][tid] = passes_sum / mp
        raw["fouls_pg"][tid] = fouls_sum / mp
        raw["cards_pg"][tid] = (yc_sum + 2 * rc_sum) / mp
        raw["clean_sheet_rate"][tid] = clean_sheets / mp
        raw["opp_shots_pg"][tid] = opp_st_sum / mp
        raw["opp_sog_pg"][tid] = opp_sog_sum / mp
        raw["opp_xg_pg"][tid] = opp_xg_sum / mp

        # Bayesowskie wygladzanie skutecznosci strzelowej wg liczby STRZALOW
        # (nie meczow) - to prawdziwa "wielkosc proby" dla tego wskaznika.
        raw["conversion"][tid] = (total_goals + K_SHOTS * EFFICIENCY_SHOTS_PRIOR) / (total_shots + K_SHOTS) if (total_shots + K_SHOTS) else EFFICIENCY_SHOTS_PRIOR
        raw["conversion_ot"][tid] = (total_goals + K_SHOTS * EFFICIENCY_SOG_PRIOR) / (total_sog + K_SHOTS) if (total_sog + K_SHOTS) else EFFICIENCY_SOG_PRIOR

    scaled = {
        "goals_for_pg": zscore_scale(raw["goals_for_pg"]),
        "shots_pg": zscore_scale(raw["shots_pg"]),
        "sog_pg": zscore_scale(raw["sog_pg"]),
        "goals_against_pg": zscore_scale(raw["goals_against_pg"], invert=True),
        "opp_shots_pg": zscore_scale(raw["opp_shots_pg"], invert=True),
        "opp_sog_pg": zscore_scale(raw["opp_sog_pg"], invert=True),
        "opp_xg_pg": zscore_scale(raw["opp_xg_pg"], invert=True),
        "clean_sheet_rate": zscore_scale(raw["clean_sheet_rate"]),
        "possession": zscore_scale(raw["possession"]),
        "pass_pct": zscore_scale(raw["pass_pct"]),
        "passes_pg": zscore_scale(raw["passes_pg"]),
        "conversion": zscore_scale(raw["conversion"]),
        "conversion_ot": zscore_scale(raw["conversion_ot"]),
        "fouls_pg": zscore_scale(raw["fouls_pg"], invert=True),
        "cards_pg": zscore_scale(raw["cards_pg"], invert=True),
    }

    indices = {}
    for tid in team_ids:
        indices[tid] = {
            "attack": 0.5 * scaled["goals_for_pg"][tid] + 0.25 * scaled["shots_pg"][tid] + 0.25 * scaled["sog_pg"][tid],
            "defense": (
                0.35 * scaled["goals_against_pg"][tid]
                + 0.20 * scaled["opp_xg_pg"][tid]
                + 0.20 * scaled["opp_sog_pg"][tid]
                + 0.15 * scaled["opp_shots_pg"][tid]
                + 0.10 * scaled["clean_sheet_rate"][tid]
            ),
            "control": 0.4 * scaled["possession"][tid] + 0.3 * scaled["pass_pct"][tid] + 0.3 * scaled["passes_pg"][tid],
            "efficiency": 0.5 * scaled["conversion"][tid] + 0.5 * scaled["conversion_ot"][tid],
            "discipline": 0.5 * scaled["fouls_pg"][tid] + 0.5 * scaled["cards_pg"][tid],
        }
    return indices


def compute_form(matches_by_team):
    """Forma: wazona (nowsze mecze wazniejsze) ocena ostatnich max 3 meczow -
    punkty + roznica bramek, pomnozone przez sile przeciwnika (jego wlasny
    bilans bramek na mecz do tej pory, przeskalowany 0-1)."""
    opp_quality_raw = {
        tid: sum(m["gf"] - m["ga"] for m in matches) / len(matches)
        for tid, matches in matches_by_team.items()
    }
    lo = min(opp_quality_raw.values())
    hi = max(opp_quality_raw.values())

    def opp_factor(opp_id):
        if opp_id not in opp_quality_raw or hi == lo:
            return 1.0
        norm = (opp_quality_raw[opp_id] - lo) / (hi - lo)  # 0..1
        return 0.5 + norm  # slaby rywal x0.5, mocny rywal x1.5

    form_raw = {}
    for tid, matches in matches_by_team.items():
        recent = sorted(matches, key=lambda m: m["match_date"], reverse=True)[:FORM_MATCHES]
        weights = FORM_WEIGHTS[: len(recent)]
        total_w = sum(weights)
        score = 0.0
        for match, w in zip(recent, weights):
            points = 1.0 if match["gf"] > match["ga"] else (0.5 if match["gf"] == match["ga"] else 0.0)
            goal_diff_component = max(-1.0, min(1.0, (match["gf"] - match["ga"]) / 3))
            match_score = (points + 0.5 * goal_diff_component) * opp_factor(match["opp_id"])
            score += (w / total_w) * match_score
        form_raw[tid] = score

    return zscore_scale(form_raw)


def shrink_toward_prior(value, matches_played, prior=50.0):
    weight = matches_played / (matches_played + SHRINKAGE_K)
    return weight * value + (1 - weight) * prior


def upsert_daily_strength(cur, calc_date, team_id, mp, idx, form, strength):
    cur.execute(
        """
        INSERT INTO daily_strength (
            calc_date, team_id, matches_played,
            attack, defense, control, efficiency, discipline, form, strength
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (calc_date, team_id) DO UPDATE SET
            matches_played = EXCLUDED.matches_played,
            attack = EXCLUDED.attack,
            defense = EXCLUDED.defense,
            control = EXCLUDED.control,
            efficiency = EXCLUDED.efficiency,
            discipline = EXCLUDED.discipline,
            form = EXCLUDED.form,
            strength = EXCLUDED.strength
        """,
        (calc_date, team_id, mp, idx["attack"], idx["defense"], idx["control"],
         idx["efficiency"], idx["discipline"], form, strength),
    )


def process_day(cur, calc_date, all_team_ids):
    matches_by_team = fetch_team_matches(cur, calc_date)
    priors = fetch_team_priors(cur)

    # Druzyny, ktore jeszcze nie zagraly do tego dnia wlacznie - prior FIFA.
    played_ids = set(matches_by_team.keys())
    for tid in all_team_ids:
        if tid not in played_ids:
            prior = priors.get(tid, {
                "attack": 50.0, "defense": 50.0, "control": 50.0,
                "efficiency": 50.0, "discipline": 50.0, "form": 50.0,
                "strength": 50.0,
            })
            upsert_daily_strength(
                cur, calc_date, tid, 0,
                {k: prior[k] for k in ("attack", "defense", "control", "efficiency", "discipline")},
                prior["form"], prior["strength"],
            )

    if not matches_by_team:
        return

    prior_history = fetch_prior_strength_history(cur, calc_date)
    indices = compute_indices(matches_by_team, prior_history, priors)
    form_scores = compute_form(matches_by_team)

    for tid, idx in indices.items():
        mp = len(matches_by_team[tid])
        prior = priors.get(tid, {
            "attack": 50.0, "defense": 50.0, "control": 50.0,
            "efficiency": 50.0, "discipline": 50.0, "form": 50.0,
        })
        idx = {k: shrink_toward_prior(v, mp, prior[k]) for k, v in idx.items()}
        form = shrink_toward_prior(form_scores[tid], mp, prior["form"])

        strength = sum(STRENGTH_WEIGHTS[k] * idx[k] for k in ("attack", "defense", "control", "efficiency", "discipline"))
        strength += STRENGTH_WEIGHTS["form"] * form
        upsert_daily_strength(cur, calc_date, tid, mp, idx, form, strength)


def main():
    from datetime import date as date_cls
    start = date_cls.fromisoformat(config.TOURNAMENT_START)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT CURRENT_DATE")
            today = cur.fetchone()[0]

            cur.execute("SELECT team_id FROM teams")
            all_team_ids = [r[0] for r in cur.fetchall()]

            days = 0
            for d in daterange(start, today):
                process_day(cur, d, all_team_ids)
                conn.commit()
                days += 1

        print(f"Gotowe. Przeliczono indeksy i sile dla {days} dni (od {start} do {today}).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
