# Notatka z doboru parametrów modelu

Robocze sprawdzenie, czy liczby przyjęte w projekcie mają sens na danych, które są już w eksporcie strony.

- Dane wejściowe: `docs\data\calendar.json` oraz `docs\data\teams.json`.
- Zakres eksportu: od `2026-06-11` do `2026-07-08`.
- Liczba drużyn: `48`.
- Liczba unikalnych meczów z wynikiem w eksporcie: `96`.
- Mecze z wynikiem i dowolnymi statystykami: `96`.
- Mecze z wynikiem i statystykami obu drużyn: `96`.

## Skąd biorę dane do sprawdzenia?

Nie pobieram tu niczego z internetu i nie łączę się z bazą danych. Liczę tylko na plikach, które strona już ma wygenerowane.

Najważniejsze pola:

- `docs/data/calendar.json -> days[].prediction[]`: dzienne oceny drużyn, szanse i indeksy 0–100.
- `docs/data/calendar.json -> days[].matches[]`: mecze, wyniki, statusy i statystyki meczowe.
- `docs/data/calendar.json -> days[].matches[].home_stats / away_stats`: strzały, strzały celne, posiadanie, podania, kartki itd.
- `docs/data/calendar.json -> days[].base_rate`: średnia goli na drużynę używana w modelu bramkowym.
- `docs/data/teams.json -> fifa_rank_points`: punkty rankingu FIFA używane do punktu startowego.

Jeśli jakiś mecz nie ma statystyk w `home_stats` albo `away_stats`, pomijam go przy sprawdzaniu skuteczności strzałów. Nie chcę mieszać prawdziwych wyników z pustymi statystykami.

## 1. Wagi składników

Najpierw sprawdzam prostą rzecz: czy wagi w każdej grupie sumują się do 100%. Jeśli nie, jedna część oceny mogłaby być przypadkiem wzmocniona.

Wzór ogólny:

```text
ocena = składnik_1 × waga_1 + składnik_2 × waga_2 + ...
```

Te liczby nie pochodzą z JSON-a. To ustawienia zapisane w kodzie modelu. Sprawdzam tylko, czy tworzą pełne 100%.

- **Atak**: suma wag = 1.000 (OK); goals: 50%, shots_total: 25%, shots_on_goal: 25%.
- **Obrona**: suma wag = 1.000 (OK); goals_against: 35%, opp_xg: 20%, opp_shots_on_goal: 20%, opp_shots_total: 15%, clean_sheets: 10%.
- **Kontrola gry**: suma wag = 1.000 (OK); possession: 40%, pass_accuracy: 30%, passes_total: 30%.
- **Skuteczność**: suma wag = 1.000 (OK); goals_per_shot: 50%, goals_per_shot_on_target: 50%.
- **Dyscyplina**: suma wag = 1.000 (OK); fouls: 50%, cards: 50%.
- **Siła drużyny**: suma wag = 1.000 (OK); attack: 30%, defense: 30%, efficiency: 15%, control: 15%, form: 5%, discipline: 5%.

Metoda: średnia ważona. Same proporcje wag są moją decyzją projektową, a nie wartością pobraną z API.

## 2. Skala 0–100 i punkt neutralny 50

Tutaj sprawdzam, czy eksportowane indeksy faktycznie zostają w skali 0–100 i czy środek skali wypada blisko neutralnego 50.

Źródło danych:

```text
docs/data/calendar.json -> days[].prediction[].strength
docs/data/calendar.json -> days[].prediction[].attack
docs/data/calendar.json -> days[].prediction[].defense
itd.
```

Sposób liczenia w tej notatce:

```text
minimum = najmniejsza wartość strength danego dnia
maksimum = największa wartość strength danego dnia
średnia = suma strength wszystkich drużyn / liczba drużyn
```

- Pierwszy dzień (`2026-06-11`): siła drużyn od `36.31` do `63.90`, średnia `50.02`.
- Ostatni dzień eksportu (`2026-07-08`): siła drużyn od `32.66` do `68.98`, średnia `50.24`.

Wynik: środek zostaje w okolicach 50, więc 50 działa jak punkt neutralny, a nie jak zawyżona ocena startowa.
Metoda: z-score / standard score.

## 3. Ranking FIFA jako prior: zakres 35–72 i szerokość 8

Punkty rankingu FIFA przeliczam tym samym wzorem, którego używa model.

Źródło danych:

```text
docs/data/teams.json -> fifa_rank_points
```

Wzór:

```text
średnia = średnia punktów FIFA wszystkich drużyn
odchylenie = odchylenie standardowe punktów FIFA
z = (punkty_drużyny - średnia) / odchylenie
prior_surowy = 50 + z × 8
prior_końcowy = ogranicz(prior_surowy do zakresu 35–72)
```

- Średnia punktów FIFA w `teams.json`: `1580.67`.
- Odchylenie standardowe punktów FIFA w `teams.json`: `155.62`.

- Przeliczony prior FIFA: minimum `35.00`, maksimum `65.23`, średnia `50.01`.
- Liczba drużyn przy dolnym limicie `35`: `1`.
- Liczba drużyn przy górnym limicie `72`: `0`.

Przykłady obliczeń:

| Drużyna | Punkty FIFA | z-score | prior surowy | prior po ograniczeniu |
|---|---:|---:|---:|---:|
| Argentyna | 1877 | 1.90 | 65.23 | 65.23 |
| Hiszpania | 1875 | 1.89 | 65.13 | 65.13 |
| Australia | 1579 | -0.01 | 49.91 | 49.91 |
| Haiti | 1293 | -1.85 | 35.21 | 35.21 |
| Nowa Zelandia | 1276 | -1.96 | 34.34 | 35.00 |

Jak dobrałam liczbę `8`: porównałam kilka możliwych szerokości wpływu rankingu FIFA.

| Wartość mnożnika | Najniższy prior bez limitu | Najwyższy prior bez limitu | Rozpiętość | Komentarz |
|---:|---:|---:|---:|---|
| 3 | 44.13 | 55.71 | 11.59 | ranking ma mały wpływ |
| 5 | 40.21 | 59.52 | 19.31 | ranking ma mały wpływ |
| 8 | 34.34 | 65.23 | 30.90 | zostawiam tę wersję: wpływ jest widoczny, ale nie dominuje startu |
| 12 | 26.51 | 72.85 | 46.34 | ranking zaczyna mocno dominować start |
| 15 | 20.63 | 78.56 | 57.93 | ranking zaczyna mocno dominować start |

Jak dobrałam zakres `35–72`: sprawdziłam kilka możliwych ograniczeń.

| Zakres | Minimum po ograniczeniu | Maksimum po ograniczeniu | Średnia | Ile drużyn ucięto od dołu | Ile drużyn ucięto od góry | Komentarz |
|---|---:|---:|---:|---:|---:|---|
| 30-70 | 34.34 | 65.23 | 50.00 | 0 | 0 | w obecnych danych bez wpływu; w przyszłości pozwala na niższy start słabszych drużyn |
| 35-70 | 35.00 | 65.23 | 50.01 | 1 | 0 | podobne w obecnych danych, ale z niższym sufitem bezpieczeństwa |
| 35-72 | 35.00 | 65.23 | 50.01 | 1 | 0 | zostawiam tę wersję: ostrożny dół i zapasowy sufit |
| 35-73 | 35.00 | 65.23 | 50.01 | 1 | 0 | prawie identyczne; minimalnie luźniejszy sufit |
| 40-70 | 40.00 | 65.23 | 50.37 | 5 | 0 | mocniej spłaszcza słabsze drużyny |

Mój wniosek: `8` daje zauważalną różnicę między faworytami i outsiderami, ale nie przenosi drużyn w okolice 80–90 przed pierwszym meczem. Zakres `35–72` traktuję jako bezpiecznik: dolny limit chroni przed zbyt mocnym skreśleniem słabszych drużyn, a górny limit zostawia wysokie oceny na sytuacje potwierdzone już wynikami turnieju.

W praktyce ranking FIFA różnicuje drużyny na starcie, ale nie rozciąga ich do skrajnych wartości 0 i 100.
Metoda: ranking FIFA jako informacja startowa + z-score. Liczby 35, 72 i 8 są ustawieniami dobranymi po sprawdzeniu kilku wariantów.

## 4. Przyciąganie do punktu startowego: 3 wirtualne mecze

Tu sprawdzam, jak szybko realne dane zaczynają dominować nad punktem startowym.

Wzór:

```text
waga_realnych_danych = rozegrane_mecze / (rozegrane_mecze + 3)
waga_punktu_startowego = 1 - waga_realnych_danych
ocena_końcowa = ocena_z_danych × waga_realnych_danych + prior × waga_punktu_startowego
```

| Rozegrane mecze | Waga realnych danych | Waga punktu startowego |
|---:|---:|---:|
| 0 | 0.0% | 100.0% |
| 1 | 25.0% | 75.0% |
| 2 | 40.0% | 60.0% |
| 3 | 50.0% | 50.0% |
| 4 | 57.1% | 42.9% |
| 5 | 62.5% | 37.5% |

Jak dobrałam liczbę `3`: porównałam kilka możliwych sił przyciągania do punktu startowego.

| Wirtualne mecze | Waga realnych danych po 1 meczu | po 2 meczach | po 3 meczach | Komentarz |
|---:|---:|---:|---:|---|
| 1 | 50.0% | 66.7% | 75.0% | szybciej reaguje, większe ryzyko przereagowania |
| 2 | 33.3% | 50.0% | 60.0% | szybciej reaguje, większe ryzyko przereagowania |
| 3 | 25.0% | 40.0% | 50.0% | zostawiam tę wersję: po fazie grupowej dane mają już 50% |
| 5 | 16.7% | 28.6% | 37.5% | bardziej zachowawcze, wolniej reaguje na turniej |
| 8 | 11.1% | 20.0% | 27.3% | bardziej zachowawcze, wolniej reaguje na turniej |

Mój wniosek: `3` pasuje do struktury mundialu, bo faza grupowa ma trzy mecze. Po trzech meczach realne dane i punkt startowy ważą po 50%, więc model nie ignoruje rankingu po jednym spotkaniu, ale też nie trzyma się go zbyt długo.

Po jednym meczu model nadal jest ostrożny, po trzech meczach realne dane i punkt startowy ważą po 50%, a później rośnie wpływ danych turniejowych.
Metoda: wygładzanie / pseudoobserwacje. Liczba 3 jest dobrana pod trzy mecze fazy grupowej.

## 5. Skuteczność: 11%, 30% i 15 wirtualnych strzałów

Tutaj porównuję przyjęte wartości z danymi meczowymi, które są już w eksporcie strony.

Źródło danych:

```text
docs/data/calendar.json -> days[].matches[].home_goals / away_goals
docs/data/calendar.json -> days[].matches[].home_stats.shots_total / away_stats.shots_total
docs/data/calendar.json -> days[].matches[].home_stats.shots_on_goal / away_stats.shots_on_goal
```

Biorę tylko mecze z wynikiem i niepustymi statystykami drużyny.

Wzory:

```text
skuteczność wszystkich strzałów = suma_goli / suma_wszystkich_strzałów
skuteczność strzałów celnych = suma_goli / suma_strzałów_celnych
```

- Wiersze statystyk drużyn z danymi strzałów: `192`.
- Gole: `280`.
- Wszystkie strzały: `2352`.
- Strzały celne: `797`.
- Rzeczywiste gole / wszystkie strzały w eksporcie: `11.90%`.
- Rzeczywiste gole / strzały celne w eksporcie: `35.13%`.

Obliczenie zbiorcze:

```text
280 / 2352 = 11.90%
280 / 797 = 35.13%
```

Przykładowe wiersze danych użyte w obliczeniu:

| Kickoff | Team ID | Gole | Strzały | Strzały celne | Gole/strzały | Gole/strzały celne |
|---|---:|---:|---:|---:|---:|---:|
| 2026-06-11T21:00:00+02:00 | 40 | 2 | 16 | 4 | 12.50% | 50.00% |
| 2026-06-11T21:00:00+02:00 | 42 | 0 | 3 | 2 | 0.00% | 0.00% |
| 2026-06-12T04:00:00+02:00 | 91 | 2 | 15 | 6 | 13.33% | 33.33% |

Jak dobrałam wartości `11%` i `30%`: porównałam kilka punktów startowych z realną skutecznością w danych projektu.

| Kandydat dla wszystkich strzałów | Różnica względem danych projektu | Kandydat dla strzałów celnych | Różnica względem danych projektu | Komentarz |
|---:|---:|---:|---:|---|
| 8.00% | -3.90% | 25.00% | -10.13% | bardziej pesymistyczne |
| 10.00% | -1.90% | 30.00% | -5.13% | bardziej pesymistyczne |
| 11.00% | -0.90% | 30.00% | -5.13% | zostawiam tę wersję: blisko danych, ale ostrożnie dla strzałów celnych |
| 11.90% | 0.00% | 35.13% | 0.00% | dokładne dopasowanie do obecnej próbki, mniej konserwatywne |

Jak dobrałam liczbę `15`: porównałam siłę wygładzania na dwóch prostych przykładach.

| Wirtualne strzały | 2 gole / 2 strzały po wygładzeniu | 5 goli / 20 strzałów po wygładzeniu | Komentarz |
|---:|---:|---:|---|
| 5 | 36.43% | 22.20% | słabsze wygładzenie, nadal mocno reaguje na małą próbkę |
| 10 | 25.83% | 20.33% | słabsze wygładzenie, nadal mocno reaguje na małą próbkę |
| 15 | 21.47% | 19.00% | zostawiam tę wersję: umiarkowane wygładzenie |
| 25 | 17.59% | 17.22% | mocniejsze wygładzenie, wolniej ufa realnym strzałom |
| 40 | 15.24% | 15.67% | mocniejsze wygładzenie, wolniej ufa realnym strzałom |

Mój wniosek: `11%` wynika z porównania z aktualną skutecznością wszystkich strzałów w danych projektu (`11.74%`). `30%` zostawiam niżej niż aktualne `34.79%`, bo ma być ostrożnym punktem startowym. `15` wirtualnych strzałów ogranicza skok do 100% przy próbie 2/2, ale nie przykrywa całkowicie realnych danych.

Przyjęte `11%` dla wszystkich strzałów jest blisko danych projektu, a `30%` dla strzałów celnych jest celowo niżej od aktualnej próbki.

Dodatkowe sprawdzenie: drużyna z 2 golami z 2 strzałów nie dostaje 100% skuteczności.

- Bez wygładzania: `2 / 2 = 100%`.
- Z wygładzaniem wszystkich strzałów: `(2 + 15 × 0.11) / (2 + 15) = 21.47%`.

Metoda: xG jako myślenie o strzale przez prawdopodobieństwo gola + additive smoothing. Liczby 11%, 30% i 15 są ustawieniami dobranymi w tym projekcie.

## 6. Forma: 3 mecze, wagi 50% / 30% / 20% i różnica bramek dzielona przez 3

Sprawdzam, czy wagi formy sumują się do 100% i jak działa ograniczenie różnicy bramek.

Źródło danych dla formy w modelu:

```text
docs/data/calendar.json -> days[].matches[].home_goals / away_goals
docs/data/calendar.json -> days[].matches[].home_team_id / away_team_id
```

Wzór dla różnicy bramek:

```text
składnik_różnicy = ogranicz((gole_drużyny - gole_rywala) / 3, od -1 do 1)
```

- **Forma**: suma wag = 1.000 (OK); 50%, 30%, 20%.

| Różnica bramek | Składnik przed ograniczeniem | Składnik po ograniczeniu |
|---:|---:|---:|
| -5 | -1.67 | -1.00 |
| -3 | -1.00 | -1.00 |
| -2 | -0.67 | -0.67 |
| -1 | -0.33 | -0.33 |
| +0 | 0.00 | 0.00 |
| +1 | 0.33 | 0.33 |
| +2 | 0.67 | 0.67 |
| +3 | 1.00 | 1.00 |
| +5 | 1.67 | 1.00 |

Jak dobrałam wagi `50% / 30% / 20%`: porównałam kilka podejść do formy.

| Wariant | Wagi meczów od najnowszego | Co oznacza |
|---|---|---|
| równe | 33% / 33% / 33% | każdy z 3 meczów ma taki sam wpływ, mniej czułe na aktualny trend |
| wybrane | 50% / 30% / 20% | zostawiam tę wersję: najnowszy mecz jest najważniejszy, ale starsze nadal stabilizują ocenę |
| bardzo świeże | 70% / 20% / 10% | bardzo mocno premiuje ostatni mecz, większe ryzyko przereagowania |

Mój wniosek: `50/30/20` jest środkiem między równym traktowaniem trzech meczów a zbyt mocnym uzależnieniem formy od ostatniego wyniku.

Zwycięstwo trzema golami jest traktowane jako bardzo mocny sygnał, ale wyższe wyniki nie zwiększają formy bez końca.
Metoda: krótka średnia ważona. Liczby 3 oraz 50/30/20 są ustawieniami projektu.

## 7. Jakość rywala: mnożnik 0.4–2.5

Sprawdzam, czy limity działają jako zabezpieczenie, a nie jako główny mechanizm sterujący całą oceną.

Źródło danych:

```text
docs/data/calendar.json -> days[].prediction[].attack
docs/data/calendar.json -> days[].prediction[].defense
```

Wzory używane w modelu:

```text
mnożnik_obrony_rywala = defense_rywala / 50
mnożnik_ataku_rywala = 50 / attack_rywala
wynik mnożnika jest ograniczany do zakresu 0.4–2.5
```

- Limit minimalny: `0.4`.
- Limit maksymalny: `2.5`.
- W ostatnim dniu eksportu Attack mieści się od `31.92` do `74.57`.
- W ostatnim dniu eksportu Defense mieści się od `28.11` do `75.23`.

Jak dobrałam zakres `0.4–2.5`: porównałam limity na przykładowych surowych mnożnikach.

| Surowy mnożnik | Wąski limit 0.7–1.6 | Wybrany limit 0.4–2.5 | Szeroki limit 0.2–4.0 |
|---:|---:|---:|---:|
| 0.20 | 0.70 | 0.40 | 0.20 |
| 0.40 | 0.70 | 0.40 | 0.40 |
| 0.80 | 0.80 | 0.80 | 0.80 |
| 1.00 | 1.00 | 1.00 | 1.00 |
| 1.60 | 1.60 | 1.60 | 1.60 |
| 2.50 | 1.60 | 2.50 | 2.50 |
| 4.00 | 1.60 | 2.50 | 4.00 |

Mój wniosek: `0.4–2.5` jest kompromisem. Wąski limit zbyt mocno spłaszcza jakość rywala, a szeroki limit pozwalałby pojedynczym skrajnościom za mocno zmieniać ocenę.
Przy obecnych danych drużyny są daleko od wartości skrajnych 0 i 100, więc limity 0.4–2.5 pełnią głównie rolę bezpiecznika na nietypowe sytuacje.
Metoda: ważenie wyniku jakością przeciwnika. Konkretne limity są technicznym ustawieniem projektu.

## 8. Średnia bramek: awaryjne 1.3 gola na drużynę

Porównuję fallback 1.3 z realnymi średnimi zapisanymi w eksporcie.

Źródło danych:

```text
docs/data/calendar.json -> days[].base_rate
docs/data/calendar.json -> days[].matches[].home_goals / away_goals
```

Wzór logiczny:

```text
base_rate = suma_goli / liczba_występów_drużyn
liczba_występów_drużyn = liczba_meczów × 2
```

Przykłady dni z eksportu:

| Data | Gole w meczach tego dnia | Występy drużyn | Gole / występ drużyny | base_rate w eksporcie |
|---|---:|---:|---:|---:|
| 2026-06-11 | 2 | 2 | 1.000 | 1.000 |
| 2026-06-12 | 5 | 4 | 1.250 | 1.167 |
| 2026-07-06 | 6 | 4 | 1.500 | 1.452 |
| 2026-07-07 | 10 | 6 | 1.667 | 1.458 |
| 2026-07-08 | 0 | 0 |  | 1.458 |

Jak dobrałam fallback `1.3`: porównałam kilka możliwych wartości startowych z późniejszymi średnimi z eksportu.

| Kandydat fallbacku | Gole łącznie w meczu | Różnica względem średniej dni eksportu | Komentarz |
|---:|---:|---:|---|
| 1.00 | 2.00 | -0.458 | bardziej ostrożny, może zaniżać liczbę goli |
| 1.20 | 2.40 | -0.258 | bardziej ostrożny, może zaniżać liczbę goli |
| 1.30 | 2.60 | -0.158 | zostawiam tę wersję: ostrożnie poniżej średniej z eksportu |
| 1.50 | 3.00 | 0.042 | bardziej ofensywny, bliżej/wyżej aktualnej średniej |
| 1.70 | 3.40 | 0.242 | bardziej ofensywny, bliżej/wyżej aktualnej średniej |

`1.3` zostaje jako start niższy od aktualnej średniej z eksportu (`1.458`), czyli ostrożny fallback używany tylko wtedy, gdy nie ma jeszcze danych turniejowych.

- Pierwsza zapisana wartość `base_rate`: `1.000`.
- Ostatnia zapisana wartość `base_rate`: `1.458`.
- Minimum w eksporcie: `1.000`.
- Maksimum w eksporcie: `1.591`.
- Średnia z dni eksportu: `1.458`.

Fallback `1.3` jest ostrożnym punktem startowym. Gdy pojawiają się mecze, model używa realnej średniej turniejowej.
Metoda: średnia goli jako parametr bazowy modelu Poissona. Liczba 1.3 jest ustawieniem projektu.

## 9. Model Poissona i maksymalnie 10 goli

Sprawdzam, jak duży ogon rozkładu odcinam przy 10 golach.

Źródło danych dla lambdy:

```text
docs/data/calendar.json -> days[].base_rate
docs/data/calendar.json -> days[].prediction[].attack
docs/data/calendar.json -> days[].prediction[].defense
```

Wzór:

```text
lambda = base_rate × (attack / 50) × ((100 - defense_rywala) / 50)
```

Największa lambda znaleziona w eksporcie:

```text
data = 2026-06-14
team_id = 50
opponent_id = 37
base_rate = 1.550
attack = 67.26
defense_rywala = 28.27
lambda = 1.550 × (67.26 / 50) × ((100 - 28.27) / 50)
lambda = 2.991
```

Jak dobrałam limit `10`: porównałam, ile prawdopodobieństwa obcinam przy różnych limitach goli.

| Limit goli | Prawdopodobieństwo wyniku powyżej limitu przy największej lambdzie | Komentarz |
|---:|---:|---|
| 6 | 3.306824% | szybsze, ale odcina większy ogon |
| 8 | 0.373244% | szybsze, ale odcina większy ogon |
| 10 | 0.028530% | zostawiam tę wersję: ogon jest już pomijalny |
| 12 | 0.001567% | dokładniejsze minimalnie, ale mało zmienia wynik |

- Prawdopodobieństwo więcej niż 10 goli przy lambda `1.3`: `0.000014%`.
- Największa lambda znaleziona w eksporcie meczów: `2.991`.
- Prawdopodobieństwo więcej niż 10 goli przy tej lambdzie: `0.028530%`.

Odcięcie przy 10 golach pomija skrajnie mały ogon rozkładu, a znacząco upraszcza obliczenia.
Metoda: rozkład Poissona. Liczba 10 jest technicznym ustawieniem projektu.

## 10. Liczba symulacji: 10 000

Szacuję typowy błąd losowy proporcji przy różnych liczbach symulacji. Dla uproszczenia biorę najtrudniejszy przypadek p=50%, gdzie błąd jest największy.

Wzór:

```text
błąd_standardowy = sqrt(p × (1 - p) / liczba_symulacji)
dla najtrudniejszego przypadku przyjmujemy p = 0.5
```

| Liczba symulacji | Przybliżony błąd standardowy |
|---:|---:|
| 1 000 | 1.58% |
| 5 000 | 0.71% |
| 10 000 | 0.50% |
| 20 000 | 0.35% |

Jak dobrałam `10 000`: 1 000 symulacji jest szybkie, ale błąd losowy jest ponad trzy razy większy niż przy 10 000. 20 000 daje mniejszy błąd, ale kosztuje więcej czasu, a zysk dla dashboardu jest już niewielki.
Przy `10 000` symulacji błąd losowy dla pojedynczej proporcji jest już niewielki, a obliczenia nadal są praktyczne lokalnie.
Metoda: Monte Carlo. Liczba 10 000 jest ustawieniem projektu.

## Źródła metod

Poniższe źródła nie podają konkretnych parametrów tego projektu. Uzasadniają metody, na których projekt się opiera:

- z-score / standaryzacja: https://en.wikipedia.org/wiki/Standard_score
- expected goals, czyli traktowanie strzału jako prawdopodobieństwa gola: https://en.wikipedia.org/wiki/Expected_goals
- additive smoothing, czyli wygładzanie przez pseudoobserwacje: https://en.wikipedia.org/wiki/Additive_smoothing
- rozkład Poissona: https://en.wikipedia.org/wiki/Poisson_distribution
- metoda Monte Carlo: https://en.wikipedia.org/wiki/Monte_Carlo_method
- ranking FIFA jako punkt odniesienia dla siły reprezentacji: https://en.wikipedia.org/wiki/FIFA_Men%27s_World_Ranking

## Podsumowanie

Te sprawdzenia nie udowadniają, że model zna przyszłość. Pokazują coś prostszego: liczby są jawne, sprawdzalne i nie są oderwane od danych, które projekt już posiada.

Najmocniej lokalnymi danymi wspierane są parametry skuteczności strzałów oraz fallback średniej bramek. Pozostałe liczby są parametrami kalibracyjnymi: ich rolą jest stabilizacja modelu, ograniczanie skrajności i zachowanie czytelnej interpretacji wyników.
