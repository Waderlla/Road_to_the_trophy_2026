"""Etap 3 metodologii: model Poissona na bramkach. Wspolne dla raportu
(06_match_probability.py) i symulacji Monte Carlo (07_simulate_tournament.py)."""

import math

MAX_GOALS = 10  # obciecie rozkladu Poissona - P(>10 goli) jest pomijalne


def poisson_pmf(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def expected_goals(attack, opp_defense, base_rate):
    """Oczekiwane gole druzyny na podstawie jej Attack i Defense przeciwnika
    (oba 0-100, srednia turnieju = 50).

    attack/50 -> mnoznik wzgledem sredniej sily ataku (1.0 = przecietny atak)
    (100-opp_defense)/50 -> mnoznik dziurawosci obrony rywala (1.0 = przecietna
    obrona; slaba obrona rywala > 1.0, mocna obrona rywala < 1.0)
    base_rate -> srednia liczba goli na druzyne na mecz w turnieju do tej pory
    """
    attack_factor = attack / 50
    defense_factor = (100 - opp_defense) / 50
    return max(0.05, base_rate * attack_factor * defense_factor)


def match_result_probabilities(attack_a, defense_a, attack_b, defense_b, base_rate):
    """Zwraca (p_win_a, p_draw, p_win_b) na podstawie modelu Poissona na
    bramkach - niezalezne rozklady goli obu druzyn, zsumowane po wszystkich
    kombinacjach wyniku."""
    lam_a = expected_goals(attack_a, defense_b, base_rate)
    lam_b = expected_goals(attack_b, defense_a, base_rate)

    p_win_a = p_draw = p_win_b = 0.0
    for i in range(MAX_GOALS + 1):
        p_i = poisson_pmf(i, lam_a)
        for j in range(MAX_GOALS + 1):
            p_j = poisson_pmf(j, lam_b)
            p = p_i * p_j
            if i > j:
                p_win_a += p
            elif i == j:
                p_draw += p
            else:
                p_win_b += p

    total = p_win_a + p_draw + p_win_b
    return p_win_a / total, p_draw / total, p_win_b / total
