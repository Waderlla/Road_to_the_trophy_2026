import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import get_connection
from poisson_model import match_result_probabilities

FINISHED_STATUSES = ("FT", "AET", "PEN")


def fetch_base_rate(cur, calc_date):
    """Srednia liczba goli strzelonych na druzyne na mecz w turnieju do danego
    dnia wlacznie - dynamiczny punkt odniesienia zamiast sztywnej stalej."""
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


def fetch_latest_strength(cur):
    cur.execute(
        """
        SELECT ds.team_id, t.name, ds.attack, ds.defense, ds.calc_date
        FROM daily_strength ds
        JOIN teams t ON t.team_id = ds.team_id
        WHERE ds.calc_date = (SELECT MAX(calc_date) FROM daily_strength)
        """
    )
    return {row[1]: {"team_id": row[0], "attack": float(row[2]), "defense": float(row[3])} for row in cur.fetchall()}


def main():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(calc_date) FROM daily_strength")
            latest_date = cur.fetchone()[0]
            base_rate = fetch_base_rate(cur, latest_date)
            strengths = fetch_latest_strength(cur)

        print(f"Dzien: {latest_date}, bazowa liczba goli/druzyne/mecz: {base_rate:.3f}\n")

        examples = [
            ("France", "Sweden"),
            ("Spain", "Austria"),
            ("Portugal", "Croatia"),
        ]
        for name_a, name_b in examples:
            if name_a not in strengths or name_b not in strengths:
                continue
            a, b = strengths[name_a], strengths[name_b]
            p_a, p_draw, p_b = match_result_probabilities(
                a["attack"], a["defense"], b["attack"], b["defense"], base_rate
            )
            print(f"{name_a} vs {name_b}: {p_a:.1%} / remis {p_draw:.1%} / {p_b:.1%} ({name_b})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
