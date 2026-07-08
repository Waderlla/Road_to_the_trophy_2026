# Notes on choosing the model's parameters

This is not a scientific validation or an attempt to prove that the model predicts matches better than the betting market.
It's a working check of whether the numbers adopted in the project make sense against the data already in the site's export.

- Input data: `docs\data\calendar.json` and `docs\data\teams.json`.
- Export range: from `2026-06-11` to `2026-07-08`.
- Number of teams: `48`.
- Number of unique scored matches in the export: `96`.
- Matches with a result and any statistics: `96`.
- Matches with a result and statistics for both teams: `96`.

## Where does the check data come from?

I don't pull anything from the internet here and I don't connect to the database. I only work from files the site has already generated.

Key fields:

- `docs/data/calendar.json -> days[].prediction[]`: daily team ratings, chances, and 0-100 indices.
- `docs/data/calendar.json -> days[].matches[]`: matches, results, statuses, and match statistics.
- `docs/data/calendar.json -> days[].matches[].home_stats / away_stats`: shots, shots on target, possession, passes, cards, etc.
- `docs/data/calendar.json -> days[].base_rate`: average goals per team used in the goal model.
- `docs/data/teams.json -> fifa_rank_points`: FIFA ranking points used for the starting point.

If a match has no statistics in `home_stats` or `away_stats`, I skip it when checking shot efficiency. I don't want to mix real results with empty statistics.

## 1. Component weights

First I check a simple thing: whether the weights in each group sum to 100%. If not, one part of the rating could accidentally be overweighted.

General formula:

```text
rating = component_1 x weight_1 + component_2 x weight_2 + ...
```

These numbers don't come from the JSON. They're settings recorded in the model's code. I'm only checking that they add up to a full 100%.

- **Attack**: sum of weights = 1.000 (OK); goals: 50%, shots_total: 25%, shots_on_goal: 25%.
- **Defense**: sum of weights = 1.000 (OK); goals_against: 35%, opp_xg: 20%, opp_shots_on_goal: 20%, opp_shots_total: 15%, clean_sheets: 10%.
- **Control**: sum of weights = 1.000 (OK); possession: 40%, pass_accuracy: 30%, passes_total: 30%.
- **Efficiency**: sum of weights = 1.000 (OK); goals_per_shot: 50%, goals_per_shot_on_target: 50%.
- **Discipline**: sum of weights = 1.000 (OK); fouls: 50%, cards: 50%.
- **Team strength**: sum of weights = 1.000 (OK); attack: 30%, defense: 30%, efficiency: 15%, control: 15%, form: 5%, discipline: 5%.

Method: weighted average. The weight proportions themselves are my design decision, not a value pulled from the API.

## 2. The 0-100 scale and the neutral point of 50

Here I check whether the exported indices actually stay within the 0-100 scale, and whether the midpoint of the scale falls close to a neutral 50.

Data source:

```text
docs/data/calendar.json -> days[].prediction[].strength
docs/data/calendar.json -> days[].prediction[].attack
docs/data/calendar.json -> days[].prediction[].defense
etc.
```

How it's calculated in this note:

```text
minimum = the smallest strength value that day
maximum = the largest strength value that day
average = sum of strength across all teams / number of teams
```

- First day (`2026-06-11`): team strength from `36.31` to `63.90`, average `50.02`.
- Latest export day (`2026-07-08`): team strength from `32.66` to `68.98`, average `50.24`.

Result: the midpoint stays around 50, so 50 works as a neutral point rather than an inflated starting rating.
Method: z-score / standard score.

## 3. FIFA ranking as a prior: range 35-72 and width 8

I recompute FIFA ranking points using the same formula the model uses.

Data source:

```text
docs/data/teams.json -> fifa_rank_points
```

Formula:

```text
mean = mean FIFA points across all teams
stdev = standard deviation of FIFA points
z = (team_points - mean) / stdev
raw_prior = 50 + z x 8
final_prior = clamp(raw_prior to the range 35-72)
```

- Mean FIFA points in `teams.json`: `1580.67`.
- Standard deviation of FIFA points in `teams.json`: `155.62`.

- Computed FIFA prior: minimum `35.00`, maximum `65.23`, mean `50.01`.
- Number of teams at the lower limit `35`: `1`.
- Number of teams at the upper limit `72`: `0`.

Calculation examples:

| Team | FIFA points | z-score | raw prior | prior after clamping |
|---|---:|---:|---:|---:|
| Argentyna | 1877 | 1.90 | 65.23 | 65.23 |
| Hiszpania | 1875 | 1.89 | 65.13 | 65.13 |
| Australia | 1579 | -0.01 | 49.91 | 49.91 |
| Haiti | 1293 | -1.85 | 35.21 | 35.21 |
| Nowa Zelandia | 1276 | -1.96 | 34.34 | 35.00 |

How I chose the number `8`: I compared several possible widths for the FIFA ranking's influence.

| Multiplier value | Lowest prior without a limit | Highest prior without a limit | Spread | Comment |
|---:|---:|---:|---:|---|
| 3 | 44.13 | 55.71 | 11.59 | the ranking has little influence |
| 5 | 40.21 | 59.52 | 19.31 | the ranking has little influence |
| 8 | 34.34 | 65.23 | 30.90 | keeping this version: the influence is visible but doesn't dominate the start |
| 12 | 26.51 | 72.85 | 46.34 | the ranking starts to strongly dominate the start |
| 15 | 20.63 | 78.56 | 57.93 | the ranking starts to strongly dominate the start |

How I chose the range `35-72`: I checked several possible limits.

| Range | Minimum after clamping | Maximum after clamping | Mean | Teams clamped from below | Teams clamped from above | Comment |
|---|---:|---:|---:|---:|---:|---|
| 30-70 | 34.34 | 65.23 | 50.00 | 0 | 0 | no effect on the current data; would allow a lower start for weaker teams in the future |
| 35-70 | 35.00 | 65.23 | 50.01 | 1 | 0 | similar on current data, but with a lower safety ceiling |
| 35-72 | 35.00 | 65.23 | 50.01 | 1 | 0 | keeping this version: cautious floor and a spare ceiling |
| 35-73 | 35.00 | 65.23 | 50.01 | 1 | 0 | nearly identical; a marginally looser ceiling |
| 40-70 | 40.00 | 65.23 | 50.37 | 5 | 0 | flattens weaker teams more strongly |

My conclusion: `8` gives a noticeable gap between favorites and underdogs, but doesn't push teams up near 80-90 before the first match. I treat the `35-72` range as a safeguard: the lower limit protects against writing off weaker teams too harshly, and the upper limit reserves high ratings for situations already confirmed by tournament results.

In practice the FIFA ranking differentiates teams at the start, but doesn't stretch them out to the extreme values of 0 and 100.
Method: FIFA ranking as starting information + z-score. The numbers 35, 72, and 8 are settings chosen after checking several variants.

## 4. Pull toward the starting point: 3 virtual matches

Here I check how quickly real data starts to dominate over the starting point.

Formula:

```text
real_data_weight = matches_played / (matches_played + 3)
starting_point_weight = 1 - real_data_weight
final_rating = data_rating x real_data_weight + prior x starting_point_weight
```

| Matches played | Real-data weight | Starting-point weight |
|---:|---:|---:|
| 0 | 0.0% | 100.0% |
| 1 | 25.0% | 75.0% |
| 2 | 40.0% | 60.0% |
| 3 | 50.0% | 50.0% |
| 4 | 57.1% | 42.9% |
| 5 | 62.5% | 37.5% |

How I chose the number `3`: I compared several possible strengths of pull toward the starting point.

| Virtual matches | Real-data weight after 1 match | after 2 matches | after 3 matches | Comment |
|---:|---:|---:|---:|---|
| 1 | 50.0% | 66.7% | 75.0% | reacts faster, higher risk of overreacting |
| 2 | 33.3% | 50.0% | 60.0% | reacts faster, higher risk of overreacting |
| 3 | 25.0% | 40.0% | 50.0% | keeping this version: after the group stage, real data already carries 50% |
| 5 | 16.7% | 28.6% | 37.5% | more conservative, reacts more slowly to the tournament |
| 8 | 11.1% | 20.0% | 27.3% | more conservative, reacts more slowly to the tournament |

My conclusion: `3` fits the World Cup's structure, since the group stage has three matches. After three matches, real data and the starting point each carry 50% weight, so the model doesn't ignore the ranking after a single match, but also doesn't cling to it for too long.

After one match the model is still cautious; after three matches real data and the starting point each carry 50%, and afterward the influence of tournament data keeps growing.
Method: smoothing / pseudo-observations. The number 3 is chosen to match the three matches of the group stage.

## 5. Efficiency: 11%, 30%, and 15 virtual shots

Here I compare the adopted values against the match data already in the site's export.

Data source:

```text
docs/data/calendar.json -> days[].matches[].home_goals / away_goals
docs/data/calendar.json -> days[].matches[].home_stats.shots_total / away_stats.shots_total
docs/data/calendar.json -> days[].matches[].home_stats.shots_on_goal / away_stats.shots_on_goal
```

I only take matches with a result and non-empty team statistics.

Formulas:

```text
efficiency from all shots = total_goals / total_shots
efficiency from shots on target = total_goals / total_shots_on_target
```

- Team-stat rows with shot data: `192`.
- Goals: `280`.
- Total shots: `2352`.
- Shots on target: `797`.
- Real goals / all shots in the export: `11.90%`.
- Real goals / shots on target in the export: `35.13%`.

Aggregate calculation:

```text
280 / 2352 = 11.90%
280 / 797 = 35.13%
```

Example data rows used in the calculation:

| Kickoff | Team ID | Goals | Shots | Shots on target | Goals/shots | Goals/shots on target |
|---|---:|---:|---:|---:|---:|---:|
| 2026-06-11T21:00:00+02:00 | 40 | 2 | 16 | 4 | 12.50% | 50.00% |
| 2026-06-11T21:00:00+02:00 | 42 | 0 | 3 | 2 | 0.00% | 0.00% |
| 2026-06-12T04:00:00+02:00 | 91 | 2 | 15 | 6 | 13.33% | 33.33% |

How I chose the values `11%` and `30%`: I compared several starting points against the real efficiency in the project's data.

| Candidate for all shots | Difference from project data | Candidate for shots on target | Difference from project data | Comment |
|---:|---:|---:|---:|---|
| 8.00% | -3.90% | 25.00% | -10.13% | more pessimistic |
| 10.00% | -1.90% | 30.00% | -5.13% | more pessimistic |
| 11.00% | -0.90% | 30.00% | -5.13% | keeping this version: close to the data, but cautious for shots on target |
| 11.90% | 0.00% | 35.13% | 0.00% | an exact match to the current sample, less conservative |

How I chose the number `15`: I compared the strength of smoothing on two simple examples.

| Virtual shots | 2 goals / 2 shots after smoothing | 5 goals / 20 shots after smoothing | Comment |
|---:|---:|---:|---|
| 5 | 36.43% | 22.20% | weaker smoothing, still reacts strongly to a small sample |
| 10 | 25.83% | 20.33% | weaker smoothing, still reacts strongly to a small sample |
| 15 | 21.47% | 19.00% | keeping this version: moderate smoothing |
| 25 | 17.59% | 17.22% | stronger smoothing, trusts real shots more slowly |
| 40 | 15.24% | 15.67% | stronger smoothing, trusts real shots more slowly |

My conclusion: `11%` comes from comparing it against the current efficiency of all shots in the project data (`11.74%`). I keep `30%` below the current `34.79%`, since it's meant to be a cautious starting point. `15` virtual shots limits the jump to 100% on a 2/2 sample, without completely masking the real data.

The adopted `11%` for all shots is close to the project's data, while `30%` for shots on target is deliberately below the current sample.

Additional check: a team with 2 goals from 2 shots doesn't get 100% efficiency.

- Without smoothing: `2 / 2 = 100%`.
- With smoothing for all shots: `(2 + 15 x 0.11) / (2 + 15) = 21.47%`.

Method: xG as thinking about a shot in terms of scoring probability + additive smoothing. The numbers 11%, 30%, and 15 are settings chosen for this project.

## 6. Form: 3 matches, weights 50% / 30% / 20%, and goal difference divided by 3

I check whether the form weights sum to 100% and how the goal-difference clamp behaves.

Data source for form in the model:

```text
docs/data/calendar.json -> days[].matches[].home_goals / away_goals
docs/data/calendar.json -> days[].matches[].home_team_id / away_team_id
```

Formula for goal difference:

```text
difference_component = clamp((team_goals - opponent_goals) / 3, from -1 to 1)
```

- **Form**: sum of weights = 1.000 (OK); 50%, 30%, 20%.

| Goal difference | Component before clamping | Component after clamping |
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

How I chose the weights `50% / 30% / 20%`: I compared several approaches to form.

| Variant | Match weights from most recent | What it means |
|---|---|---|
| równe | 33% / 33% / 33% | each of the 3 matches has the same influence, less sensitive to the current trend |
| wybrane | 50% / 30% / 20% | keeping this version: the most recent match matters most, but older ones still stabilize the rating |
| bardzo świeże | 70% / 20% / 10% | very strongly rewards the last match, higher risk of overreacting |

My conclusion: `50/30/20` is a middle ground between treating all three matches equally and making form too dependent on the last result.

A win by three goals is treated as a very strong signal, but higher scores don't keep boosting form indefinitely.
Method: short weighted average. The numbers 3 and 50/30/20 are project settings.

## 7. Opponent quality: multiplier 0.4-2.5

I check whether the limits act as a safeguard rather than the main mechanism driving the whole rating.

Data source:

```text
docs/data/calendar.json -> days[].prediction[].attack
docs/data/calendar.json -> days[].prediction[].defense
```

Formulas used in the model:

```text
opponent_defense_multiplier = opponent_defense / 50
opponent_attack_multiplier = 50 / opponent_attack
the multiplier result is clamped to the range 0.4-2.5
```

- Minimum limit: `0.4`.
- Maximum limit: `2.5`.
- On the latest export day, Attack ranges from `31.92` to `74.57`.
- On the latest export day, Defense ranges from `28.11` to `75.23`.

How I chose the range `0.4-2.5`: I compared the limits against sample raw multipliers.

| Raw multiplier | Narrow limit 0.7-1.6 | Chosen limit 0.4-2.5 | Wide limit 0.2-4.0 |
|---:|---:|---:|---:|
| 0.20 | 0.70 | 0.40 | 0.20 |
| 0.40 | 0.70 | 0.40 | 0.40 |
| 0.80 | 0.80 | 0.80 | 0.80 |
| 1.00 | 1.00 | 1.00 | 1.00 |
| 1.60 | 1.60 | 1.60 | 1.60 |
| 2.50 | 1.60 | 2.50 | 2.50 |
| 4.00 | 1.60 | 2.50 | 4.00 |

My conclusion: `0.4-2.5` is a compromise. A narrow limit flattens opponent quality too much, while a wide limit would let single extreme cases distort the rating too strongly.
With the current data, teams are far from the extreme values of 0 and 100, so the 0.4-2.5 limits mainly act as a safeguard for unusual situations.
Method: weighting the result by opponent quality. The specific limits are a technical setting of the project.

## 8. Average goals: fallback of 1.3 goals per team

I compare the 1.3 fallback against the real averages recorded in the export.

Data source:

```text
docs/data/calendar.json -> days[].base_rate
docs/data/calendar.json -> days[].matches[].home_goals / away_goals
```

Logical formula:

```text
base_rate = total_goals / number_of_team_appearances
number_of_team_appearances = number_of_matches x 2
```

Example days from the export:

| Date | Goals in that day's matches | Team appearances | Goals / team appearance | base_rate in the export |
|---|---:|---:|---:|---:|
| 2026-06-11 | 2 | 2 | 1.000 | 1.000 |
| 2026-06-12 | 5 | 4 | 1.250 | 1.167 |
| 2026-07-06 | 6 | 4 | 1.500 | 1.452 |
| 2026-07-07 | 10 | 6 | 1.667 | 1.458 |
| 2026-07-08 | 0 | 0 |  | 1.458 |

How I chose the fallback `1.3`: I compared several possible starting values against later averages from the export.

| Fallback candidate | Total goals per match | Difference from the export-day average | Comment |
|---:|---:|---:|---|
| 1.00 | 2.00 | -0.458 | more cautious, may understate the number of goals |
| 1.20 | 2.40 | -0.258 | more cautious, may understate the number of goals |
| 1.30 | 2.60 | -0.158 | keeping this version: cautiously below the export average |
| 1.50 | 3.00 | 0.042 | more attacking, closer to/above the current average |
| 1.70 | 3.40 | 0.242 | more attacking, closer to/above the current average |

`1.3` stays as a starting point below the current export average (`1.458`) - a cautious fallback used only when there's no real tournament average yet.

- First recorded `base_rate` value: `1.000`.
- Latest recorded `base_rate` value: `1.458`.
- Minimum in the export: `1.000`.
- Maximum in the export: `1.591`.
- Mean across export days: `1.458`.

The `1.3` fallback is a cautious starting point. Once matches are played, the model uses the real tournament average.
Method: average goals as the base parameter of the Poisson model. The number 1.3 is a project setting.

## 9. The Poisson model and a maximum of 10 goals

I check how much of the distribution's tail gets cut off at 10 goals.

Data source for lambda:

```text
docs/data/calendar.json -> days[].base_rate
docs/data/calendar.json -> days[].prediction[].attack
docs/data/calendar.json -> days[].prediction[].defense
```

Formula:

```text
lambda = base_rate x (attack / 50) x ((100 - opponent_defense) / 50)
```

The largest lambda found in the export:

```text
date = 2026-06-14
team_id = 50
opponent_id = 37
base_rate = 1.550
attack = 67.26
opponent_defense = 28.27
lambda = 1.550 x (67.26 / 50) x ((100 - 28.27) / 50)
lambda = 2.991
```

How I chose the limit `10`: I compared how much probability gets cut off at different goal limits.

| Goal limit | Probability of a result above the limit at the largest lambda | Comment |
|---:|---:|---|
| 6 | 3.306824% | faster, but cuts off a bigger tail |
| 8 | 0.373244% | faster, but cuts off a bigger tail |
| 10 | 0.028530% | keeping this version: the tail is already negligible |
| 12 | 0.001567% | marginally more precise, barely changes the result |

- Probability of more than 10 goals at lambda `1.3`: `0.000014%`.
- Largest lambda found in the match export: `2.991`.
- Probability of more than 10 goals at that lambda: `0.028530%`.

Cutting off at 10 goals skips an extremely small tail of the distribution, while significantly simplifying the calculations.
Method: Poisson distribution. The number 10 is a technical setting of the project.

## 10. Number of simulations: 10,000

I estimate the typical random error of a proportion at different numbers of simulations. For simplicity I take the hardest case, p=50%, where the error is largest.

Formula:

```text
standard_error = sqrt(p x (1 - p) / number_of_simulations)
for the hardest case we take p = 0.5
```

| Number of simulations | Approximate standard error |
|---:|---:|
| 1 000 | 1.58% |
| 5 000 | 0.71% |
| 10 000 | 0.50% |
| 20 000 | 0.35% |

How I chose `10,000`: 1,000 simulations is fast, but the random error is more than three times larger than at 10,000. 20,000 gives a smaller error, but costs more time, and the benefit for the dashboard is already small.
At `10,000` simulations, the random error for a single proportion is already small, and the computation is still practical to run locally.
Method: Monte Carlo. The number 10,000 is a project setting.

## Method sources

The sources below don't state the specific parameters of this project. They justify the methods the project is built on:

- z-score / standardization: https://en.wikipedia.org/wiki/Standard_score
- expected goals, i.e. treating a shot as a scoring probability: https://en.wikipedia.org/wiki/Expected_goals
- additive smoothing, i.e. smoothing via pseudo-observations: https://en.wikipedia.org/wiki/Additive_smoothing
- the Poisson distribution: https://en.wikipedia.org/wiki/Poisson_distribution
- the Monte Carlo method: https://en.wikipedia.org/wiki/Monte_Carlo_method
- the FIFA ranking as a reference point for national-team strength: https://en.wikipedia.org/wiki/FIFA_Men%27s_World_Ranking

## Summary

These checks don't prove that the model knows the future. They show something simpler: the numbers are explicit, verifiable, and not disconnected from the data the project already has.

The parameters most strongly supported by local data are shot efficiency and the average-goals fallback. The remaining numbers are calibration parameters: their role is to stabilize the model, limit extremes, and keep the results interpretable.
