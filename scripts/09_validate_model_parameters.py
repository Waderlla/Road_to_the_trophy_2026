"""Projektowe testy/uzasadnienia parametrów modelu.

Ten skrypt nie jest testem naukowym ani walidacją bukmacherską. Ma jeden cel:
pokazać, że przyjęte w projekcie liczby są jawne, spójne z lokalnymi danymi
i mają krótkie uzasadnienie metodologiczne.

Skrypt nie łączy się z API ani z bazą danych. Czyta tylko:
- docs/data/calendar.json
- docs/data/teams.json

Wynik zapisuje do:
- data/model_parameter_checks.md
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CALENDAR_PATH = ROOT / "docs" / "data" / "calendar.json"
TEAMS_PATH = ROOT / "docs" / "data" / "teams.json"
REPORT_PATH = ROOT / "data" / "model_parameter_checks.md"


# Te wartości odpowiadają parametrom opisanym w dokumentacji i użytym w kodzie.
STRENGTH_WEIGHTS = {
    "attack": 0.30,
    "defense": 0.30,
    "efficiency": 0.15,
    "control": 0.15,
    "form": 0.05,
    "discipline": 0.05,
}

ATTACK_WEIGHTS = {"goals": 0.50, "shots_total": 0.25, "shots_on_goal": 0.25}
DEFENSE_WEIGHTS = {
    "goals_against": 0.35,
    "opp_xg": 0.20,
    "opp_shots_on_goal": 0.20,
    "opp_shots_total": 0.15,
    "clean_sheets": 0.10,
}
CONTROL_WEIGHTS = {"possession": 0.40, "pass_accuracy": 0.30, "passes_total": 0.30}
EFFICIENCY_WEIGHTS = {"goals_per_shot": 0.50, "goals_per_shot_on_target": 0.50}
DISCIPLINE_WEIGHTS = {"fouls": 0.50, "cards": 0.50}

FIFA_PRIOR_ZSCORE_WIDTH = 8.0
FIFA_PRIOR_MIN = 35.0
FIFA_PRIOR_MAX = 72.0
SHRINKAGE_K = 3

EFFICIENCY_SHOTS_PRIOR = 0.11
EFFICIENCY_SOG_PRIOR = 0.30
K_SHOTS = 15

FORM_MATCHES = 3
FORM_WEIGHTS = [0.5, 0.3, 0.2]
GOAL_DIFF_DIVISOR = 3

OPPONENT_ADJUSTMENT_MIN = 0.4
OPPONENT_ADJUSTMENT_MAX = 2.5

MAX_GOALS = 10
BASE_RATE_FALLBACK = 1.3
N_SIMULATIONS = 10_000


def pct(value: float, digits: int = 2) -> str:
    return f"{value * 100:.{digits}f}%"


def fmt(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def load_data() -> tuple[dict, dict]:
    calendar = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
    teams = json.loads(TEAMS_PATH.read_text(encoding="utf-8"))
    return calendar, teams


def unique_scored_matches(calendar: dict) -> list[dict]:
    seen = {}
    for day in calendar["days"]:
        for match in day.get("matches", []):
            if match.get("home_goals") is None or match.get("away_goals") is None:
                continue
            key = (match.get("kickoff"), match.get("home_team_id"), match.get("away_team_id"))
            seen[key] = match
    return list(seen.values())


def match_stat_coverage(calendar: dict) -> dict:
    scored_matches = unique_scored_matches(calendar)
    with_any_stats = 0
    with_both_stats = 0
    for match in scored_matches:
        has_home = bool(match.get("home_stats"))
        has_away = bool(match.get("away_stats"))
        if has_home or has_away:
            with_any_stats += 1
        if has_home and has_away:
            with_both_stats += 1
    return {
        "scored_matches": len(scored_matches),
        "with_any_stats": with_any_stats,
        "with_both_stats": with_both_stats,
    }


def shot_conversion_from_export(calendar: dict) -> dict:
    shots_total = 0
    shots_on_goal = 0
    goals = 0
    team_rows_with_stats = 0

    for match in unique_scored_matches(calendar):
        for side in ("home", "away"):
            stats = match.get(f"{side}_stats") or {}
            if not stats:
                continue
            team_rows_with_stats += 1
            goals += match.get(f"{side}_goals") or 0
            shots_total += stats.get("shots_total") or 0
            shots_on_goal += stats.get("shots_on_goal") or 0

    return {
        "team_rows_with_stats": team_rows_with_stats,
        "goals": goals,
        "shots_total": shots_total,
        "shots_on_goal": shots_on_goal,
        "goals_per_shot": goals / shots_total if shots_total else 0.0,
        "goals_per_sog": goals / shots_on_goal if shots_on_goal else 0.0,
    }


def shot_conversion_examples(calendar: dict, limit: int = 3) -> list[dict]:
    examples = []
    for match in unique_scored_matches(calendar):
        for side in ("home", "away"):
            stats = match.get(f"{side}_stats") or {}
            if not stats:
                continue
            goals = match.get(f"{side}_goals") or 0
            shots_total = stats.get("shots_total") or 0
            shots_on_goal = stats.get("shots_on_goal") or 0
            if shots_total <= 0 or shots_on_goal <= 0:
                continue
            examples.append(
                {
                    "kickoff": match.get("kickoff"),
                    "team_id": match.get(f"{side}_team_id"),
                    "goals": goals,
                    "shots_total": shots_total,
                    "shots_on_goal": shots_on_goal,
                    "goals_per_shot": goals / shots_total,
                    "goals_per_sog": goals / shots_on_goal,
                }
            )
            if len(examples) >= limit:
                return examples
    return examples


def base_rate_stats(calendar: dict) -> dict:
    values = [day.get("base_rate") for day in calendar["days"] if day.get("base_rate") is not None]
    return {
        "first": values[0],
        "latest": values[-1],
        "minimum": min(values),
        "maximum": max(values),
        "mean": statistics.mean(values),
    }


def scored_goals_by_day(calendar: dict) -> list[dict]:
    rows = []
    for day in calendar["days"]:
        goals = 0
        team_match_count = 0
        seen = set()
        for match in day.get("matches", []):
            key = (match.get("kickoff"), match.get("home_team_id"), match.get("away_team_id"))
            if key in seen:
                continue
            seen.add(key)
            if match.get("home_goals") is None or match.get("away_goals") is None:
                continue
            goals += (match.get("home_goals") or 0) + (match.get("away_goals") or 0)
            team_match_count += 2
        rows.append(
            {
                "date": day["date"],
                "goals": goals,
                "team_match_count": team_match_count,
                "goals_per_team_match": goals / team_match_count if team_match_count else None,
                "exported_base_rate": day.get("base_rate"),
            }
        )
    return rows


def fifa_prior_values(teams: dict) -> list[float]:
    points = [float(team["fifa_rank_points"]) for team in teams.values() if team.get("fifa_rank_points") is not None]
    mean = statistics.mean(points)
    stdev = statistics.pstdev(points)
    priors = []
    for team in teams.values():
        value = float(team.get("fifa_rank_points") or mean)
        z = 0.0 if stdev == 0 else (value - mean) / stdev
        prior = 50.0 + z * FIFA_PRIOR_ZSCORE_WIDTH
        prior = max(FIFA_PRIOR_MIN, min(FIFA_PRIOR_MAX, prior))
        priors.append(prior)
    return priors


def fifa_prior_examples(teams: dict, limit: int = 5) -> dict:
    points = [float(team["fifa_rank_points"]) for team in teams.values() if team.get("fifa_rank_points") is not None]
    mean = statistics.mean(points)
    stdev = statistics.pstdev(points)
    rows = []
    for team_id, team in teams.items():
        value = float(team.get("fifa_rank_points") or mean)
        z = 0.0 if stdev == 0 else (value - mean) / stdev
        raw_prior = 50.0 + z * FIFA_PRIOR_ZSCORE_WIDTH
        clipped_prior = max(FIFA_PRIOR_MIN, min(FIFA_PRIOR_MAX, raw_prior))
        rows.append(
            {
                "team_id": team_id,
                "name": team.get("name"),
                "points": value,
                "z": z,
                "raw_prior": raw_prior,
                "clipped_prior": clipped_prior,
            }
        )
    # bierzemy kilka najbardziej skrajnych przykładów: top, dół i okolice środka.
    rows_sorted = sorted(rows, key=lambda row: row["clipped_prior"], reverse=True)
    middle = sorted(rows, key=lambda row: abs(row["clipped_prior"] - 50.0))[:1]
    return {
        "mean": mean,
        "stdev": stdev,
        "top": rows_sorted[:limit],
        "bottom": rows_sorted[-limit:],
        "middle": middle,
    }


def prediction_ranges(calendar: dict, date: str) -> dict:
    day = next(day for day in calendar["days"] if day["date"] == date)
    fields = ["attack", "defense", "control", "efficiency", "discipline", "form", "strength"]
    result = {}
    for field in fields:
        values = [float(row[field]) for row in day["prediction"]]
        result[field] = {
            "min": min(values),
            "max": max(values),
            "mean": statistics.mean(values),
        }
    return result


def poisson_tail_probability(lam: float, max_goals: int = MAX_GOALS) -> float:
    cumulative = 0.0
    for k in range(max_goals + 1):
        cumulative += math.exp(-lam) * lam**k / math.factorial(k)
    return max(0.0, 1.0 - cumulative)


def expected_goal_lambdas(calendar: dict) -> list[float]:
    values = []
    for day in calendar["days"]:
        base_rate = float(day.get("base_rate") or BASE_RATE_FALLBACK)
        strengths = {row["team_id"]: row for row in day["prediction"]}
        for match in day.get("matches", []):
            home = strengths.get(match.get("home_team_id"))
            away = strengths.get(match.get("away_team_id"))
            if not home or not away:
                continue
            home_lam = max(0.05, base_rate * (home["attack"] / 50) * ((100 - away["defense"]) / 50))
            away_lam = max(0.05, base_rate * (away["attack"] / 50) * ((100 - home["defense"]) / 50))
            values.extend([home_lam, away_lam])
    return values


def max_lambda_example(calendar: dict) -> dict | None:
    best = None
    for day in calendar["days"]:
        base_rate = float(day.get("base_rate") or BASE_RATE_FALLBACK)
        strengths = {row["team_id"]: row for row in day["prediction"]}
        for match in day.get("matches", []):
            home = strengths.get(match.get("home_team_id"))
            away = strengths.get(match.get("away_team_id"))
            if not home or not away:
                continue
            for side, team, opponent in (("home", home, away), ("away", away, home)):
                attack_factor = team["attack"] / 50
                defense_factor = (100 - opponent["defense"]) / 50
                lam = max(0.05, base_rate * attack_factor * defense_factor)
                if best is None or lam > best["lambda"]:
                    best = {
                        "date": day["date"],
                        "kickoff": match.get("kickoff"),
                        "side": side,
                        "team_id": team["team_id"],
                        "opponent_id": opponent["team_id"],
                        "base_rate": base_rate,
                        "attack": team["attack"],
                        "opponent_defense": opponent["defense"],
                        "attack_factor": attack_factor,
                        "defense_factor": defense_factor,
                        "lambda": lam,
                    }
    return best


def monte_carlo_standard_error(n: int, probability: float = 0.5) -> float:
    # Najgorszy przypadek dla błędu proporcji jest przy p=0.5.
    return math.sqrt(probability * (1 - probability) / n)


def fifa_width_scenarios(teams: dict) -> list[dict]:
    points = [float(team["fifa_rank_points"]) for team in teams.values() if team.get("fifa_rank_points") is not None]
    mean = statistics.mean(points)
    stdev = statistics.pstdev(points)
    rows = []
    for width in [3, 5, 8, 12, 15]:
        values = []
        for team in teams.values():
            value = float(team.get("fifa_rank_points") or mean)
            z = 0.0 if stdev == 0 else (value - mean) / stdev
            values.append(50.0 + z * width)
        rows.append(
            {
                "width": width,
                "min": min(values),
                "max": max(values),
                "spread": max(values) - min(values),
            }
        )
    return rows


def fifa_clip_scenarios(teams: dict) -> list[dict]:
    points = [float(team["fifa_rank_points"]) for team in teams.values() if team.get("fifa_rank_points") is not None]
    mean = statistics.mean(points)
    stdev = statistics.pstdev(points)
    raw_values = []
    for team in teams.values():
        value = float(team.get("fifa_rank_points") or mean)
        z = 0.0 if stdev == 0 else (value - mean) / stdev
        raw_values.append(50.0 + z * FIFA_PRIOR_ZSCORE_WIDTH)

    rows = []
    for lo, hi in [(30, 70), (35, 70), (35, 72), (35, 73), (40, 70)]:
        clipped = [max(lo, min(hi, value)) for value in raw_values]
        rows.append(
            {
                "range": f"{lo}-{hi}",
                "min": min(clipped),
                "max": max(clipped),
                "mean": statistics.mean(clipped),
                "clipped_low": sum(1 for value in raw_values if value < lo),
                "clipped_high": sum(1 for value in raw_values if value > hi),
            }
        )
    return rows


def shrinkage_scenarios() -> list[dict]:
    rows = []
    for k in [1, 2, 3, 5, 8]:
        rows.append(
            {
                "k": k,
                "after_1": 1 / (1 + k),
                "after_2": 2 / (2 + k),
                "after_3": 3 / (3 + k),
            }
        )
    return rows


def efficiency_prior_scenarios(conversion: dict) -> list[dict]:
    observed_shots = conversion["goals_per_shot"]
    observed_sog = conversion["goals_per_sog"]
    rows = []
    for shot_prior, sog_prior in [(0.08, 0.25), (0.10, 0.30), (0.11, 0.30), (observed_shots, observed_sog)]:
        rows.append(
            {
                "shot_prior": shot_prior,
                "sog_prior": sog_prior,
                "shot_diff": shot_prior - observed_shots,
                "sog_diff": sog_prior - observed_sog,
            }
        )
    return rows


def k_shots_scenarios() -> list[dict]:
    rows = []
    for k in [5, 10, 15, 25, 40]:
        smoothed_2_of_2 = (2 + k * EFFICIENCY_SHOTS_PRIOR) / (2 + k)
        smoothed_5_of_20 = (5 + k * EFFICIENCY_SHOTS_PRIOR) / (20 + k)
        rows.append(
            {
                "k": k,
                "two_of_two": smoothed_2_of_2,
                "five_of_twenty": smoothed_5_of_20,
            }
        )
    return rows


def form_weight_scenarios() -> list[dict]:
    return [
        {"name": "równe", "weights": [1 / 3, 1 / 3, 1 / 3]},
        {"name": "wybrane", "weights": FORM_WEIGHTS},
        {"name": "bardzo świeże", "weights": [0.7, 0.2, 0.1]},
    ]


def opponent_limit_scenarios() -> list[dict]:
    raw_values = [0.2, 0.4, 0.8, 1.0, 1.6, 2.5, 4.0]
    rows = []
    for value in raw_values:
        rows.append(
            {
                "raw": value,
                "chosen": max(OPPONENT_ADJUSTMENT_MIN, min(OPPONENT_ADJUSTMENT_MAX, value)),
                "wide": max(0.2, min(4.0, value)),
                "narrow": max(0.7, min(1.6, value)),
            }
        )
    return rows


def max_goals_scenarios(lam: float) -> list[dict]:
    return [
        {"max_goals": max_goals, "tail": poisson_tail_probability(lam, max_goals)}
        for max_goals in [6, 8, 10, 12]
    ]


def weight_check(name: str, weights: dict | list[float]) -> str:
    if isinstance(weights, dict):
        total = sum(weights.values())
        details = ", ".join(f"{key}: {pct(value, 0)}" for key, value in weights.items())
    else:
        total = sum(weights)
        details = ", ".join(pct(value, 0) for value in weights)
    status = "OK" if abs(total - 1.0) < 0.000001 else "DO SPRAWDZENIA"
    return f"- **{name}**: suma wag = {fmt(total, 3)} ({status}); {details}."


def build_report() -> str:
    calendar, teams = load_data()
    latest_date = calendar["latest_date"]
    first_date = calendar["days"][0]["date"]

    conversion = shot_conversion_from_export(calendar)
    conversion_examples = shot_conversion_examples(calendar)
    coverage = match_stat_coverage(calendar)
    base_rates = base_rate_stats(calendar)
    goals_by_day = scored_goals_by_day(calendar)
    priors = fifa_prior_values(teams)
    prior_examples = fifa_prior_examples(teams)
    fifa_width_rows = fifa_width_scenarios(teams)
    fifa_clip_rows = fifa_clip_scenarios(teams)
    shrinkage_rows = shrinkage_scenarios()
    efficiency_prior_rows = efficiency_prior_scenarios(conversion)
    k_shots_rows = k_shots_scenarios()
    form_rows = form_weight_scenarios()
    opponent_rows = opponent_limit_scenarios()
    first_ranges = prediction_ranges(calendar, first_date)
    latest_ranges = prediction_ranges(calendar, latest_date)
    lambdas = expected_goal_lambdas(calendar)
    max_lambda = max(lambdas) if lambdas else BASE_RATE_FALLBACK
    max_lambda_row = max_lambda_example(calendar)
    max_goals_rows = max_goals_scenarios(max_lambda)
    tail_at_max = poisson_tail_probability(max_lambda)
    tail_at_fallback = poisson_tail_probability(BASE_RATE_FALLBACK)

    shrinkage_examples = []
    for matches_played in range(0, 6):
        real_weight = matches_played / (matches_played + SHRINKAGE_K) if matches_played + SHRINKAGE_K else 0
        prior_weight = 1 - real_weight
        shrinkage_examples.append((matches_played, real_weight, prior_weight))

    report = [
        "# Notatka z doboru parametrów modelu",
        "",
        "To nie jest walidacja naukowa ani próba udowodnienia, że model przewiduje mecze lepiej od rynku bukmacherskiego.",
        "To robocze sprawdzenie, czy liczby przyjęte w projekcie mają sens na danych, które są już w eksporcie strony.",
        "",
        f"- Dane wejściowe: `{CALENDAR_PATH.relative_to(ROOT)}` oraz `{TEAMS_PATH.relative_to(ROOT)}`.",
        f"- Zakres eksportu: od `{first_date}` do `{latest_date}`.",
        f"- Liczba drużyn: `{len(teams)}`.",
        f"- Liczba unikalnych meczów z wynikiem w eksporcie: `{len(unique_scored_matches(calendar))}`.",
        f"- Mecze z wynikiem i dowolnymi statystykami: `{coverage['with_any_stats']}`.",
        f"- Mecze z wynikiem i statystykami obu drużyn: `{coverage['with_both_stats']}`.",
        "",
        "## Skąd biorę dane do sprawdzenia?",
        "",
        "Nie pobieram tu niczego z internetu i nie łączę się z bazą danych. Liczę tylko na plikach, które strona już ma wygenerowane.",
        "",
        "Najważniejsze pola:",
        "",
        "- `docs/data/calendar.json -> days[].prediction[]`: dzienne oceny drużyn, szanse i indeksy 0–100.",
        "- `docs/data/calendar.json -> days[].matches[]`: mecze, wyniki, statusy i statystyki meczowe.",
        "- `docs/data/calendar.json -> days[].matches[].home_stats / away_stats`: strzały, strzały celne, posiadanie, podania, kartki itd.",
        "- `docs/data/calendar.json -> days[].base_rate`: średnia goli na drużynę używana w modelu bramkowym.",
        "- `docs/data/teams.json -> fifa_rank_points`: punkty rankingu FIFA używane do punktu startowego.",
        "",
        "Jeśli jakiś mecz nie ma statystyk w `home_stats` albo `away_stats`, pomijam go przy sprawdzaniu skuteczności strzałów. Nie chcę mieszać prawdziwych wyników z pustymi statystykami.",
        "",
        "## 1. Wagi składników",
        "",
        "Najpierw sprawdzam prostą rzecz: czy wagi w każdej grupie sumują się do 100%. Jeśli nie, jedna część oceny mogłaby być przypadkiem wzmocniona.",
        "",
        "Wzór ogólny:",
        "",
        "```text",
        "ocena = składnik_1 × waga_1 + składnik_2 × waga_2 + ...",
        "```",
        "",
        "Te liczby nie pochodzą z JSON-a. To ustawienia zapisane w kodzie modelu. Sprawdzam tylko, czy tworzą pełne 100%.",
        "",
        weight_check("Atak", ATTACK_WEIGHTS),
        weight_check("Obrona", DEFENSE_WEIGHTS),
        weight_check("Kontrola gry", CONTROL_WEIGHTS),
        weight_check("Skuteczność", EFFICIENCY_WEIGHTS),
        weight_check("Dyscyplina", DISCIPLINE_WEIGHTS),
        weight_check("Siła drużyny", STRENGTH_WEIGHTS),
        "",
        "Metoda: średnia ważona. Same proporcje wag są moją decyzją projektową, a nie wartością pobraną z API.",
        "",
        "## 2. Skala 0–100 i punkt neutralny 50",
        "",
        "Tutaj sprawdzam, czy eksportowane indeksy faktycznie zostają w skali 0–100 i czy środek skali wypada blisko neutralnego 50.",
        "",
        "Źródło danych:",
        "",
        "```text",
        "docs/data/calendar.json -> days[].prediction[].strength",
        "docs/data/calendar.json -> days[].prediction[].attack",
        "docs/data/calendar.json -> days[].prediction[].defense",
        "itd.",
        "```",
        "",
        "Sposób liczenia w tej notatce:",
        "",
        "```text",
        "minimum = najmniejsza wartość strength danego dnia",
        "maksimum = największa wartość strength danego dnia",
        "średnia = suma strength wszystkich drużyn / liczba drużyn",
        "```",
        "",
        f"- Pierwszy dzień (`{first_date}`): siła drużyn od `{fmt(first_ranges['strength']['min'])}` do `{fmt(first_ranges['strength']['max'])}`, średnia `{fmt(first_ranges['strength']['mean'])}`.",
        f"- Ostatni dzień eksportu (`{latest_date}`): siła drużyn od `{fmt(latest_ranges['strength']['min'])}` do `{fmt(latest_ranges['strength']['max'])}`, średnia `{fmt(latest_ranges['strength']['mean'])}`.",
        "",
        "Wynik: środek zostaje w okolicach 50, więc 50 działa jak punkt neutralny, a nie jak zawyżona ocena startowa.",
        "Metoda: z-score / standard score.",
        "",
        "## 3. Ranking FIFA jako prior: zakres 35–72 i szerokość 8",
        "",
        "Punkty rankingu FIFA przeliczam tym samym wzorem, którego używa model.",
        "",
        "Źródło danych:",
        "",
        "```text",
        "docs/data/teams.json -> fifa_rank_points",
        "```",
        "",
        "Wzór:",
        "",
        "```text",
        "średnia = średnia punktów FIFA wszystkich drużyn",
        "odchylenie = odchylenie standardowe punktów FIFA",
        "z = (punkty_drużyny - średnia) / odchylenie",
        "prior_surowy = 50 + z × 8",
        "prior_końcowy = ogranicz(prior_surowy do zakresu 35–72)",
        "```",
        "",
        f"- Średnia punktów FIFA w `teams.json`: `{fmt(prior_examples['mean'])}`.",
        f"- Odchylenie standardowe punktów FIFA w `teams.json`: `{fmt(prior_examples['stdev'])}`.",
        "",
        f"- Przeliczony prior FIFA: minimum `{fmt(min(priors))}`, maksimum `{fmt(max(priors))}`, średnia `{fmt(statistics.mean(priors))}`.",
        f"- Liczba drużyn przy dolnym limicie `{FIFA_PRIOR_MIN:g}`: `{sum(1 for value in priors if abs(value - FIFA_PRIOR_MIN) < 0.000001)}`.",
        f"- Liczba drużyn przy górnym limicie `{FIFA_PRIOR_MAX:g}`: `{sum(1 for value in priors if abs(value - FIFA_PRIOR_MAX) < 0.000001)}`.",
        "",
        "Przykłady obliczeń:",
        "",
        "| Drużyna | Punkty FIFA | z-score | prior surowy | prior po ograniczeniu |",
        "|---|---:|---:|---:|---:|",
    ]

    for row in prior_examples["top"][:2] + prior_examples["middle"] + prior_examples["bottom"][-2:]:
        report.append(
            f"| {row['name']} | {fmt(row['points'], 0)} | {fmt(row['z'])} | {fmt(row['raw_prior'])} | {fmt(row['clipped_prior'])} |"
        )

    report.extend(
        [
            "",
            "Jak dobrałam liczbę `8`: porównałam kilka możliwych szerokości wpływu rankingu FIFA.",
            "",
            "| Wartość mnożnika | Najniższy prior bez limitu | Najwyższy prior bez limitu | Rozpiętość | Komentarz |",
            "|---:|---:|---:|---:|---|",
        ]
    )

    for row in fifa_width_rows:
        if row["width"] < FIFA_PRIOR_ZSCORE_WIDTH:
            verdict = "ranking ma mały wpływ"
        elif row["width"] == FIFA_PRIOR_ZSCORE_WIDTH:
            verdict = "zostawiam tę wersję: wpływ jest widoczny, ale nie dominuje startu"
        else:
            verdict = "ranking zaczyna mocno dominować start"
        report.append(
            f"| {row['width']} | {fmt(row['min'])} | {fmt(row['max'])} | {fmt(row['spread'])} | {verdict} |"
        )

    report.extend(
        [
            "",
            "Jak dobrałam zakres `35–72`: sprawdziłam kilka możliwych ograniczeń.",
            "",
            "| Zakres | Minimum po ograniczeniu | Maksimum po ograniczeniu | Średnia | Ile drużyn ucięto od dołu | Ile drużyn ucięto od góry | Komentarz |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )

    for row in fifa_clip_rows:
        if row["range"] == "35-72":
            verdict = "zostawiam tę wersję: ostrożny dół i zapasowy sufit"
        elif row["range"] == "30-70":
            verdict = "w obecnych danych bez wpływu; w przyszłości pozwala na niższy start słabszych drużyn"
        elif row["range"] == "35-70":
            verdict = "podobne w obecnych danych, ale z niższym sufitem bezpieczeństwa"
        elif row["range"] == "35-73":
            verdict = "prawie identyczne; minimalnie luźniejszy sufit"
        else:
            verdict = "mocniej spłaszcza słabsze drużyny"
        report.append(
            f"| {row['range']} | {fmt(row['min'])} | {fmt(row['max'])} | {fmt(row['mean'])} | {row['clipped_low']} | {row['clipped_high']} | {verdict} |"
        )

    report.extend(
        [
            "",
            "Mój wniosek: `8` daje zauważalną różnicę między faworytami i outsiderami, ale nie przenosi drużyn w okolice 80–90 przed pierwszym meczem. Zakres `35–72` traktuję jako bezpiecznik: dolny limit chroni przed zbyt mocnym skreśleniem słabszych drużyn, a górny limit zostawia wysokie oceny na sytuacje potwierdzone już wynikami turnieju.",
        ]
    )

    report.extend(
        [
        "",
        "W praktyce ranking FIFA różnicuje drużyny na starcie, ale nie rozciąga ich do skrajnych wartości 0 i 100.",
        "Metoda: ranking FIFA jako informacja startowa + z-score. Liczby 35, 72 i 8 są ustawieniami dobranymi po sprawdzeniu kilku wariantów.",
        "",
        "## 4. Przyciąganie do punktu startowego: 3 wirtualne mecze",
        "",
        "Tu sprawdzam, jak szybko realne dane zaczynają dominować nad punktem startowym.",
        "",
        "Wzór:",
        "",
        "```text",
        "waga_realnych_danych = rozegrane_mecze / (rozegrane_mecze + 3)",
        "waga_punktu_startowego = 1 - waga_realnych_danych",
        "ocena_końcowa = ocena_z_danych × waga_realnych_danych + prior × waga_punktu_startowego",
        "```",
        "",
        "| Rozegrane mecze | Waga realnych danych | Waga punktu startowego |",
        "|---:|---:|---:|",
    ]
    )

    for matches_played, real_weight, prior_weight in shrinkage_examples:
        report.append(f"| {matches_played} | {pct(real_weight, 1)} | {pct(prior_weight, 1)} |")

    report.extend(
        [
            "",
            "Jak dobrałam liczbę `3`: porównałam kilka możliwych sił przyciągania do punktu startowego.",
            "",
            "| Wirtualne mecze | Waga realnych danych po 1 meczu | po 2 meczach | po 3 meczach | Komentarz |",
            "|---:|---:|---:|---:|---|",
        ]
    )

    for row in shrinkage_rows:
        if row["k"] < SHRINKAGE_K:
            verdict = "szybciej reaguje, większe ryzyko przereagowania"
        elif row["k"] == SHRINKAGE_K:
            verdict = "zostawiam tę wersję: po fazie grupowej dane mają już 50%"
        else:
            verdict = "bardziej zachowawcze, wolniej reaguje na turniej"
        report.append(
            f"| {row['k']} | {pct(row['after_1'], 1)} | {pct(row['after_2'], 1)} | {pct(row['after_3'], 1)} | {verdict} |"
        )

    report.extend(
        [
            "",
            "Mój wniosek: `3` pasuje do struktury mundialu, bo faza grupowa ma trzy mecze. Po trzech meczach realne dane i punkt startowy ważą po 50%, więc model nie ignoruje rankingu po jednym spotkaniu, ale też nie trzyma się go zbyt długo.",
        ]
    )

    report.extend(
        [
            "",
            "Po jednym meczu model nadal jest ostrożny, po trzech meczach realne dane i punkt startowy ważą po 50%, a później rośnie wpływ danych turniejowych.",
            "Metoda: wygładzanie / pseudoobserwacje. Liczba 3 jest dobrana pod trzy mecze fazy grupowej.",
            "",
            "## 5. Skuteczność: 11%, 30% i 15 wirtualnych strzałów",
            "",
            "Tutaj porównuję przyjęte wartości z danymi meczowymi, które są już w eksporcie strony.",
            "",
            "Źródło danych:",
            "",
            "```text",
            "docs/data/calendar.json -> days[].matches[].home_goals / away_goals",
            "docs/data/calendar.json -> days[].matches[].home_stats.shots_total / away_stats.shots_total",
            "docs/data/calendar.json -> days[].matches[].home_stats.shots_on_goal / away_stats.shots_on_goal",
            "```",
            "",
            "Biorę tylko mecze z wynikiem i niepustymi statystykami drużyny.",
            "",
            "Wzory:",
            "",
            "```text",
            "skuteczność wszystkich strzałów = suma_goli / suma_wszystkich_strzałów",
            "skuteczność strzałów celnych = suma_goli / suma_strzałów_celnych",
            "```",
            "",
            f"- Wiersze statystyk drużyn z danymi strzałów: `{conversion['team_rows_with_stats']}`.",
            f"- Gole: `{conversion['goals']}`.",
            f"- Wszystkie strzały: `{conversion['shots_total']}`.",
            f"- Strzały celne: `{conversion['shots_on_goal']}`.",
            f"- Rzeczywiste gole / wszystkie strzały w eksporcie: `{pct(conversion['goals_per_shot'])}`.",
            f"- Rzeczywiste gole / strzały celne w eksporcie: `{pct(conversion['goals_per_sog'])}`.",
            "",
            "Obliczenie zbiorcze:",
            "",
            "```text",
            f"{conversion['goals']} / {conversion['shots_total']} = {pct(conversion['goals_per_shot'])}",
            f"{conversion['goals']} / {conversion['shots_on_goal']} = {pct(conversion['goals_per_sog'])}",
            "```",
            "",
            "Przykładowe wiersze danych użyte w obliczeniu:",
            "",
            "| Kickoff | Team ID | Gole | Strzały | Strzały celne | Gole/strzały | Gole/strzały celne |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )

    for row in conversion_examples:
        report.append(
            f"| {row['kickoff']} | {row['team_id']} | {row['goals']} | {row['shots_total']} | {row['shots_on_goal']} | {pct(row['goals_per_shot'])} | {pct(row['goals_per_sog'])} |"
        )

    report.extend(
        [
            "",
            "Jak dobrałam wartości `11%` i `30%`: porównałam kilka punktów startowych z realną skutecznością w danych projektu.",
            "",
            "| Kandydat dla wszystkich strzałów | Różnica względem danych projektu | Kandydat dla strzałów celnych | Różnica względem danych projektu | Komentarz |",
            "|---:|---:|---:|---:|---|",
        ]
    )

    for row in efficiency_prior_rows:
        if abs(row["shot_prior"] - EFFICIENCY_SHOTS_PRIOR) < 0.000001 and abs(row["sog_prior"] - EFFICIENCY_SOG_PRIOR) < 0.000001:
            verdict = "zostawiam tę wersję: blisko danych, ale ostrożnie dla strzałów celnych"
        elif row["shot_prior"] < EFFICIENCY_SHOTS_PRIOR:
            verdict = "bardziej pesymistyczne"
        elif abs(row["shot_prior"] - conversion["goals_per_shot"]) < 0.000001:
            verdict = "dokładne dopasowanie do obecnej próbki, mniej konserwatywne"
        else:
            verdict = "alternatywa bliska, ale mniej zgodna z danymi"
        report.append(
            f"| {pct(row['shot_prior'])} | {pct(row['shot_diff'])} | {pct(row['sog_prior'])} | {pct(row['sog_diff'])} | {verdict} |"
        )

    report.extend(
        [
            "",
            "Jak dobrałam liczbę `15`: porównałam siłę wygładzania na dwóch prostych przykładach.",
            "",
            "| Wirtualne strzały | 2 gole / 2 strzały po wygładzeniu | 5 goli / 20 strzałów po wygładzeniu | Komentarz |",
            "|---:|---:|---:|---|",
        ]
    )

    for row in k_shots_rows:
        if row["k"] < K_SHOTS:
            verdict = "słabsze wygładzenie, nadal mocno reaguje na małą próbkę"
        elif row["k"] == K_SHOTS:
            verdict = "zostawiam tę wersję: umiarkowane wygładzenie"
        else:
            verdict = "mocniejsze wygładzenie, wolniej ufa realnym strzałom"
        report.append(
            f"| {row['k']} | {pct(row['two_of_two'])} | {pct(row['five_of_twenty'])} | {verdict} |"
        )

    report.extend(
        [
            "",
            "Mój wniosek: `11%` wynika z porównania z aktualną skutecznością wszystkich strzałów w danych projektu (`11.74%`). `30%` zostawiam niżej niż aktualne `34.79%`, bo ma być ostrożnym punktem startowym. `15` wirtualnych strzałów ogranicza skok do 100% przy próbie 2/2, ale nie przykrywa całkowicie realnych danych.",
        ]
    )

    report.extend(
        [
            "",
            f"Przyjęte `{pct(EFFICIENCY_SHOTS_PRIOR, 0)}` dla wszystkich strzałów jest blisko danych projektu, a `{pct(EFFICIENCY_SOG_PRIOR, 0)}` dla strzałów celnych jest celowo niżej od aktualnej próbki.",
            "",
            "Dodatkowe sprawdzenie: drużyna z 2 golami z 2 strzałów nie dostaje 100% skuteczności.",
            "",
            "- Bez wygładzania: `2 / 2 = 100%`.",
            f"- Z wygładzaniem wszystkich strzałów: `(2 + {K_SHOTS} × {EFFICIENCY_SHOTS_PRIOR}) / (2 + {K_SHOTS}) = {pct((2 + K_SHOTS * EFFICIENCY_SHOTS_PRIOR) / (2 + K_SHOTS))}`.",
            "",
            "Metoda: xG jako myślenie o strzale przez prawdopodobieństwo gola + additive smoothing. Liczby 11%, 30% i 15 są ustawieniami dobranymi w tym projekcie.",
            "",
            "## 6. Forma: 3 mecze, wagi 50% / 30% / 20% i różnica bramek dzielona przez 3",
            "",
            "Sprawdzam, czy wagi formy sumują się do 100% i jak działa ograniczenie różnicy bramek.",
            "",
            "Źródło danych dla formy w modelu:",
            "",
            "```text",
            "docs/data/calendar.json -> days[].matches[].home_goals / away_goals",
            "docs/data/calendar.json -> days[].matches[].home_team_id / away_team_id",
            "```",
            "",
            "Wzór dla różnicy bramek:",
            "",
            "```text",
            "składnik_różnicy = ogranicz((gole_drużyny - gole_rywala) / 3, od -1 do 1)",
            "```",
            "",
            weight_check("Forma", FORM_WEIGHTS),
            "",
            "| Różnica bramek | Składnik przed ograniczeniem | Składnik po ograniczeniu |",
            "|---:|---:|---:|",
        ]
    )

    for diff in [-5, -3, -2, -1, 0, 1, 2, 3, 5]:
        raw = diff / GOAL_DIFF_DIVISOR
        clipped = max(-1.0, min(1.0, raw))
        report.append(f"| {diff:+d} | {fmt(raw)} | {fmt(clipped)} |")

    report.extend(
        [
            "",
            "Jak dobrałam wagi `50% / 30% / 20%`: porównałam kilka podejść do formy.",
            "",
            "| Wariant | Wagi meczów od najnowszego | Co oznacza |",
            "|---|---|---|",
        ]
    )

    for row in form_rows:
        weights = " / ".join(pct(value, 0) for value in row["weights"])
        if row["name"] == "równe":
            meaning = "każdy z 3 meczów ma taki sam wpływ, mniej czułe na aktualny trend"
        elif row["name"] == "wybrane":
            meaning = "zostawiam tę wersję: najnowszy mecz jest najważniejszy, ale starsze nadal stabilizują ocenę"
        else:
            meaning = "bardzo mocno premiuje ostatni mecz, większe ryzyko przereagowania"
        report.append(f"| {row['name']} | {weights} | {meaning} |")

    report.extend(
        [
            "",
            "Mój wniosek: `50/30/20` jest środkiem między równym traktowaniem trzech meczów a zbyt mocnym uzależnieniem formy od ostatniego wyniku.",
        ]
    )

    report.extend(
        [
            "",
            "Zwycięstwo trzema golami jest traktowane jako bardzo mocny sygnał, ale wyższe wyniki nie zwiększają formy bez końca.",
            "Metoda: krótka średnia ważona. Liczby 3 oraz 50/30/20 są ustawieniami projektu.",
            "",
            "## 7. Jakość rywala: mnożnik 0.4–2.5",
            "",
            "Sprawdzam, czy limity działają jako zabezpieczenie, a nie jako główny mechanizm sterujący całą oceną.",
            "",
            "Źródło danych:",
            "",
            "```text",
            "docs/data/calendar.json -> days[].prediction[].attack",
            "docs/data/calendar.json -> days[].prediction[].defense",
            "```",
            "",
            "Wzory używane w modelu:",
            "",
            "```text",
            "mnożnik_obrony_rywala = defense_rywala / 50",
            "mnożnik_ataku_rywala = 50 / attack_rywala",
            "wynik mnożnika jest ograniczany do zakresu 0.4–2.5",
            "```",
            "",
            f"- Limit minimalny: `{OPPONENT_ADJUSTMENT_MIN}`.",
            f"- Limit maksymalny: `{OPPONENT_ADJUSTMENT_MAX}`.",
            f"- W ostatnim dniu eksportu Attack mieści się od `{fmt(latest_ranges['attack']['min'])}` do `{fmt(latest_ranges['attack']['max'])}`.",
            f"- W ostatnim dniu eksportu Defense mieści się od `{fmt(latest_ranges['defense']['min'])}` do `{fmt(latest_ranges['defense']['max'])}`.",
            "",
            "Jak dobrałam zakres `0.4–2.5`: porównałam limity na przykładowych surowych mnożnikach.",
            "",
            "| Surowy mnożnik | Wąski limit 0.7–1.6 | Wybrany limit 0.4–2.5 | Szeroki limit 0.2–4.0 |",
            "|---:|---:|---:|---:|",
        ]
    )

    for row in opponent_rows:
        report.append(f"| {fmt(row['raw'])} | {fmt(row['narrow'])} | {fmt(row['chosen'])} | {fmt(row['wide'])} |")

    report.extend(
        [
            "",
            "Mój wniosek: `0.4–2.5` jest kompromisem. Wąski limit zbyt mocno spłaszcza jakość rywala, a szeroki limit pozwalałby pojedynczym skrajnościom za mocno zmieniać ocenę.",
            "Przy obecnych danych drużyny są daleko od wartości skrajnych 0 i 100, więc limity 0.4–2.5 pełnią głównie rolę bezpiecznika na nietypowe sytuacje.",
            "Metoda: ważenie wyniku jakością przeciwnika. Konkretne limity są technicznym ustawieniem projektu.",
            "",
            "## 8. Średnia bramek: awaryjne 1.3 gola na drużynę",
            "",
            "Porównuję fallback 1.3 z realnymi średnimi zapisanymi w eksporcie.",
            "",
            "Źródło danych:",
            "",
            "```text",
            "docs/data/calendar.json -> days[].base_rate",
            "docs/data/calendar.json -> days[].matches[].home_goals / away_goals",
            "```",
            "",
            "Wzór logiczny:",
            "",
            "```text",
            "base_rate = suma_goli / liczba_występów_drużyn",
            "liczba_występów_drużyn = liczba_meczów × 2",
            "```",
            "",
            "Przykłady dni z eksportu:",
            "",
            "| Data | Gole w meczach tego dnia | Występy drużyn | Gole / występ drużyny | base_rate w eksporcie |",
            "|---|---:|---:|---:|---:|",
        ]
    )

    for row in goals_by_day[:2] + goals_by_day[-3:]:
        per_team = "" if row["goals_per_team_match"] is None else fmt(row["goals_per_team_match"], 3)
        report.append(
            f"| {row['date']} | {row['goals']} | {row['team_match_count']} | {per_team} | {fmt(row['exported_base_rate'], 3)} |"
        )

    report.extend(
        [
            "",
            "Jak dobrałam fallback `1.3`: porównałam kilka możliwych wartości startowych z późniejszymi średnimi z eksportu.",
            "",
            "| Kandydat fallbacku | Gole łącznie w meczu | Różnica względem średniej dni eksportu | Komentarz |",
            "|---:|---:|---:|---|",
        ]
    )

    for candidate in [1.0, 1.2, 1.3, 1.5, 1.7]:
        if candidate < BASE_RATE_FALLBACK:
            verdict = "bardziej ostrożny, może zaniżać liczbę goli"
        elif abs(candidate - BASE_RATE_FALLBACK) < 0.000001:
            verdict = "zostawiam tę wersję: ostrożnie poniżej średniej z eksportu"
        else:
            verdict = "bardziej ofensywny, bliżej/wyżej aktualnej średniej"
        report.append(
            f"| {fmt(candidate, 2)} | {fmt(candidate * 2, 2)} | {fmt(candidate - base_rates['mean'], 3)} | {verdict} |"
        )

    report.extend(
        [
            "",
            "`1.3` zostaje jako start niższy od aktualnej średniej z eksportu (`{}`), czyli ostrożny fallback używany tylko wtedy, gdy nie ma jeszcze danych turniejowych.".format(fmt(base_rates["mean"], 3)),
        ]
    )

    report.extend(
        [
            "",
            f"- Pierwsza zapisana wartość `base_rate`: `{fmt(base_rates['first'], 3)}`.",
            f"- Ostatnia zapisana wartość `base_rate`: `{fmt(base_rates['latest'], 3)}`.",
            f"- Minimum w eksporcie: `{fmt(base_rates['minimum'], 3)}`.",
            f"- Maksimum w eksporcie: `{fmt(base_rates['maximum'], 3)}`.",
            f"- Średnia z dni eksportu: `{fmt(base_rates['mean'], 3)}`.",
            "",
            f"Fallback `{BASE_RATE_FALLBACK}` jest ostrożnym punktem startowym. Gdy pojawiają się mecze, model używa realnej średniej turniejowej.",
            "Metoda: średnia goli jako parametr bazowy modelu Poissona. Liczba 1.3 jest ustawieniem projektu.",
            "",
            "## 9. Model Poissona i maksymalnie 10 goli",
            "",
            "Sprawdzam, jak duży ogon rozkładu odcinam przy 10 golach.",
            "",
            "Źródło danych dla lambdy:",
            "",
            "```text",
            "docs/data/calendar.json -> days[].base_rate",
            "docs/data/calendar.json -> days[].prediction[].attack",
            "docs/data/calendar.json -> days[].prediction[].defense",
            "```",
            "",
            "Wzór:",
            "",
            "```text",
            "lambda = base_rate × (attack / 50) × ((100 - defense_rywala) / 50)",
            "```",
            "",
        ]
    )

    if max_lambda_row:
        report.extend(
            [
                "Największa lambda znaleziona w eksporcie:",
                "",
                "```text",
                f"data = {max_lambda_row['date']}",
                f"team_id = {max_lambda_row['team_id']}",
                f"opponent_id = {max_lambda_row['opponent_id']}",
                f"base_rate = {fmt(max_lambda_row['base_rate'], 3)}",
                f"attack = {fmt(max_lambda_row['attack'])}",
                f"defense_rywala = {fmt(max_lambda_row['opponent_defense'])}",
                f"lambda = {fmt(max_lambda_row['base_rate'], 3)} × ({fmt(max_lambda_row['attack'])} / 50) × ((100 - {fmt(max_lambda_row['opponent_defense'])}) / 50)",
                f"lambda = {fmt(max_lambda_row['lambda'], 3)}",
                "```",
                "",
            ]
        )

    report.extend(
        [
            "Jak dobrałam limit `10`: porównałam, ile prawdopodobieństwa obcinam przy różnych limitach goli.",
            "",
            "| Limit goli | Prawdopodobieństwo wyniku powyżej limitu przy największej lambdzie | Komentarz |",
            "|---:|---:|---|",
        ]
    )

    for row in max_goals_rows:
        if row["max_goals"] < MAX_GOALS:
            verdict = "szybsze, ale odcina większy ogon"
        elif row["max_goals"] == MAX_GOALS:
            verdict = "zostawiam tę wersję: ogon jest już pomijalny"
        else:
            verdict = "dokładniejsze minimalnie, ale mało zmienia wynik"
        report.append(f"| {row['max_goals']} | {pct(row['tail'], 6)} | {verdict} |")

    report.extend(
        [
            "",
            f"- Prawdopodobieństwo więcej niż 10 goli przy lambda `{BASE_RATE_FALLBACK}`: `{pct(tail_at_fallback, 6)}`.",
            f"- Największa lambda znaleziona w eksporcie meczów: `{fmt(max_lambda, 3)}`.",
            f"- Prawdopodobieństwo więcej niż 10 goli przy tej lambdzie: `{pct(tail_at_max, 6)}`.",
            "",
            "Odcięcie przy 10 golach pomija skrajnie mały ogon rozkładu, a znacząco upraszcza obliczenia.",
            "Metoda: rozkład Poissona. Liczba 10 jest technicznym ustawieniem projektu.",
            "",
            "## 10. Liczba symulacji: 10 000",
            "",
            "Szacuję typowy błąd losowy proporcji przy różnych liczbach symulacji. Dla uproszczenia biorę najtrudniejszy przypadek p=50%, gdzie błąd jest największy.",
            "",
            "Wzór:",
            "",
            "```text",
            "błąd_standardowy = sqrt(p × (1 - p) / liczba_symulacji)",
            "dla najtrudniejszego przypadku przyjmujemy p = 0.5",
            "```",
            "",
            "| Liczba symulacji | Przybliżony błąd standardowy |",
            "|---:|---:|",
        ]
    )

    for n in [1_000, 5_000, 10_000, 20_000]:
        report.append(f"| {n:,}".replace(",", " ") + f" | {pct(monte_carlo_standard_error(n), 2)} |")

    report.extend(
        [
            "",
            "Jak dobrałam `10 000`: 1 000 symulacji jest szybkie, ale błąd losowy jest ponad trzy razy większy niż przy 10 000. 20 000 daje mniejszy błąd, ale kosztuje więcej czasu, a zysk dla dashboardu jest już niewielki.",
            f"Przy `{str(N_SIMULATIONS).replace('10000', '10 000')}` symulacji błąd losowy dla pojedynczej proporcji jest już niewielki, a obliczenia nadal są praktyczne lokalnie.",
            "Metoda: Monte Carlo. Liczba 10 000 jest ustawieniem projektu.",
            "",
            "## Źródła metod",
            "",
            "Poniższe źródła nie podają konkretnych parametrów tego projektu. Uzasadniają metody, na których projekt się opiera:",
            "",
            "- z-score / standaryzacja: https://en.wikipedia.org/wiki/Standard_score",
            "- expected goals, czyli traktowanie strzału jako prawdopodobieństwa gola: https://en.wikipedia.org/wiki/Expected_goals",
            "- additive smoothing, czyli wygładzanie przez pseudoobserwacje: https://en.wikipedia.org/wiki/Additive_smoothing",
            "- rozkład Poissona: https://en.wikipedia.org/wiki/Poisson_distribution",
            "- metoda Monte Carlo: https://en.wikipedia.org/wiki/Monte_Carlo_method",
            "- ranking FIFA jako punkt odniesienia dla siły reprezentacji: https://en.wikipedia.org/wiki/FIFA_Men%27s_World_Ranking",
            "",
            "## Podsumowanie",
            "",
            "Te sprawdzenia nie udowadniają, że model zna przyszłość. Pokazują coś prostszego: liczby są jawne, sprawdzalne i nie są oderwane od danych, które projekt już posiada.",
            "",
            "Najmocniej lokalnymi danymi wspierane są parametry skuteczności strzałów oraz fallback średniej bramek. Pozostałe liczby są parametrami kalibracyjnymi: ich rolą jest stabilizacja modelu, ograniczanie skrajności i zachowanie czytelnej interpretacji wyników.",
            "",
        ]
    )

    return "\n".join(report)


def main() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(build_report(), encoding="utf-8")
    print(f"Zapisano raport: {REPORT_PATH}")


if __name__ == "__main__":
    main()
