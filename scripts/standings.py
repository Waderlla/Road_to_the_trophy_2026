"""Tabele grupowe wg regul FIFA: punkty -> roznica bramek -> bramki strzelone
-> mecz bezposredni (w tej samej kolejnosci, ale tylko miedzy zremisowanymi
druzynami) -> losowanie. Uzywane zarowno do sprawdzenia realnych tabel, jak i
wewnatrz symulacji Monte Carlo (gdzie czesc/wszystkie wyniki sa losowane)."""


def team_stats(team_id, group_matches):
    pts = gf = ga = 0
    for home_id, away_id, home_goals, away_goals in group_matches:
        if team_id not in (home_id, away_id):
            continue
        if team_id == home_id:
            my, opp = home_goals, away_goals
        else:
            my, opp = away_goals, home_goals
        gf += my
        ga += opp
        if my > opp:
            pts += 3
        elif my == opp:
            pts += 1
    return pts, gf - ga, gf


def _resolve_tied_group(tied_ids, all_matches, rng):
    """tied_ids maja identyczne (pkt, roznica, strzelone) w calej grupie -
    rozstrzygamy mikro-tabela tylko z meczow miedzy nimi, a przy dalszym
    remisie losowo (jak w regulaminie FIFA - "drawing of lots")."""
    if len(tied_ids) == 1:
        return list(tied_ids)

    h2h_matches = [
        m for m in all_matches
        if m[0] in tied_ids and m[1] in tied_ids
    ]
    h2h_stats = {t: team_stats(t, h2h_matches) for t in tied_ids}

    groups = {}
    for t in tied_ids:
        groups.setdefault(h2h_stats[t], []).append(t)

    result = []
    for key in sorted(groups.keys(), reverse=True):
        bucket = groups[key]
        if len(bucket) > 1:
            rng.shuffle(bucket)
        result.extend(bucket)
    return result


def rank_group(team_ids, group_matches, rng):
    """Zwraca liste 4 team_id w kolejnosci 1-2-3-4 wg tabeli grupowej."""
    stats = {t: team_stats(t, group_matches) for t in team_ids}

    buckets = {}
    for t in team_ids:
        buckets.setdefault(stats[t], []).append(t)

    ordered = []
    for key in sorted(buckets.keys(), reverse=True):
        ordered.extend(_resolve_tied_group(buckets[key], group_matches, rng))
    return ordered


def rank_third_places(third_place_by_group, all_group_matches, rng):
    """third_place_by_group: dict grupa -> team_id trzeciego miejsca.
    Zwraca liste team_id posortowana od najlepszego trzeciego miejsca
    (uzywajac pkt/roznica/strzelone z calej fazy grupowej danej druzyny -
    mecz bezposredni nie ma zastosowania, bo to druzyny z roznych grup)."""
    thirds = list(third_place_by_group.values())
    stats = {t: team_stats(t, all_group_matches) for t in thirds}

    buckets = {}
    for t in thirds:
        buckets.setdefault(stats[t], []).append(t)

    ordered = []
    for key in sorted(buckets.keys(), reverse=True):
        bucket = buckets[key]
        if len(bucket) > 1:
            rng.shuffle(bucket)
        ordered.extend(bucket)
    return ordered
