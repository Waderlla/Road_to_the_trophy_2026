**Language:** English | [Polski](README_PL.md)

# About the project

**Live site:** https://waderlla.github.io/Road_to_the_trophy_2026/

**Road to the Trophy 2026** is an interactive analytics project showing how the chances of each national team winning the 2026 FIFA World Cup change throughout the tournament.

This isn't a classic results table. The site doesn't just show who won a given match. Its main goal is to answer the question:

> Which team has the best chance of becoming world champion on any given day of the tournament - and why?

The project combines match data, team statistics, the FIFA ranking, the tournament schedule, and computer simulations to show, day by day, how the balance of power shifts.

## What can you see on the site?

The site lets you follow the entire tournament day by day.

For any selected date, the dashboard shows:

- team ranking by chance of winning the title,
- the current forecast leader,
- teams with the biggest gains and drops in chances,
- results or scheduled matches for that day,
- the current stage of the tournament,
- the knockout bracket,
- the history of probability changes,
- detailed data for a selected team.

Clicking on a team opens its extended profile: team strength, key statistics, likely opponent, chances of reaching the next stages, head coach, captain, average squad age, and FIFA ranking position.

## Where does the data come from?

The data doesn't come from a single place. The project uses several sources, because each one supplies a different piece of information needed to build the forecast.

The first source is **API-Football** (`https://www.api-football.com/`). It supplies mainly matches, results, match statuses, and the basic schedule. This source is used in the scripts that import matches and match statistics. Data from the API includes goals, match status, and statistics such as shots, shots on target, possession, passes, fouls, and cards.

The second source is **FotMob**, but not as an automated API - as HTML pages saved locally. These files are saved manually from the browser and then processed by the project's scripts. FotMob is used in three places:

- saved individual match pages fill in or correct results, statuses, and statistics, especially when the API doesn't have complete data;
- a saved FotMob schedule page gives the official dates and times of future bracket slots, even before the teams in them are known;
- saved FotMob team pages supply the FIFA ranking, head coaches, and supporting squad information.

A third, supporting source is a saved **Soccer2026 / Bola 2026** page (`https://soccer2026.app/pl/schedule`). It's used to check the full schedule of all 104 matches and the structure of the knockout stage. In the project it's treated as a control source for the schedule and bracket: it helps confirm which knockout slots exist, in what order they're played, and what dates and times they have.

A separate category is **data calculated locally within the project**. This isn't data pulled from an external source - it's values computed from earlier information. This group includes:

- the group table,
- team standings within groups,
- teams advancing to the knockout stage,
- the current bracket,
- eliminated teams,
- daily team strength scores,
- championship probabilities from the simulations.

All data is stored in the project's local database. This makes it possible to reconstruct, for any day of the tournament, exactly what was known at that point: which matches had already been played, which statistics were known, who was still in the tournament, and what the forecast looked like for the rest of the World Cup.

## How are the chances calculated?

The project first evaluates each team's current strength. Only then, based on that strength, does it simulate the tournament's possible continuation.

Team strength isn't based solely on results. The result of a match alone can be misleading - a team can win off one lucky shot, or lose despite playing very well.

That's why the model first turns raw match statistics into six team ratings on a scale from 0 to 100:

- **attack** - goals, shots, and shots on target,
- **defense** - goals conceded, opponent shots, opponent shots on target, opponent xG, and clean sheets,
- **control** - possession, number of passes, and pass accuracy,
- **efficiency** - goals relative to shots and shots on target,
- **discipline** - fouls, yellow cards, and red cards,
- **form** - results of recent matches, weighted more heavily toward the most recent ones.

Each of these areas is calculated a bit differently.

### Attack

Attack isn't based on goal count alone. Goals matter, but they can be random. That's why the model also looks at whether a team regularly creates chances.

In the attack rating:

- goals account for **50%** of the score,
- total shots account for **25%**,
- shots on target account for **25%**.

If a team scores a lot of goals and regularly creates chances, its attack rating rises. If it won by chance while taking very few shots, the model doesn't boost its rating as much.

### Defense

Defense also isn't based solely on the number of goals conceded. A team might not concede a goal but still allow the opponent plenty of good chances.

In the defense rating:

- goals conceded account for **35%**,
- opponent xG accounts for **20%**,
- opponent shots on target account for **20%**,
- total opponent shots account for **15%**,
- clean sheets account for **10%**.

This lets the model distinguish a team that genuinely defends well from one that just got lucky in a single match.

### Control

Control describes whether a team can keep possession and manage the tempo of the match.

In the control rating:

- possession accounts for **40%**,
- pass accuracy accounts for **30%**,
- number of passes accounts for **30%**.

This part of the model rewards teams that don't just defend and counter-attack, but can sustain longer spells of play.

### Efficiency

Efficiency measures how well a team converts chances into goals.

The model looks at:

- goals relative to total shots,
- goals relative to shots on target.

Both parts carry **50%** weight each.

There's an important safeguard here though: efficiency is **smoothed**, meaning the model doesn't fully trust a small sample of data.

In simple terms: when a team has taken very few shots, its efficiency isn't calculated purely from those few actions. The model adds a number of "virtual" shots at a typical, average conversion rate for football.

In the project this works as follows:

- for efficiency from all shots, the model assumes a typical conversion rate of **11%**,
- for efficiency from shots on target, the model assumes a typical conversion rate of **30%**,
- **15 virtual shots** are added to both calculations.

So instead of calculating just:

```text
goals / shots
```

the model calculates:

```text
(goals + 15 x typical rate) / (shots + 15)
```

Example: if a team took 2 shots and scored 2 goals, the raw efficiency would be:

```text
2 / 2 = 100%
```

But after smoothing for all shots, the model calculates:

```text
(2 + 15 x 0.11) / (2 + 15)
= 3.65 / 17
= about 21.5%
```

That's still a very good efficiency rating, but no longer an absurd 100%. This means one unusual match doesn't automatically turn a team into the most efficient side in the tournament.

The more real shots a team takes, the less these "virtual" shots matter. Early in the tournament, the smoothing strongly stabilizes the rating; later, real data increasingly takes over.

In the end, both smoothed indicators - efficiency from all shots and efficiency from shots on target - are compared against the rest of the teams, rescaled to **0-100**, and combined equally.

### Discipline

Discipline carries a smaller weight, but still affects a team's rating.

The model takes into account:

- fouls,
- yellow cards,
- red cards.

A red card is treated more heavily than a yellow one. Discipline alone doesn't determine team strength, but it can slightly lower the rating of a team that plays very roughly and takes risks.

### Form

Form looks at a team's most recent matches.

The most recent match carries the most weight, older ones less. The model takes into account the result, goal difference, and the quality of the opponent.

The point is to notice that a team can be rising or fading during the tournament, while not overreacting to a single random result.

### How does the model compare teams?

Raw statistics have different scales. Goals, shots, possession, and cards can't be compared directly.

That's why every statistic is rescaled to a 0-100 scale relative to the rest of the teams in the tournament.

In practice:

- a score around **50** means an average level,
- a score above **50** means a result better than average,
- a score below **50** means a result worse than average.

The model doesn't use a simple "best = 100, worst = 0" approach, because that could artificially inflate small differences. Instead, it takes into account how far a given team deviates from the average.

### How do these ratings become a single team strength?

After calculating the six areas, the model combines them into a single value: **team strength**.

The weights are as follows:

```text
30% - attack
30% - defense
15% - efficiency
15% - control
 5% - form
 5% - discipline
```

Attack and defense matter most, since they most directly affect a match result. Efficiency and control are important, but supporting factors. Form and discipline carry less weight, so the model doesn't overreact to a single unusual match.

### Why is the FIFA ranking used at the start?

At the start of the tournament there are no World Cup match statistics yet. If the model knew nothing about the teams, every team would start with a similar strength, which wouldn't be realistic.

That's why, before the first matches, the model uses FIFA ranking points as a starting point.

This means stronger teams start a bit higher, and weaker ones a bit lower. The FIFA ranking isn't treated as absolute truth, though. It's only a starting estimate whose influence shrinks with every subsequent match.

You can think of it this way:

- before the first match, the model trusts the FIFA ranking more heavily,
- after a few matches, it increasingly trusts the real tournament results and statistics,
- the more World Cup data there is, the smaller the influence of the starting point.

This protects the model from two mistakes: pretending all teams are equal at the start, and overreacting to a single random result.

## Adopted model parameters

The project contains numbers that don't come directly from the API. These are **model parameters** - deliberately chosen settings. Each parameter has a defined role: it stabilizes calculations, limits extreme results, or tells the model how strongly to trust a given piece of information.

This is an important distinction:

- the API supplies data, e.g. goals, shots, cards, possession, FIFA ranking,
- the model decides how to convert that data into a team rating,
- parameters tell the model how sharply or gently it should react.

Detailed calculations and justification for each of these numbers, based on the project's real data, can be found in [`data/model_parameter_checks_EN.md`](data/model_parameter_checks_EN.md).

### The 0-100 scale and the neutral point of 50

Team ratings are shown on a **0-100** scale.

On this scale:

- **50** means an average level relative to other teams,
- a score above **50** means a result better than average,
- a score below **50** means a result worse than average.

This isn't a school grade or a task-completion percentage. It's a simplified comparative scale.

The method is based on statistical standardization - comparing a result to its mean and standard deviation. This result is called a **z-score**: [Standard score](https://en.wikipedia.org/wiki/Standard_score).

In the project, the z-score is then converted to a more readable 0-100 scale. The midpoint of the scale is set at 50, so it's easy to read whether a team is above or below average.

### Range of FIFA ranking influence: 35-72

The FIFA ranking is used as a starting point before the first matches.

The model doesn't let the FIFA ranking give a team an immediately extreme low or high rating, though. That's why the FIFA-ranking starting point is limited to a range:

```text
minimum: 35
maximum: 72
```

Why this range?

Because the FIFA ranking should help set a reasonable starting point, but it can't determine the whole tournament. If the best teams started near 100 and the weakest near 0, the model would trust the pre-tournament ranking far too much. The 35-72 range preserves a difference between stronger and weaker teams, while still leaving every team room to change its rating after real matches.

The use of the FIFA ranking itself is based on the official idea behind the ranking: comparing the strength of national teams based on match results. A description of the ranking and its current points system can be found here: [FIFA Men's World Ranking](https://en.wikipedia.org/wiki/FIFA_Men%27s_World_Ranking).

The numbers **35** and **72** are parameters of this project. They don't come from FIFA. They were chosen so that the ranking acts as a starting point, not a verdict.

### Width of FIFA ranking influence: 8 points per standard deviation

In the project, the FIFA ranking is first compared to the average ranking points of all teams. The model then checks how far a given team deviates from that average.

It's assumed that one standard deviation from the mean shifts the starting rating by about **8 points** on the 0-100 scale.

Why 8?

Because it's a moderate value. The FIFA ranking influences the start, but doesn't dominate the whole rating. A strong team starts higher, but not so high that a weaker team couldn't catch up after good matches.

The method is based on the z-score - measuring distance from the mean in standard deviations: [Standard score](https://en.wikipedia.org/wiki/Standard_score).

The number **8** is a project parameter. It represents how strongly the FIFA ranking is translated onto the model's scale.

### Pull toward the starting point: 3 virtual matches

Early in the tournament there's little real data. After a single match, the model could change a team's rating too abruptly.

That's why the rating after the first matches is pulled toward the FIFA-ranking starting point. In the code, this is handled by a parameter:

```text
3 virtual matches
```

You can think of it this way: before a team has played enough matches, the model still keeps its starting rating in memory.

Why 3?

Because the group stage consists of three matches. That's a natural unit for the tournament: after one match the model should be cautious, after two still partly cautious, and after three it already has a reasonable amount of World Cup data.

Methodologically, this is similar to smoothing via pseudo-observations - adding "virtual" observations to a small data sample: [Additive smoothing](https://en.wikipedia.org/wiki/Additive_smoothing).

The number **3** is a project parameter. Its role is to limit an overreaction of the model to a single match.

### Shot efficiency: 11% and 30%

Efficiency is smoothed so that a small number of shots doesn't produce absurd results.

Two reference points were adopted:

```text
11% - baseline efficiency for all shots
30% - baseline efficiency for shots on target
```

These numbers aren't pulled from the API. They're model parameters.

Why these values?

Because they're a conservative starting point:

- **11%** roughly means 1 goal per 9 shots,
- **30%** roughly means 1 goal per 3 shots on target.

The point is for the model to have a reasonable reference point before it gathers more tournament data.

The idea is based on xG analytics, where every shot can be treated as a probability of scoring: [Expected goals](https://en.wikipedia.org/wiki/Expected_goals).

The numbers **11%** and **30%** are project parameters. If the project is developed further, they could be calibrated on a large historical match dataset.

### Shot efficiency: 15 virtual shots

The model adds **15 virtual shots** to the efficiency calculation.

This means a team with very few shots isn't rated solely on the basis of a handful of actions.

Why 15?

Because it's a moderate smoothing strength. That number is enough that one match doesn't flip the efficiency rating upside down, but not so large that a team's real shots stop mattering.

The method is based on additive smoothing - adding pseudo-observations to a small data sample: [Additive smoothing](https://en.wikipedia.org/wiki/Additive_smoothing).

The number **15** is a project parameter. It determines how strongly the model stabilizes efficiency early on.

### Form: 3 most recent matches and weights 50% / 30% / 20%

A team's form is calculated from up to **3 most recent matches**.

Their weights are:

```text
50% - most recent match
30% - previous match
20% - third most recent match
```

Why this way?

Because form is meant to show the current trend, not a team's entire history. The most recent match says the most about current condition, but older matches still help distinguish a genuine trend from a one-off result.

The number **3** also fits the tournament's structure, since the group stage has three matches. This lets the model assess a team's short, tournament-specific form instead of mixing it with very old history.

This is a project parameter. It doesn't come from an external table. It's a methodological decision: form is meant to be short, current, and cautious.

### Opponent quality: multiplier limited to a range of 0.4 to 2.5

The model takes into account who a team played against.

A goal scored against a strong defense is worth more than a goal scored against a very weak defense. Likewise, a goal conceded against a weak attack is more damaging than a goal conceded against a very strong attack.

To keep this effect from being exaggerated, the opponent-quality multiplier has limits:

```text
minimum: 0.4
maximum: 2.5
```

Why this way?

Because without limits, one extreme result or one very low opponent rating could artificially distort the whole model. The limits allow opponent quality to be taken into account while guarding against absurd outcomes.

The numbers **0.4** and **2.5** are project parameters. Their role is technical: they protect the model from extreme multipliers.

### Goal difference in form: divided by 3

When assessing form, the model takes into account not just win/draw/loss, but also goal difference.

Goal difference is divided by **3** and clamped to a range from -1 to 1.

Why 3?

Because a win by three goals is treated as a very strong signal, but winning by five or six goals shouldn't keep boosting form indefinitely. The model treats a difference of about three goals as enough to count a match as a clear dominant performance.

The number **3** is a project parameter. It limits the impact of very high-scoring results.

### Goal model: the Poisson distribution

The Poisson distribution is used to forecast the number of goals in a match.

It's a popular probability distribution for the number of events in a given time period, e.g. the number of goals in a match. Method source: [Poisson distribution](https://en.wikipedia.org/wiki/Poisson_distribution).

The model first estimates each team's expected number of goals, then checks the probabilities of various results, e.g. 0:0, 1:0, 1:1, 2:1.

### Maximum of 10 goals in the match model

When calculating the results of a single match, the model checks scores from 0 to **10** goals for each team.

Why 10?

Because results above 10 goals for one team are extremely rare in football. Accounting for them would barely change the probabilities, while increasing the amount of computation.

The number **10** is a technical parameter of the project. It represents a practical cutoff of a very low-probability tail of the distribution.

### Average goals: fallback value of 1.3

The model uses the tournament's average number of goals as a reference point for match forecasts.

If there isn't yet enough tournament data at a given moment, a fallback value is used:

```text
1.3 goals per team
```

Why 1.3?

Because it's a cautious starting point for football: about 2.6 goals in total per match. It isn't data from the API or from FIFA. It's a project parameter used only when a real tournament average isn't available yet.

Once data from played matches becomes available, the model uses the actual tournament average.

### Number of simulations: 10,000

The entire tournament is simulated **10,000 times**.

Why 10,000?

Because the Monte Carlo method works by repeatedly sampling possible scenarios. The more simulations, the more stable the result, but also the longer the computation takes.

10,000 is a practical compromise:

- the result is far more stable than with a few hundred simulations,
- the computation can still be run locally,
- the percentages are readable enough for the site's users.

The method is based on Monte Carlo simulation - estimating probabilities through many random repetitions: [Monte Carlo method](https://en.wikipedia.org/wiki/Monte_Carlo_method).

The number **10,000** is a project parameter. It determines the accuracy and computational cost.

## Why do the chances change every day?

Every match changes the situation.

A win can increase a team's chances, but not always in an obvious way. What also matters:

- who the team played,
- what the match result was,
- what the statistics looked like,
- whether the team advanced,
- who it might face in the next round,
- how the bracket changed.

So sometimes a team can win a match, but its title chances only rise slightly. Other times, the result of a different match can open up an easier path and improve the situation of a team that didn't even play that day.

## What is the tournament simulation?

After calculating team strengths, the project simulates the tournament's possible continuation.

The computer plays out the rest of the tournament thousands of times. In each simulation, the results of future matches, the advancements, and the bracket can all differ.

If a given team wins the tournament in many of these simulations, its title chance is high. If it rarely wins, its chance is low.

Example:

> If a team wins 1,900 out of 10,000 simulations, the model assigns it about a 19% chance of winning the title.

This means the project doesn't try to point to a single certain future. Instead, it shows which scenarios are most likely based on the available data.

## How are individual matches forecast?

A simple goal-based model is used to estimate the results of individual matches.

The model compares:

- one team's attacking strength,
- the other team's defensive quality,
- the tournament's average number of goals.

Based on this, it estimates how many goals each side might score, then calculates the probability of a win, draw, or loss.

That's why, for scheduled matches, you can see a forecast like:

```text
France 63% / draw 20% / Colombia 17%
```

This isn't a certainty. It's an estimated chance of the result after 90 minutes, based on the current rating of both teams.

## What do the percentages mean?

The percentages on the site represent probability in the model.

If a team has:

```text
19% chance of winning the title
```

that means it won the entire tournament in about 19% of the computer simulations.

If, for a match, we see:

```text
48% / draw 24% / 28%
```

that represents the estimated chance of the result after 90 minutes:

- 48% - win for the first team,
- 24% - draw,
- 28% - win for the second team.

## Why doesn't the model always match intuition?

The model looks more broadly than just at the last result.

It takes into account:

- team strength,
- opponent quality,
- statistics so far,
- the possible path through the bracket,
- likely opponents in upcoming rounds.

So a lower-ranked team can sometimes have a favorable path and higher chances than its "strength on paper" alone would suggest. Conversely, a very strong team can face a harder bracket and, as a result, a lower probability of ultimately winning.

## What does the timeline show?

The timeline lets you go back to any day of the tournament.

For past days, the site shows the state of the model as it was on that day - as if we didn't yet know the future results.

For future days, the site shows the latest available forecast along with the schedule of upcoming matches. The project doesn't pretend to know future results.

## Is this a betting model?

No.

The project is analytical and educational in nature. Its goal is to show how sports data, a simple statistical model, and a tournament simulation can be combined into an interactive dashboard.

The model doesn't account for every factor that might matter in a professional betting model, such as:

- injuries,
- predicted lineups,
- player fatigue,
- a specific opponent's style,
- tactical decisions,
- betting-market information.

That's why the percentages should be treated as an analytical forecast, not a guarantee of the outcome.

## Key limitations

Every model is a simplification of reality.

In this project, the most important limitations are:

- data comes from several different sources,
- some information requires manual import,
- extra time and penalty shootouts are simplified,
- the FIFA ranking is only a starting point, not a full description of team strength,
- the model doesn't know about injuries or match lineups.

Despite these limitations, the project shows something a regular results table doesn't: how every subsequent match affects the chances of the entire tournament.

## Why was this project created?

The project was created as a combination of data analysis, statistical modeling, and sports visualization.

I wanted to show that football data can be presented not just as results and tables, but as a dynamic story of changing chances.

During the tournament, every team has its own road to the trophy. This site shows how that road changes, day by day.
