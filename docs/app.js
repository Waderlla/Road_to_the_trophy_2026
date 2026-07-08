const TOURNAMENT_START = "2026-06-11";
const TOURNAMENT_END = "2026-07-19";

let teams = {};
let daysByDate = {};
let allDates = [];
let latestDate = null;
let selectedDate = null;
let historyChart = null;
let modalHistoryChart = null;
let highlightedTeamId = null;

if (window.parent !== window) {
  document.documentElement.classList.add("is-embedded");
}

// --- Model Poissona (port z scripts/poisson_model.py) - liczony po stronie
// przegladarki, zeby moc prognozowac dowolna pare druzyn "na zywo" (np.
// mozliwych rywali z rozkladu prawdopodobienstwa), bez wstepnego liczenia
// wszystkich mozliwych par po stronie serwera. ---
const MAX_GOALS = 10;

function poissonPmf(k, lam) {
  let fact = 1;
  for (let i = 2; i <= k; i++) fact *= i;
  return Math.exp(-lam) * Math.pow(lam, k) / fact;
}

function expectedGoals(attack, oppDefense, baseRate) {
  const attackFactor = attack / 50;
  const defenseFactor = (100 - oppDefense) / 50;
  return Math.max(0.05, baseRate * attackFactor * defenseFactor);
}

function matchResultProbabilities(attackA, defenseA, attackB, defenseB, baseRate) {
  const lamA = expectedGoals(attackA, defenseB, baseRate);
  const lamB = expectedGoals(attackB, defenseA, baseRate);
  let winA = 0, draw = 0, winB = 0;
  for (let i = 0; i <= MAX_GOALS; i++) {
    const pI = poissonPmf(i, lamA);
    for (let j = 0; j <= MAX_GOALS; j++) {
      const p = pI * poissonPmf(j, lamB);
      if (i > j) winA += p;
      else if (i === j) draw += p;
      else winB += p;
    }
  }
  const total = winA + draw + winB;
  return { winA: winA / total, draw: draw / total, winB: winB / total };
}

function mostLikelyScorelines(attackA, defenseA, attackB, defenseB, baseRate, topN) {
  const lamA = expectedGoals(attackA, defenseB, baseRate);
  const lamB = expectedGoals(attackB, defenseA, baseRate);
  const scores = [];
  let total = 0;
  for (let i = 0; i <= MAX_GOALS; i++) {
    const pI = poissonPmf(i, lamA);
    for (let j = 0; j <= MAX_GOALS; j++) {
      const p = pI * poissonPmf(j, lamB);
      scores.push([i, j, p]);
      total += p;
    }
  }
  scores.forEach((s) => { s[2] /= total; });
  scores.sort((a, b) => b[2] - a[2]);
  return scores.slice(0, topN || 3);
}

const STAGE_ORDER = ["p_r32", "p_r16", "p_qf", "p_sf", "p_final"];
const STAGE_KEY_FOR = { p_r32: "R32", p_r16: "R16", p_qf: "QF", p_sf: "SF", p_final: "final" };

function nextStageForTeam(entry) {
  for (const key of STAGE_ORDER) {
    const val = entry[key];
    if (val === undefined || val === null) continue;
    if (val > 0.001 && val < 0.999) return { stage: STAGE_KEY_FOR[key], reachProbability: val };
  }
  return null;
}

function nextMatchInfo(dayData, entry) {
  const stageInfo = nextStageForTeam(entry);
  if (!stageInfo) return null;
  const { stage, reachProbability } = stageInfo;
  const opponents = (entry.opponents && entry.opponents[stage]) || [];
  if (opponents.length === 0) return null;

  const top = [...opponents].sort((a, b) => b.probability - a.probability)[0];
  const oppEntry = dayData.prediction.find((p) => p.team_id === top.opponent_id);
  if (!oppEntry) return null;

  const baseRate = dayData.base_rate || 1.3;
  const probs = matchResultProbabilities(entry.attack, entry.defense, oppEntry.attack, oppEntry.defense, baseRate);
  const scorelines = mostLikelyScorelines(entry.attack, entry.defense, oppEntry.attack, oppEntry.defense, baseRate, 3);
  return { stage, reachProbability, opponentId: top.opponent_id, opponentChance: top.probability, probs, scorelines };
}

async function loadData() {
  const [teamsRes, calendarRes] = await Promise.all([
    fetch("data/teams.json"),
    fetch("data/calendar.json"),
  ]);
  teams = await teamsRes.json();
  const calendar = await calendarRes.json();
  latestDate = calendar.latest_date;
  daysByDate = {};
  for (const day of calendar.days) {
    daysByDate[day.date] = day;
  }

  allDates = buildFullDateRange(TOURNAMENT_START, TOURNAMENT_END);
  selectedDate = latestDate;

  setupTimeline();
  selectDate(latestDate);
}

function buildFullDateRange(start, end) {
  const dates = [];
  let d = new Date(start + "T00:00:00Z");
  const endD = new Date(end + "T00:00:00Z");
  while (d <= endD) {
    dates.push(d.toISOString().slice(0, 10));
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return dates;
}

function dayNumber(dateStr) {
  const start = new Date(TOURNAMENT_START + "T00:00:00Z");
  const cur = new Date(dateStr + "T00:00:00Z");
  return Math.round((cur - start) / 86400000) + 1;
}

function formatDatePl(dateStr) {
  const d = new Date(dateStr + "T00:00:00Z");
  return d.toLocaleDateString("pl-PL", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
}

function formatDateShort(dateStr) {
  const [, month, day] = dateStr.split("-");
  return `${day}.${month}`;
}

function formatTimelineDate(dateStr, index) {
  if (index === 0 || index === allDates.length - 1) {
    const d = new Date(dateStr + "T00:00:00Z");
    return d.toLocaleDateString("pl-PL", {
      day: "numeric",
      month: "long",
      timeZone: "UTC",
    });
  }
  return formatDateShort(dateStr);
}

function formatDateShortPl(dateStr) {
  const d = new Date(dateStr + "T00:00:00Z");
  return d.toLocaleDateString("pl-PL", { day: "numeric", month: "short", timeZone: "UTC" });
}

function effectiveDayData(dateStr) {
  // "Dzisiaj" (latestDate) ma juz realne dane (wyniki/mecze policzone przez
  // pipeline) - pokazujemy je normalnie, tylko oznaczone jako "dzisiaj" (moga
  // dojsc kolejne wyniki tego samego dnia). Dopiero dni STRICTLY po latestDate
  // sa czysta projekcja - nic tam jeszcze nie policzono, wiec pokazujemy
  // ostatnia dostepna prognoze bez zadnych meczow.
  if (dateStr === latestDate) {
    const day = daysByDate[latestDate];
    if (!day) return { date: dateStr, prediction: [], matches: [], bracket: {}, isFutureOrToday: true };
    return { ...day, isFutureOrToday: true };
  }
  if (dateStr > latestDate) {
    const base = daysByDate[latestDate];
    return {
      date: dateStr,
      prediction: base ? base.prediction : [],
      base_rate: base ? base.base_rate : 1.3,
      bracket: base ? base.bracket : {},
      matches: [],
      isFutureOrToday: true,
    };
  }
  const day = daysByDate[dateStr];
  if (!day) {
    return { date: dateStr, prediction: [], matches: [], bracket: {}, isFutureOrToday: true };
  }
  return { ...day, isFutureOrToday: false };
}

function setupTimeline() {
  document.getElementById("timeline-start-label").textContent = formatDatePl(allDates[0]);
  document.getElementById("timeline-end-label").textContent = formatDatePl(allDates[allDates.length - 1]);

  const ticksContainer = document.getElementById("timeline-ticks");
  ticksContainer.innerHTML = "";
  const todayIdx = allDates.indexOf(latestDate);
  for (let i = 0; i < allDates.length; i++) {
    const dateStr = allDates[i];
    const tick = document.createElement("div");
    tick.className = "timeline-tick";
    tick.dataset.date = dateStr;
    tick.innerHTML = `<span class="timeline-tick-label">${formatTimelineDate(dateStr, i)}</span><span class="timeline-tick-dot"></span>`;
    tick.addEventListener("click", () => selectDate(dateStr));
    // Kolor kropki zalezy tylko od odleglosci od dzisiejszego dnia (nie od
    // wybranej/klikanej daty) - ten sam gradient zloty co w kroczku etapow,
    // ale osadzony na "dzis", zeby zawsze wskazywac aktualny dzien turnieju.
    const color = tickColorFor(i, todayIdx);
    if (color) tick.querySelector(".timeline-tick-dot").style.setProperty("--tick-color", color);
    ticksContainer.appendChild(tick);
  }

  // Przeciaganie bezposrednio po rzedzie kropek - ten sam ukland wspolrzednych
  // co same kropki, wiec zaznaczenie zawsze trafia dokladnie w date pod kursorem.
  let dragging = false;
  const pickDateFromEvent = (evt) => {
    const rect = ticksContainer.getBoundingClientRect();
    const clientX = evt.touches ? evt.touches[0].clientX : evt.clientX;
    const relX = clientX - rect.left + ticksContainer.scrollLeft;
    const tickWidth = ticksContainer.scrollWidth / allDates.length;
    const idx = Math.max(0, Math.min(allDates.length - 1, Math.floor(relX / tickWidth)));
    return allDates[idx];
  };
  const onDragMove = (evt) => {
    if (!dragging) return;
    const d = pickDateFromEvent(evt);
    if (d !== selectedDate) selectDate(d);
    if (evt.cancelable) evt.preventDefault();
  };
  ticksContainer.addEventListener("mousedown", (evt) => { dragging = true; onDragMove(evt); });
  window.addEventListener("mousemove", onDragMove);
  window.addEventListener("mouseup", () => { dragging = false; });
  ticksContainer.addEventListener("touchstart", (evt) => { dragging = true; onDragMove(evt); });
  window.addEventListener("touchmove", onDragMove, { passive: false });
  window.addEventListener("touchend", () => { dragging = false; });
}

function centerTimelineTick(tick) {
  const container = document.getElementById("timeline-ticks");
  if (!container || !tick) return;

  const targetLeft = tick.offsetLeft - (container.clientWidth / 2) + (tick.clientWidth / 2);
  const maxLeft = container.scrollWidth - container.clientWidth;
  const nextLeft = Math.max(0, Math.min(maxLeft, targetLeft));

  container.scrollTo({ left: nextLeft, behavior: "smooth" });
}

function resetPageScrollX() {
  if (window.scrollX === 0 && document.documentElement.scrollLeft === 0 && document.body.scrollLeft === 0) return;
  window.scrollTo({ left: 0, top: window.scrollY, behavior: "auto" });
  document.documentElement.scrollLeft = 0;
  document.body.scrollLeft = 0;
}

function selectDate(dateStr) {
  selectedDate = dateStr;
  document.getElementById("timeline-current-label").textContent = formatDatePl(dateStr);

  document.querySelectorAll(".timeline-tick").forEach((el) => {
    el.classList.toggle("selected", el.dataset.date === dateStr);
  });
  resetPageScrollX();

  const current = effectiveDayData(dateStr);
  const prevDateStr = allDates[allDates.indexOf(dateStr) - 1];
  const previous = prevDateStr ? effectiveDayData(prevDateStr) : null;

  const dayTypeLabel = current.isFutureOrToday
    ? `Prognoza na ${formatDatePl(dateStr)}`
    : `Podsumowanie dnia ${formatDatePl(dateStr)}`;
  document.getElementById("header-subtitle").textContent =
    `Mistrzostwa Świata w Piłce Nożnej 2026 - ${dayTypeLabel} (dzień turnieju ${dayNumber(dateStr)})`;
  document.getElementById("prediction-date-label").textContent = `(${formatDatePl(dateStr)})`;
  document.getElementById("reality-title").firstChild.textContent = dateStr === latestDate
    ? "Mecze dnia "
    : (current.isFutureOrToday ? "Zaplanowane mecze " : "Wyniki dnia ");
  document.getElementById("reality-date-label").textContent = current.isFutureOrToday ? "" : formatDatePl(dateStr);

  renderPrediction(current, previous);
  renderEliminated(current);
  renderReality(current);
  renderMovers(current, previous);
  renderHeroCards(current, previous);
  renderChart();
  renderBracket(current);
  renderStageStepper(current);
  setTimeout(sendEmbedHeight, 0);
}

function probBarStyle(pct) {
  const p = Math.max(0, Math.min(100, pct));
  return `background: linear-gradient(to right, #d99f2e 0%, #F5C451 ${p}%, #1D2940 ${p}%, #1D2940 100%);`;
}

function probabilityOf(dayData, teamId) {
  const entry = dayData.prediction.find((p) => p.team_id === teamId);
  return entry ? entry.probability : null;
}

function renderPrediction(current, previous) {
  const tbody = document.getElementById("ranking-body");
  tbody.innerHTML = "";

  const alive = current.prediction.filter((e) => !e.real_eliminated);

  alive.forEach((entry, idx) => {
    const team = teams[entry.team_id] || { name: "?" };
    const prevProb = previous ? probabilityOf(previous, entry.team_id) : null;
    const change = prevProb === null ? null : entry.probability - prevProb;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td><span class="team-name-cell">${flagImg(entry.team_id)}${team.name}</span></td>
      <td>
        <div class="prob-cell">
          <span class="prob-bar-wrap" style="${probBarStyle(entry.probability * 100)}"></span>
          <span class="prob-pct">${(entry.probability * 100).toFixed(1)}%</span>
        </div>
      </td>
      <td class="${changeClass(change)}">${formatChange(change)}</td>
    `;
    tr.addEventListener("click", () => openTeamModal(entry.team_id));
    tbody.appendChild(tr);
  });
}

function renderEliminated(current) {
  const container = document.getElementById("eliminated-list");
  const eliminated = current.prediction.filter((e) => e.real_eliminated);

  container.innerHTML = eliminated.length
    ? eliminated
        .map((e) => `<span class="eliminated-tag" data-team-id="${e.team_id}">${(teams[e.team_id] || {}).name || "?"}</span>`)
        .join("")
    : `<span class="empty-state">Jeszcze nikt nie odpadł.</span>`;

  container.querySelectorAll(".eliminated-tag").forEach((el) => {
    el.addEventListener("click", () => openTeamModal(Number(el.dataset.teamId)));
  });
}

function changeClass(change) {
  if (change === null) return "change-neutral";
  if (change > 0.001) return "change-up";
  if (change < -0.001) return "change-down";
  return "change-neutral";
}

function formatChange(change) {
  if (change === null) return "—";
  const pts = (change * 100).toFixed(1);
  if (change > 0.001) return `▲ ${pts}`;
  if (change < -0.001) return `▼ ${Math.abs(pts)}`;
  return "0.0";
}

const FINISHED_STATUSES = ["FT", "AET", "PEN"];

function hasMatchScore(match) {
  return match.home_goals !== null && match.home_goals !== undefined
    && match.away_goals !== null && match.away_goals !== undefined;
}

function isFinishedMatch(match) {
  return FINISHED_STATUSES.includes(match.status);
}

function isResultMatch(match) {
  return isFinishedMatch(match) || hasMatchScore(match);
}

function formatKickoff(isoDate) {
  if (!isoDate) return "";
  return new Date(isoDate).toLocaleTimeString("pl-PL", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Warsaw",
  });
}

function formatMatchDateTime(isoDate, fallbackDate) {
  if (isoDate) {
    const date = new Date(isoDate);
    const day = date.toLocaleDateString("pl-PL", {
      day: "numeric",
      month: "short",
      timeZone: "Europe/Warsaw",
    });
    const time = date.toLocaleTimeString("pl-PL", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Europe/Warsaw",
    });
    return `${day} · ${time}`;
  }
  return fallbackDate ? formatDateShortPl(fallbackDate) : "";
}

function preMatchPrediction(m, matchDate) {
  let idx = allDates.indexOf(matchDate) - 1;
  while (idx >= 0) {
    const day = daysByDate[allDates[idx]];
    if (day) {
      const home = day.prediction.find((entry) => entry.team_id === m.home_team_id);
      const away = day.prediction.find((entry) => entry.team_id === m.away_team_id);
      if (home && away) {
        const probs = matchResultProbabilities(
          home.attack, home.defense, away.attack, away.defense, day.base_rate || 1.3,
        );
        return { probs, date: day.date };
      }
    }
    idx -= 1;
  }
  return null;
}

function predictionPercentagesHtml(probs) {
  return `${(probs.winA * 100).toFixed(0)}% / remis ${(probs.draw * 100).toFixed(0)}% / ${(probs.winB * 100).toFixed(0)}%`;
}

function matchCardHtml(m, showScore, matchDate) {
  const home = teams[m.home_team_id] || { name: "?" };
  const away = teams[m.away_team_id] || { name: "?" };
  const middle = showScore && hasMatchScore(m) ? `${m.home_goals} : ${m.away_goals}` : "–";
  const kickoff = formatMatchDateTime(m.kickoff, matchDate);
  const forecast = showScore && matchDate ? preMatchPrediction(m, matchDate) : null;
  return `
    <div class="match-card">
      <div class="stage-label"><span>${stageLabel(m.stage)}</span>${kickoff ? `<time>${kickoff}</time>` : ""}</div>
      <div class="score-line">
        <span class="team-name-cell">${flagImg(m.home_team_id)}${home.name}</span>
        <span>${middle}</span>
        <span class="team-name-cell align-right">${away.name}${flagImg(m.away_team_id)}</span>
      </div>
      ${forecast ? `
        <div class="pre-match-forecast">
          <span>Prognoza przed meczem</span>
          <strong>${predictionPercentagesHtml(forecast.probs)}</strong>
        </div>
      ` : ""}
    </div>
  `;
}

function predictedMatchCardHtml(current, m) {
  const homeEntry = current.prediction.find((p) => p.team_id === m.home_team_id);
  const awayEntry = current.prediction.find((p) => p.team_id === m.away_team_id);

  const home = teams[m.home_team_id] || { name: "TBD" };
  const away = teams[m.away_team_id] || { name: "TBD" };
  const baseRate = current.base_rate || 1.3;
  const probs = homeEntry && awayEntry
    ? matchResultProbabilities(homeEntry.attack, homeEntry.defense, awayEntry.attack, awayEntry.defense, baseRate)
    : null;
  const kickoff = formatMatchDateTime(m.kickoff, current.date);
  return `
    <div class="match-card">
      <div class="stage-label"><span>${stageLabel(m.stage)} - przewidywanie</span>${kickoff ? `<time>${kickoff}</time>` : ""}</div>
      <div class="score-line">
        <span class="team-name-cell">${flagImg(m.home_team_id)}${home.name}</span>
        <span>${probs ? predictionPercentagesHtml(probs) : "termin znany · drużyny do ustalenia"}</span>
        <span class="team-name-cell align-right">${away.name}${flagImg(m.away_team_id)}</span>
      </div>
    </div>
  `;
}

function scheduledBracketMatchesForDate(current) {
  const bracket = current.bracket || {};
  const rows = [];
  for (const [stage, matches] of Object.entries(bracket)) {
    for (const match of matches || []) {
      if (match.date !== current.date || match.result) continue;
      rows.push({
        stage,
        home_team_id: match.team_a ?? null,
        away_team_id: match.team_b ?? null,
        home_goals: null,
        away_goals: null,
        status: "NS",
        kickoff: match.kickoff || null,
      });
    }
  }
  rows.sort((a, b) => (a.kickoff || "").localeCompare(b.kickoff || ""));
  return rows;
}

function renderReality(current) {
  const container = document.getElementById("matches-list");
  container.innerHTML = "";

  const finished = current.matches.filter(isResultMatch);
  const scheduledFromMatches = current.matches.filter((m) => !isResultMatch(m));
  const scheduled = scheduledFromMatches.length ? scheduledFromMatches : scheduledBracketMatchesForDate(current);

  if (!current.isFutureOrToday && finished.length === 0 && scheduled.length === 0) {
    container.innerHTML = `<div class="empty-state">Tego dnia nie rozegrano żadnego meczu.</div>`;
    return;
  }

  if (finished.length > 0) {
    container.innerHTML += finished.map((m) => matchCardHtml(m, true, current.date)).join("");
  }

  if (scheduled.length > 0) {
    // Realny, znany juz terminarz na ten dzien (np. mecze pozniej tego samego
    // dnia) - pokazujemy przewidywanie Poissona dla PRAWDZIWEJ pary druzyn,
    // zamiast zgadywania najbardziej prawdopodobnego rywala.
    container.innerHTML += `<h3 class="scheduled-heading">Przewidywania na zaplanowane mecze tego dnia</h3>`;
    container.innerHTML += scheduled.map((m) => predictedMatchCardHtml(current, m)).join("");
  } else if (current.isFutureOrToday) {
    container.innerHTML += `<div class="empty-state">Tego dnia nie ma zaplanowanych meczów.</div>`;
  }
}

function renderUpcomingPreviewHtml(current) {
  const topEntries = [...current.prediction].sort((a, b) => a.rank - b.rank).slice(0, 6);
  const cards = [];

  for (const entry of topEntries) {
    const info = nextMatchInfo(current, entry);
    if (!info) continue;
    const team = teams[entry.team_id] || { name: "?" };
    const oppTeam = teams[info.opponentId] || { name: "?" };
    const scheduledMatch = nearestBracketMatch(current, entry.team_id);
    const matchDate = scheduledMatch || bracketDateForStage(current, entry.team_id, info.stage);
    const kickoff = matchDate ? formatMatchDateTime(matchDate.kickoff, matchDate.date) : "";
    cards.push(`
      <div class="match-card">
        <div class="stage-label"><span>${stageLabel(info.stage)} - prawdopodobny rywal (${(info.opponentChance * 100).toFixed(0)}%)</span>${kickoff ? `<time>${kickoff}</time>` : ""}</div>
        <div class="score-line">
          <span>${team.name}</span>
          <span>${(info.probs.winA * 100).toFixed(0)}% / remis ${(info.probs.draw * 100).toFixed(0)}% / ${(info.probs.winB * 100).toFixed(0)}%</span>
          <span>${oppTeam.name}</span>
        </div>
      </div>
    `);
  }

  return cards.length
    ? cards.join("")
    : `<div class="empty-state">Ten dzień jeszcze się nie wydarzył - nie ma jeszcze czego pokazać.</div>`;
}

function stageLabel(stage) {
  const map = {
    group: "Faza grupowa", R32: "1/16 finału", R16: "1/8 finału",
    QF: "Ćwierćfinał", SF: "Półfinał", final: "Finał", third_place: "Mecz o 3. miejsce",
  };
  return map[stage] || stage;
}

function renderMovers(current, previous) {
  const upPanel = document.querySelector(".movers-up");
  const downPanel = document.querySelector(".movers-down");
  const upList = document.getElementById("movers-up-list");
  const downList = document.getElementById("movers-down-list");
  const upTitle = document.getElementById("movers-up-title");
  const downTitle = document.getElementById("movers-down-title");
  upList.innerHTML = "";
  downList.innerHTML = "";

  if (current.isFutureOrToday || !previous) {
    upPanel.classList.add("hidden");
    downPanel.classList.add("hidden");
    return;
  }
  upPanel.classList.remove("hidden");
  downPanel.classList.remove("hidden");
  upTitle.textContent = "Największy wzrost";
  downTitle.textContent = "Największy spadek";

  const changes = current.prediction.map((entry) => {
    const prevProb = probabilityOf(previous, entry.team_id);
    return {
      teamId: entry.team_id,
      name: (teams[entry.team_id] || {}).name || "?",
      change: prevProb === null ? 0 : entry.probability - prevProb,
    };
  });

  const sorted = [...changes].sort((a, b) => b.change - a.change);
  const risers = sorted.filter((c) => c.change > 0).slice(0, 5);
  const fallers = sorted.filter((c) => c.change < 0).slice(-5).reverse();

  for (const r of risers) {
    const li = document.createElement("li");
    li.innerHTML = `<span>${r.name}</span><span class="change-up">▲ ${(r.change * 100).toFixed(1)}</span>`;
    upList.appendChild(li);
  }
  for (const f of fallers) {
    const li = document.createElement("li");
    li.innerHTML = `<span>${f.name}</span><span class="change-down">▼ ${Math.abs(f.change * 100).toFixed(1)}</span>`;
    downList.appendChild(li);
  }
}

function sparklineSvg(teamId, uptoDate, color) {
  const idx = allDates.indexOf(uptoDate);
  const window = allDates.slice(0, idx + 1);
  const values = window
    .map((d) => daysByDate[d])
    .filter(Boolean)
    .map((day) => probabilityOf(day, teamId))
    .filter((v) => v !== null);

  if (values.length < 2) return "";

  const w = 90, h = 32, pad = 3;
  const min = 0;
  const observedMaxPct = Math.max(...values) * 100;
  const max = Math.max(20, Math.ceil((observedMaxPct * 1.25) / 10) * 10) / 100;
  const range = max - min;
  const points = values
    .map((v, i) => {
      const x = pad + (i / (values.length - 1)) * (w - pad * 2);
      const y = h - pad - ((v - min) / range) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return `<svg class="hero-sparkline" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}">
    <polyline points="${points}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;
}

function nearestBracketMatch(current, teamId) {
  const bracket = current.bracket || {};
  const stageKeys = ["R32", "R16", "QF", "SF", "final", "third_place"];
  const candidates = [];

  for (const stage of stageKeys) {
    for (const match of (bracket[stage] || [])) {
      if (match.result || !match.date || match.date < current.date) continue;
      if (match.team_a !== teamId && match.team_b !== teamId) continue;
      const opponentId = match.team_a === teamId ? match.team_b : match.team_a;
      if (opponentId !== null && opponentId !== undefined) {
        candidates.push({ stage, opponentId, date: match.date, kickoff: match.kickoff || null });
      }
    }
  }

  candidates.sort((a, b) => a.date.localeCompare(b.date));
  return candidates[0] || null;
}

function bracketDateForStage(current, teamId, stage) {
  const matches = ((current.bracket || {})[stage] || []).filter((match) => match.date);
  if (!matches.length) return null;

  const exact = matches.filter((match) => match.team_a === teamId || match.team_b === teamId);
  const pool = exact.length ? exact : matches;
  const sorted = [...pool].sort((a, b) => a.date.localeCompare(b.date));
  const futureOrToday = sorted.find((match) => match.date >= current.date);
  const match = futureOrToday || sorted[sorted.length - 1];

  return { stage, date: match.date, kickoff: match.kickoff || null };
}

function matchCountLabel(count) {
  if (count === 1) return "mecz";
  if (count >= 2 && count <= 4) return "mecze";
  return "meczów";
}

function goalBarsHtml(matches) {
  if (!matches.length) return `<div class="hero-goal-bars-empty">Brak meczów</div>`;
  const goals = matches.map((match) => Number(match.home_goals || 0) + Number(match.away_goals || 0));
  const maxGoals = Math.max(1, ...goals);
  return `<div class="hero-goal-bars" aria-label="Liczba goli w poszczególnych meczach">
    ${goals.map((value) => `<span style="--goal-height:${Math.max(8, (value / maxGoals) * 100)}%" title="${value} goli"></span>`).join("")}
  </div>`;
}

function renderHeroCards(current, previous) {
  const container = document.getElementById("hero-cards");
  const captionEl = document.getElementById("day-description");
  container.innerHTML = "";
  captionEl.textContent = "";

  if (current.prediction.length === 0) return;

  const leader = current.prediction[0];
  const leaderName = (teams[leader.team_id] || {}).name || "?";
  const prevLeaderId = previous && previous.prediction[0] ? previous.prediction[0].team_id : null;
  const leaderIsNew = previous && prevLeaderId !== null && prevLeaderId !== leader.team_id;
  const leaderMatch = nearestBracketMatch(current, leader.team_id);
  const leaderOpponent = leaderMatch ? (teams[leaderMatch.opponentId] || {}) : null;
  const leaderMatchHtml = leaderMatch && leaderOpponent ? `
    <div class="hero-next-match">
      <div class="hero-next-label">Najbliższy mecz</div>
      <div class="hero-next-team">${flagImg(leaderMatch.opponentId)}<strong>${leaderOpponent.name || "?"}</strong></div>
      <div class="hero-next-stage">${stageLabel(leaderMatch.stage)}</div>
      <div class="hero-next-date">${formatDateShort(leaderMatch.date)}${leaderMatch.kickoff ? ` · ${formatKickoff(leaderMatch.kickoff)}` : ""}</div>
      ${sparklineSvg(leader.team_id, current.date, "#F5B82E")}
    </div>
  ` : `<div class="hero-next-match hero-next-match-empty">Brak zaplanowanego meczu</div>`;

  const cards = [`
    <div class="hero-card hero-leader">
      <div class="hero-leader-main">
        <div class="hero-label">Lider${leaderIsNew ? " (nowy!)" : ""}</div>
        <div class="hero-team">${leaderName}</div>
        <div class="hero-value">${(leader.probability * 100).toFixed(1)}%</div>
        <div class="hero-caption">szans na mistrzostwo</div>
      </div>
      ${leaderMatchHtml}
    </div>
  `];

  if (previous) {
    const changes = current.prediction.map((entry) => {
      const prevProb = probabilityOf(previous, entry.team_id) ?? entry.probability;
      return {
        teamId: entry.team_id,
        name: (teams[entry.team_id] || {}).name || "?",
        change: entry.probability - prevProb,
      };
    });
    const sorted = [...changes].sort((a, b) => b.change - a.change);
    const topRiser = sorted[0];
    const topFaller = sorted[sorted.length - 1];

    if (topRiser && topRiser.change > 0.005) {
      cards.push(`
        <div class="hero-card hero-up">
          <div class="hero-label">Największy wzrost</div>
          <div class="hero-team">${topRiser.name}</div>
          <div class="hero-value">▲ ${(topRiser.change * 100).toFixed(1)} pp</div>
          <div class="hero-caption">względem poprzedniego dnia</div>
          ${sparklineSvg(topRiser.teamId, current.date, "#22C55E")}
        </div>
      `);
    }
    if (topFaller && topFaller.change < -0.005) {
      cards.push(`
        <div class="hero-card hero-down">
          <div class="hero-label">Największy spadek</div>
          <div class="hero-team">${topFaller.name}</div>
          <div class="hero-value">▼ ${Math.abs(topFaller.change * 100).toFixed(1)} pp</div>
          <div class="hero-caption">względem poprzedniego dnia</div>
          ${sparklineSvg(topFaller.teamId, current.date, "#EF4444")}
        </div>
      `);
    }
  }

  const allDayMatches = current.matches || [];
  const dayMatches = allDayMatches.filter(hasMatchScore);
  const totalGoals = dayMatches.reduce(
    (sum, match) => sum + Number(match.home_goals || 0) + Number(match.away_goals || 0),
    0,
  );
  const averageGoals = dayMatches.length ? totalGoals / dayMatches.length : 0;
  const dayCardLabel = current.date === latestDate ? "Dzisiaj z wynikiem" : "Mecze z wynikiem";
  cards.push(`
    <div class="hero-card hero-day">
      <div class="hero-label">${dayCardLabel}</div>
      <div class="hero-day-stats">
        <div class="hero-day-primary">
          <strong>${dayMatches.length}</strong>
          <span>${matchCountLabel(dayMatches.length)}${allDayMatches.length !== dayMatches.length ? ` z ${allDayMatches.length}` : ""}</span>
        </div>
        <div class="hero-day-stat">
          <span>Gole</span>
          <strong>${totalGoals}</strong>
        </div>
        <div class="hero-day-stat">
          <span>Średnia goli</span>
          <strong>${averageGoals.toFixed(2)}</strong>
        </div>
      </div>
      ${goalBarsHtml(dayMatches)}
    </div>
  `);

  container.innerHTML = cards.join("");
}

function renderChart() {
  const latestDay = daysByDate[latestDate];
  if (!latestDay) return;

  const topTeamIds = [...latestDay.prediction].sort((a, b) => a.rank - b.rank).slice(0, 8).map((e) => e.team_id);
  const labels = allDates.filter((d) => d <= latestDate);

  const datasets = topTeamIds.map((teamId, idx) => {
    const data = labels.map((dateStr) => {
      const day = daysByDate[dateStr];
      if (!day) return null;
      const prob = probabilityOf(day, teamId);
      return prob === null ? null : prob * 100;
    });
    return {
      label: (teams[teamId] || {}).name || "?",
      data,
      borderColor: colorForIndex(idx),
      backgroundColor: "transparent",
      borderWidth: 3,
      tension: 0.2,
      pointRadius: 0,
      pointStyle: "line",
    };
  });

  const ctx = document.getElementById("history-chart").getContext("2d");
  if (historyChart) historyChart.destroy();
  historyChart = new Chart(ctx, {
    type: "line",
    data: { labels: labels.map(formatDatePl), datasets },
    options: {
      responsive: true,
      interaction: { mode: "nearest", intersect: false },
      scales: {
        y: { ticks: { color: "#9CA3AF", callback: (v) => v + "%" }, grid: { color: "#263247" } },
        x: { ticks: { color: "#9CA3AF", maxRotation: 60, minRotation: 60 }, grid: { color: "#263247" } },
      },
      plugins: { legend: { labels: { color: "#F5F7FA", usePointStyle: true, pointStyleWidth: 20, boxHeight: 3 } } },
    },
  });
}

function colorForIndex(idx) {
  const palette = ["#F5C451", "#4EA8FF", "#22C55E", "#EF4444", "#a874e8", "#33c3d6", "#ff8a5c", "#c4d635"];
  return palette[idx % palette.length];
}

const BRACKET_STAGE_TITLES = {
  R32: "1/16 finału", R16: "1/8 finału", QF: "Ćwierćfinał", SF: "Półfinał", final: "Final",
};

const TROPHY_IMG = `<img src="images/puchar.png" alt="Puchar">`;

function pick(arr, indices) {
  return indices.map((i) => arr[i]);
}

// Sztywny, publicznie znany harmonogram etapow (daty ogloszone przed
// turniejem, niezalezne od wynikow) - kazdy zakres siega do dnia przed
// poczatkiem kolejnego etapu, zeby nie bylo dziur (dni przerwy naleza do
// etapu, ktory wlasnie sie zakonczyl/za chwile zacznie).
const STAGE_STEPPER_ITEMS = [
  { key: "group", label: "Faza grupowa", matches: "64 mecze", start: "2026-06-11" },
  { key: "R32", label: "1/16 finału", matches: "16 meczów", start: "2026-06-28" },
  { key: "R16", label: "1/8 finału", matches: "8 meczów", start: "2026-07-04" },
  { key: "QF", label: "Ćwierćfinały", matches: "4 mecze", start: "2026-07-09" },
  { key: "SF", label: "Półfinały", matches: "2 mecze", start: "2026-07-14" },
  { key: "final", label: "Finał", matches: "1 mecz", start: "2026-07-19", finalDate: "19.07.2026" },
];

function currentStageIndex(dateStr) {
  let idx = 0;
  for (let i = 0; i < STAGE_STEPPER_ITEMS.length; i++) {
    if (dateStr >= STAGE_STEPPER_ITEMS[i].start) idx = i;
  }
  return idx;
}

const STAGE_GRADIENT_START = [138, 122, 92]; // zolto-szary
const STAGE_GRADIENT_END = [245, 196, 81]; // zloty (--accent-gold)

function interpolateRgb(t) {
  const r = Math.round(STAGE_GRADIENT_START[0] + (STAGE_GRADIENT_END[0] - STAGE_GRADIENT_START[0]) * t);
  const g = Math.round(STAGE_GRADIENT_START[1] + (STAGE_GRADIENT_END[1] - STAGE_GRADIENT_START[1]) * t);
  const b = Math.round(STAGE_GRADIENT_START[2] + (STAGE_GRADIENT_END[2] - STAGE_GRADIENT_START[2]) * t);
  return `rgb(${r}, ${g}, ${b})`;
}

// Gradient od pierwszego dnia turnieju (najslabszy, szaro-zolty) az do
// dzisiaj (pelny zloty); dni po dzisiejszym pozostaja neutralne.
function tickColorFor(idx, todayIdx) {
  if (todayIdx < 0 || idx > todayIdx) return null;
  if (todayIdx === 0) return interpolateRgb(1);
  return interpolateRgb(idx / todayIdx);
}

// Kolor zalezy od odleglosci OD AKTUALNEGO etapu, nie od pozycji bezwzglednej:
// aktualny etap = zawsze pelny zloty; wczesniejsze (zakonczone) etapy blakna
// im dalej wstecz; przyszle etapy zostaja neutralne (jak przed zmiana).
function stageColorFor(idx, currentIdx) {
  if (idx > currentIdx) return null;
  if (currentIdx === 0) return idx === 0 ? interpolateRgb(1) : null;
  return interpolateRgb(idx / currentIdx);
}

function renderStageStepper(current) {
  const container = document.getElementById("stage-stepper");
  const currentIdx = currentStageIndex(current.date);

  container.innerHTML = STAGE_STEPPER_ITEMS.map((item, idx) => {
    const isCompleted = idx < currentIdx;
    const isCurrent = idx === currentIdx;
    const state = isCompleted ? "completed" : isCurrent ? "current" : "future";
    const marker = idx === 0 && isCompleted ? "✓" : String(idx + 1);
    const status = isCompleted
      ? "Ukończona"
      : isCurrent
        ? "Trwa"
        : (item.finalDate || "Nadchodzące");
    return `
      <div class="stage-step ${state}">
        <div class="stage-dot"><span>${marker}</span></div>
        <div class="stage-step-label">${item.label}</div>
        <div class="stage-step-matches">${item.matches}</div>
        <div class="stage-step-status">${status}</div>
      </div>
    `;
  }).join("");
}

function renderBracket(current) {
  const container = document.getElementById("bracket");
  container.innerHTML = "";

  const bracket = current.bracket || {};
  const r32 = bracket.R32 || [];
  const r16 = bracket.R16 || [];
  const qf = bracket.QF || [];
  const sf = bracket.SF || [];
  const final = bracket.final || [];
  const thirdPlace = bracket.third_place || [];
  if (r32.length === 0) return;

  const leftHalf = buildHalf(
    pick(r32, [0, 1, 2, 3, 8, 9, 10, 11]),
    pick(r16, [0, 1, 4, 5]),
    pick(qf, [0, 1]),
    sf[0],
    false,
  );
  const rightHalf = buildHalf(
    pick(r32, [4, 5, 6, 7, 12, 13, 14, 15]),
    pick(r16, [2, 3, 6, 7]),
    pick(qf, [2, 3]),
    sf[1],
    true,
  );

  const centerCol = document.createElement("div");
  centerCol.className = "bracket-center";
  const trophyDiv = document.createElement("div");
  trophyDiv.className = "bracket-trophy";
  trophyDiv.innerHTML = TROPHY_IMG + `<div class="bracket-trophy-label">ZWYCIĘZCA</div>`;
  centerCol.appendChild(trophyDiv);
  if (final[0]) {
    const finalLabel = document.createElement("div");
    finalLabel.className = "bracket-final-label";
    finalLabel.textContent = "FINAŁ";
    const finalWrap = document.createElement("div");
    finalWrap.className = "bracket-final-match";
    finalWrap.appendChild(renderBracketMatch(final[0], "has-incoming has-incoming-right"));
    finalWrap.appendChild(finalLabel);
    centerCol.appendChild(finalWrap);
  }
  if (thirdPlace[0]) {
    const thirdPlaceLabel = document.createElement("div");
    thirdPlaceLabel.className = "bracket-third-place-label";
    thirdPlaceLabel.textContent = "MECZ O 3. MIEJSCE";
    const thirdPlaceWrap = document.createElement("div");
    thirdPlaceWrap.className = "bracket-third-place";
    thirdPlaceWrap.appendChild(renderBracketMatch(thirdPlace[0]));
    thirdPlaceWrap.appendChild(thirdPlaceLabel);
    centerCol.appendChild(thirdPlaceWrap);
  }

  container.appendChild(leftHalf);
  container.appendChild(centerCol);
  container.appendChild(rightHalf);
}

function buildHalf(r32Entries, r16Entries, qfEntries, sfEntry, mirrored) {
  const half = document.createElement("div");
  half.className = "bracket-half" + (mirrored ? " mirrored" : "");

  const pairedRounds = [
    { entries: r32Entries, cls: "round-r32", first: true },
    { entries: r16Entries, cls: "round-r16" },
    { entries: qfEntries, cls: "round-qf" },
  ];

  for (const round of pairedRounds) {
    const col = document.createElement("div");
    col.className = "bracket-round " + round.cls + (round.first ? "" : " has-incoming");
    for (let i = 0; i < round.entries.length; i += 2) {
      const pair = document.createElement("div");
      pair.className = "bracket-pair";
      pair.appendChild(renderBracketMatch(round.entries[i]));
      if (round.entries[i + 1]) pair.appendChild(renderBracketMatch(round.entries[i + 1]));
      col.appendChild(pair);
    }
    half.appendChild(col);
  }

  const sfCol = document.createElement("div");
  sfCol.className = "bracket-round round-sf has-incoming";
  if (sfEntry) {
    const wrap = document.createElement("div");
    wrap.className = "bracket-pair bracket-pair-single";
    wrap.appendChild(renderBracketMatch(sfEntry));
    sfCol.appendChild(wrap);
  }
  half.appendChild(sfCol);

  if (mirrored) half.style.flexDirection = "row-reverse";
  return half;
}

function flagImg(teamId) {
  const team = teams[teamId] || {};
  if (!team.iso) return "";
  return `<img class="flag-icon" src="https://flagcdn.com/24x18/${team.iso}.png" alt="" width="20" height="15">`;
}

function renderBracketMatch(entry, extraClass) {
  const div = document.createElement("div");
  div.className = "bracket-match" + (extraClass ? " " + extraClass : "");

  const winnerId = entry.result ? entry.result.winner_team_id : null;
  const teamsRow = document.createElement("div");
  teamsRow.className = "bracket-match-teams";

  [entry.team_a, entry.team_b].forEach((teamId) => {
    const cell = document.createElement("div");
    if (teamId === null) {
      cell.className = "bracket-team-cell tbd";
      cell.textContent = "TBD";
    } else {
      const team = teams[teamId] || { name: "?" };
      const isWinner = winnerId !== null && winnerId === teamId;
      const isLoser = winnerId !== null && winnerId !== teamId;
      cell.className = "bracket-team-cell" + (isWinner ? " winner" : "") + (isLoser ? " loser" : "") + (teamId === highlightedTeamId ? " highlighted" : "");
      cell.innerHTML = `${flagImg(teamId)}<span class="bracket-team-code">${team.code || team.name}</span>`;
      cell.addEventListener("click", () => {
        highlightedTeamId = highlightedTeamId === teamId ? null : teamId;
        renderBracket(effectiveDayData(selectedDate));
      });
    }
    teamsRow.appendChild(cell);
  });
  div.appendChild(teamsRow);

  if (entry.result) {
    const scoreRow = document.createElement("div");
    scoreRow.className = "bracket-match-score";
    scoreRow.textContent = `${entry.result.home_goals} - ${entry.result.away_goals}`;
    div.appendChild(scoreRow);
  }
  if (entry.date) {
    const dateRow = document.createElement("div");
    dateRow.className = "bracket-match-date";
    const kickoff = formatKickoff(entry.kickoff);
    dateRow.textContent = `${formatDateShortPl(entry.date)}${kickoff ? ` · ${kickoff}` : ""}`;
    div.appendChild(dateRow);
  }

  return div;
}

function openTeamModal(teamId) {
  const team = teams[teamId] || { name: "?" };
  const current = effectiveDayData(selectedDate);
  const entry = current.prediction.find((p) => p.team_id === teamId);
  if (!entry) return;

  const selectedIdx = allDates.indexOf(selectedDate);
  const previousDate = selectedIdx > 0 ? allDates[selectedIdx - 1] : null;
  const previous = previousDate ? effectiveDayData(previousDate) : null;
  const previousEntry = previous ? previous.prediction.find((p) => p.team_id === teamId) : null;
  const flag = team.iso
    ? `<img class="modal-team-flag" src="https://flagcdn.com/80x60/${team.iso}.png" alt="Flaga: ${team.name}">`
    : `<div class="modal-team-flag modal-team-flag-placeholder"></div>`;

  const modal = document.getElementById("team-modal");
  const body = document.getElementById("modal-body");
  body.innerHTML = `
    <div class="modal-team-header">
      ${flag}
      <div>
        <h2>${team.name} <span class="modal-favorite-star">☆</span></h2>
        <p>Grupa ${team.group || "?"} <span>•</span> ${entry.matches_played} rozegranych meczów do tego dnia</p>
      </div>
    </div>

    <div class="modal-top-grid">
      ${renderModalProbabilityCard(entry, previousEntry)}
      ${renderModalRivalCard(current, entry)}
      ${renderBracketPath(entry)}
    </div>

    ${renderModalIndices(entry)}

    <div class="modal-summary-card">
      <div class="modal-strength">
        <strong>${fmtIdx(entry.strength)}</strong>
        <span>Siła ogólna zespołu</span>
      </div>
      <div class="modal-summary-item">
        <img src="images/Selekcjoner.png" alt="">
        <div><span>Selekcjoner</span><strong>${team.coach_name || "—"}</strong></div>
      </div>
      <div class="modal-summary-item">
        <img src="images/Kapitan.png" alt="">
        <div><span>Kapitan</span><strong>${team.captain_name || "—"}</strong></div>
      </div>
      <div class="modal-summary-item">
        <img src="images/Sredni_wiek.png" alt="">
        <div><span>Średnia wieku</span><strong>${team.average_age !== null && team.average_age !== undefined ? Number(team.average_age).toFixed(1) : "—"}</strong></div>
      </div>
      <div class="modal-summary-item">
        <img src="images/FIFA_ranking.png" alt="">
        <div><span>Ranking FIFA</span><strong>${team.fifa_rank ? `${team.fifa_rank}.` : "—"}</strong></div>
      </div>
    </div>

    <div class="modal-history-card">
      <h3>Historia szans na mistrzostwo</h3>
      <div class="modal-history-chart-wrap">
        <canvas id="modal-history-chart"></canvas>
      </div>
    </div>
  `;
  modal.classList.remove("hidden");
  renderModalHistoryChart(teamId);
}

function renderModalProbabilityCard(entry, previousEntry) {
  const change = previousEntry ? entry.probability - previousEntry.probability : null;
  const changeText = change === null ? "—" : `${change >= 0 ? "▲" : "▼"} ${Math.abs(change * 100).toFixed(1)} pp`;
  const rankText = `${entry.rank}. miejsce`;
  return `
    <section class="modal-dashboard-card modal-probability-card">
      <h3>Szansa na mistrzostwo</h3>
      <div class="modal-probability-value">${(entry.probability * 100).toFixed(1)}%</div>
      <div class="modal-rank-label">miejsce ${entry.rank}</div>
      ${sparklineSvg(entry.team_id, selectedDate, "#F5B82E")}
      <div class="modal-probability-deltas">
        <div class="${changeClass(change)}"><strong>${changeText}</strong><span>zmiana vs wczoraj</span></div>
        <div class="modal-rank-change"><strong>${rankText}</strong><span>w rankingu ogólnym</span></div>
      </div>
    </section>
  `;
}

function renderModalRivalCard(dayData, entry) {
  const info = nextMatchInfo(dayData, entry);
  if (!info) {
    return `<section class="modal-dashboard-card modal-rival-card"><h3>Najbardziej prawdopodobny rywal</h3><div class="modal-card-empty">Brak kolejnego rywala</div></section>`;
  }
  const opponent = teams[info.opponentId] || { name: "?" };
  const scores = info.scorelines
    .map((score) => `<span>${score[0]}:${score[1]} (${(score[2] * 100).toFixed(0)}%)</span>`)
    .join("");
  return `
    <section class="modal-dashboard-card modal-rival-card">
      <h3>Najbardziej prawdopodobny rywal</h3>
      <div class="modal-rival-team">
        ${flagImg(info.opponentId)}
        <strong>${opponent.name}</strong>
        <span>${(info.opponentChance * 100).toFixed(0)}%</span>
      </div>
      <p>${stageLabel(info.stage)} (jeśli drużyna dotrze)</p>
      <div class="modal-result-title">Szacowane prawdopodobieństwo wyniku po 90 minutach</div>
      <div class="modal-result-probs">
        <div><span>Wygrana</span><strong class="change-up">${(info.probs.winA * 100).toFixed(0)}%</strong></div>
        <div><span>Remis</span><strong>${(info.probs.draw * 100).toFixed(0)}%</strong></div>
        <div><span>Porażka</span><strong class="change-down">${(info.probs.winB * 100).toFixed(0)}%</strong></div>
      </div>
      <div class="modal-score-title">3 najbardziej prawdopodobne dokładne wyniki</div>
      <div class="modal-score-pills">${scores}</div>
    </section>
  `;
}

function renderModalIndices(entry) {
  const indices = [
    ["Atak.png", "Atak", entry.attack],
    ["Obrona.png", "Obrona", entry.defense],
    ["Kontrola.png", "Kontrola", entry.control],
    ["Efektywnosc.png", "Efektywność", entry.efficiency],
    ["Dyscyplina.png", "Dyscyplina", entry.discipline],
    ["Forma.png", "Forma", entry.form],
  ];
  return `
    <section class="modal-indices-card">
      <h3>Kluczowe statystyki <span>(rating 0–100)</span></h3>
      <div class="modal-indices-row">
        ${indices.map(([icon, label, value]) => `
          <div class="modal-index-item">
            <span class="modal-index-icon"><img src="images/${icon}" alt=""></span>
            <div><strong>${fmtIdx(value)}</strong><span>${label}</span></div>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

function renderModalHistoryChart(teamId) {
  const canvas = document.getElementById("modal-history-chart");
  if (!canvas) return;
  if (modalHistoryChart) modalHistoryChart.destroy();

  const dates = allDates.filter((date) => date <= selectedDate && daysByDate[date]);
  const values = dates.map((date) => (probabilityOf(daysByDate[date], teamId) || 0) * 100);
  const suggestedMax = Math.max(20, Math.ceil((Math.max(...values, 0) * 1.25) / 10) * 10);
  modalHistoryChart = new Chart(canvas.getContext("2d"), {
    type: "line",
    data: {
      labels: dates.map(formatDateShort),
      datasets: [{
        data: values,
        borderColor: "#F5B82E",
        backgroundColor: "rgba(245, 184, 46, .06)",
        fill: true,
        borderWidth: 2,
        tension: .25,
        pointRadius: 2.5,
        pointHoverRadius: 5,
        pointBackgroundColor: "#0d1a2b",
        pointBorderColor: "#F5B82E",
        pointBorderWidth: 1.5,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { display: false } },
      scales: {
        y: {
          beginAtZero: true,
          suggestedMax,
          ticks: { color: "#8090a4", callback: (value) => value + "%", maxTicksLimit: 5 },
          grid: { color: "rgba(73, 96, 124, .22)" },
        },
        x: {
          ticks: { color: "#8090a4", maxTicksLimit: 7, maxRotation: 0 },
          grid: { color: "rgba(73, 96, 124, .14)" },
        },
      },
    },
  });
}

function renderNextMatch(dayData, entry) {
  const info = nextMatchInfo(dayData, entry);
  if (!info) return "";

  const team = teams[entry.team_id] || { name: "?" };
  const oppTeam = teams[info.opponentId] || { name: "?" };
  const scoreLines = info.scorelines
    .map((s) => `${s[0]}:${s[1]} <span class="score-pct">(${(s[2] * 100).toFixed(0)}%)</span>`)
    .join(", ");

  return `
    <div class="next-match">
      <h3>Jeśli ${team.name} dotrze do etapu: ${stageLabel(info.stage)} <span class="next-match-reach">(${(info.reachProbability * 100).toFixed(0)}% szans, że tam dotrze)</span></h3>
      <p class="next-match-teams">Najbardziej prawdopodobny rywal: ${oppTeam.name} <span class="next-match-chance">(${(info.opponentChance * 100).toFixed(0)}% szans, że to on)</span></p>
      <div class="next-match-probs">
        <span>Wygrana: <strong>${(info.probs.winA * 100).toFixed(0)}%</strong></span>
        <span>Remis: <strong>${(info.probs.draw * 100).toFixed(0)}%</strong></span>
        <span>Porażka: <strong>${(info.probs.winB * 100).toFixed(0)}%</strong></span>
      </div>
      <p class="next-match-scores">Najbardziej prawdopodobne wyniki tego meczu: ${scoreLines}</p>
    </div>
  `;
}

function renderBracketPath(entry) {
  const stages = [
    { key: "p_r32", label: "1/16 finału" },
    { key: "p_r16", label: "1/8 finału" },
    { key: "p_qf", label: "Ćwierćfinał" },
    { key: "p_sf", label: "Półfinał" },
    { key: "p_final", label: "Finał" },
    { key: "probability", label: "Mistrzostwo" },
  ];
  const rows = stages.map((s) => {
    const value = entry[s.key];
    if (value === undefined || value === null) return "";
    return `
      <div class="bracket-row">
        <span class="bracket-label">${s.label}</span>
        <span class="prob-bar-wrap" style="${probBarStyle(value * 100)}"></span>
        <span class="bracket-pct">${(value * 100).toFixed(1)}%</span>
      </div>
    `;
  }).join("");
  return `<div class="bracket-path"><h3>Szansa dotarcia do etapu</h3>${rows}</div>`;
}

function fmtIdx(value) {
  return value === undefined || value === null ? "—" : value.toFixed(1);
}

document.getElementById("modal-close").addEventListener("click", () => {
  document.getElementById("team-modal").classList.add("hidden");
});
document.getElementById("team-modal").addEventListener("click", (e) => {
  if (e.target.id === "team-modal") e.target.classList.add("hidden");
});

function sendEmbedHeight() {
  if (window.parent === window) return;
  const contentSelectors = [".site-header", ".timeline-section", ".layout", ".site-footer"];
  const contentBottom = contentSelectors.reduce((maxBottom, selector) => {
    const el = document.querySelector(selector);
    if (!el) return maxBottom;
    const rect = el.getBoundingClientRect();
    return Math.max(maxBottom, rect.bottom + window.scrollY);
  }, 0);
  const height = Math.ceil(contentBottom + 24);
  window.parent.postMessage(
    {
      source: "road-to-the-trophy-2026",
      iframeHeight: height,
    },
    "*"
  );
}

function initEmbedHeightMessenger() {
  if (window.parent === window) return;

  sendEmbedHeight();
  window.addEventListener("load", sendEmbedHeight);
  window.addEventListener("resize", sendEmbedHeight);

  if ("ResizeObserver" in window) {
    const observer = new ResizeObserver(sendEmbedHeight);
    observer.observe(document.documentElement);
    if (document.body) observer.observe(document.body);
  } else {
    setInterval(sendEmbedHeight, 1000);
  }
}

initEmbedHeightMessenger();
loadData();
