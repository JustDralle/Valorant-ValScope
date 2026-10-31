const SMURF_LIKELY = 60;
const CAREER_FILTERS = ["All", "Competitive", "Unrated", "Swiftplay", "Other"];
const ROUND_RESULTS = { "Eliminated": "E", "Bomb defused": "D", "Bomb detonated": "B", "Round timer expired": "T", "Surrendered": "S" };
const PARTY_COLORS = ["#a78bfa", "#f59e0b", "#38bdf8", "#f472b6", "#a3e635"];

const S = {
  tab: "live",
  status: { kind: "idle", text: "Starting..." },
  players: [],
  onlyHidden: false,
  known: {},        // puuid -> player, for the pages
  pages: [],        // overlay pages: {type: "player"|"match", ...}
  career: { started: false, loading: false, error: null, me: null, matches: [], total: 0, xp: null, filter: "All", loadingMore: false },
};

const $ = (sel) => document.querySelector(sel);
const api = () => window.pywebview.api;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const img = (url, cls = "") => (url ? `<img src="${esc(url)}" class="${cls}" alt="">` : "");
const scoreClass = (s) => (s == null ? "muted" : s >= SMURF_LIKELY ? "red" : s >= 35 ? "yellow" : "green");
const pct = (v) => (v == null ? "-" : `${v}%`);
const dash = (v) => (v == null ? "-" : v);
const fmtDate = (ms, withYear = false) => new Date(ms).toLocaleString("fr-FR", {
  day: "2-digit", month: "2-digit", ...(withYear ? { year: "numeric" } : {}), hour: "2-digit", minute: "2-digit",
}).replace(",", "");

let toastTimer;
function toast(text, error = false) {
  const t = $("#toast");
  t.textContent = text;
  t.className = `toast show${error ? " error" : ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = "toast"), 2000);
}

function remember(p) {
  S.known[p.puuid] = p;
  return p;
}

// ---------- events pushed by Python ----------

window.onEvent = (e) => {
  if (e.type === "status") S.status = { kind: e.kind, text: e.text };
  if (e.type === "players") S.players = e.players.map(remember);
  renderLive();
};

// ---------- live match ----------

function statChips(p) {
  return [
    `<span class="chip">${img(p.rankIcon)}${esc(p.rank || "Unranked")}</span>`,
    p.peakTier > p.tier ? `<span class="chip muted">Peak ${esc(p.peak)}</span>` : "",
    p.rankedGames != null ? `<span class="chip">${p.rankedGames} ranked</span>` : "",
    p.actWinRate != null ? `<span class="chip">Act ${p.actWinRate}% (${p.actGames})</span>` : "",
    p.avgWinRR != null ? `<span class="chip ${p.avgWinRR >= 27 ? "red" : p.avgWinRR >= 23 ? "yellow" : ""}">+${p.avgWinRR} RR/win</span>` : "",
  ].join("");
}

function playerCard(p) {
  const likely = (p.smurfScore || 0) >= SMURF_LIKELY;
  const withheld = !p.full_name.includes("#");
  const chips = statChips(p);
  return `
    <div class="pcard${p.incognito ? " hidden-player" : ""}${likely ? " likely" : ""}" data-player="${esc(p.puuid)}">
      ${p.agentIcon ? img(p.agentIcon, "agent-icon") : `<div class="agent-icon"></div>`}
      <div class="pname">
        <span class="name${withheld ? " withheld" : ""}">${esc(p.full_name)}</span>
        ${p.isSelf ? `<span class="badge you">YOU</span>` : ""}
        ${p.inMyParty ? `<span class="badge party">YOUR PARTY</span>` : ""}
        ${p.incognito ? `<span class="badge hidden-badge">HIDDEN</span>` : ""}
      </div>
      <div class="sub">${esc(p.agent.toUpperCase())} · ${p.level ? `Lvl ${p.level}` : "Lvl hidden"}</div>
      <div class="chips">${chips}</div>
      <div class="reasons">${esc((p.smurfReasons || []).join(" · ") || "No smurf signs")}</div>
      <div class="pside">
        <span class="score ${scoreClass(p.smurfScore)}">${p.smurfScore != null ? p.smurfScore + "%" : "?"}</span>
        <span class="score-label">SMURF</span>
        ${withheld ? "" : `<button class="btn small" data-copy="${esc(p.full_name)}">Copy</button>`}
      </div>
    </div>`;
}

function renderLive() {
  const teams = ["Attacking", "Defending"].map((side) => {
    const list = S.players
      .filter((p) => p.team === side && (p.incognito || !S.onlyHidden))
      .sort((a, b) => (b.smurfScore || 0) - (a.smurfScore || 0));
    const body = list.length ? list.map(playerCard).join("")
      : `<div class="empty">${S.players.length ? "No players to show" : "Waiting for a match"}</div>`;
    return `<div class="team"><h2 class="${side === "Attacking" ? "red" : "teal"}">${side.toUpperCase()}</h2><div class="list">${body}</div></div>`;
  }).join("");
  $("#live").innerHTML = `
    <div class="status"><span class="dot ${esc(S.status.kind)}"></span><span class="text">${esc(S.status.text)}</span>
      <span class="hint">Smurf % is an estimate from level, ranked games, RR per win and win rate</span></div>
    <div class="teams">${teams}</div>`;
}

// ---------- shared pieces ----------

function summarize(matches) {
  const avg = (key) => {
    const v = matches.map((m) => m[key]).filter((x) => x != null);
    return v.length ? Math.round(v.reduce((a, b) => a + b, 0) / v.length) : null;
  };
  const kills = matches.reduce((a, m) => a + m.kills, 0), deaths = matches.reduce((a, m) => a + m.deaths, 0);
  const decided = matches.filter((m) => m.won != null);
  return {
    kd: matches.length ? Math.round((kills / Math.max(deaths, 1)) * 100) / 100 : null,
    acs: avg("acs"), adr: avg("adr"), hs: avg("hs"),
    winRate: decided.length ? Math.round((100 * decided.filter((m) => m.won).length) / decided.length) : null,
  };
}

function tiles(s, matchesLabel, highlight = false) {
  const tile = (k, v, red) => `<div class="tile"><div class="v${red ? " red" : ""}">${v}</div><div class="k">${k}</div></div>`;
  return `<div class="tiles">
    ${tile("K/D", dash(s.kd), highlight && s.kd >= 1.5)}
    ${tile("ACS", dash(s.acs), highlight && s.acs >= 280)}
    ${tile("ADR", dash(s.adr))}
    ${tile("HS %", pct(s.hs), highlight && s.hs >= 30)}
    ${tile("WIN RATE", pct(s.winRate))}
    ${tile("MATCHES", matchesLabel)}
  </div>`;
}

function matchRow(m, puuid) {
  const cls = m.won === true ? "win" : m.won === false ? "loss" : "";
  const result = m.won === true ? "WIN" : m.won === false ? "LOSS" : "";
  const head = `${result} ${m.scoreLine || ""}`.trim() || m.queue;
  // only matches with Riot's details (not HenrikDev search results) open a scoreboard
  const open = m.id ? ` data-match="${esc(m.id)}" data-for="${esc(puuid)}"` : "";
  return `
    <div class="mrow ${cls}${m.id ? " clickable" : ""}"${open}>
      <span class="bar"></span>${img(m.agentIcon)}
      <div class="info"><div class="result">${esc(head)}</div>
        <div class="sub">${esc(m.map)} · ${esc(m.queue)} · ${fmtDate(m.start)}${m.tier ? " · " + esc(m.tier) : ""}</div></div>
      <div class="mstats">
        <div><b>${m.kills} / ${m.deaths} / ${m.assists}</b><span>K / D / A</span></div>
        <div><b>${dash(m.acs)}</b><span>ACS</span></div>
        <div><b>${dash(m.adr)}</b><span>ADR</span></div>
        <div><b>${pct(m.hs)}</b><span>HS</span></div>
      </div>
    </div>`;
}

// ---------- career ----------

async function startCareer(start = 0) {
  const c = S.career;
  if (start === 0) {
    if (c.started) return;
    Object.assign(c, { started: true, loading: true, error: null, matches: [] });
    renderCareer();
  } else {
    c.loadingMore = true;
    renderCareer();
  }
  const d = await api().career(start);
  c.loading = c.loadingMore = false;
  if (d.error) {
    if (start === 0) Object.assign(c, { started: false, error: d.error });
    else toast(`Could not load more matches: ${d.error}`, true);
  } else {
    c.me = remember(d.me);
    c.matches = c.matches.concat(d.matches);
    c.total = d.total;
    c.xp = d.xp || c.xp;
  }
  renderCareer();
}

function renderCareer() {
  const c = S.career, el = $("#career");
  if (c.error) return (el.innerHTML = `<div class="error">Could not load your matches: ${esc(c.error)}</div>`);
  if (c.loading || !c.me) return (el.innerHTML = `<div class="loading">Loading your last 20 matches...</div>`);

  const me = c.me;
  const matches = c.filter === "All" ? c.matches
    : c.filter === "Other" ? c.matches.filter((m) => !CAREER_FILTERS.includes(m.queue))
    : c.matches.filter((m) => m.queue === c.filter);
  const level = c.xp ? c.xp.level : me.level;
  let line = `${me.rank} · peak ${me.peak} · ${me.rankedGames} ranked games`;
  if (me.actWinRate != null) line += ` · this act ${me.actWinRate}% (${me.actGames} games)`;
  if (level) line = `Level ${level} · ` + line;
  const recent = c.xp ? c.xp.recent.slice(0, 10) : [];

  const agents = {};
  for (const m of matches) {
    const a = (agents[m.agent] ||= { icon: m.agentIcon, games: 0, wins: 0, kills: 0, deaths: 0 });
    a.games++; a.wins += m.won ? 1 : 0; a.kills += m.kills; a.deaths += m.deaths;
  }
  const topAgents = Object.entries(agents).sort((a, b) => b[1].games - a[1].games).slice(0, 4);

  el.innerHTML = `<div class="scroll">
    <div class="profile">
      ${img(me.rankIcon)}
      <div class="who"><h2>${esc(me.full_name)}</h2><div class="muted">${esc(line)}</div>
        ${c.xp ? `<div class="xp">${c.xp.xp} XP into this level · +${recent.reduce((a, b) => a + b, 0)} XP over the last ${recent.length} matches</div>` : ""}</div>
      ${me.smurfScore != null ? `<div class="rating"><div class="score ${scoreClass(me.smurfScore)}">${me.smurfScore}%</div><div class="score-label">SMURF RATING</div></div>` : ""}
      <button class="btn small" id="career-refresh">Refresh</button>
    </div>
    <div class="filters">${CAREER_FILTERS.map((f) => `<button data-filter="${f}" class="${f === c.filter ? "active" : ""}">${f}</button>`).join("")}</div>
    ${tiles(summarize(matches), matches.length)}
    ${topAgents.length ? `<div class="section-title">MOST PLAYED AGENTS</div><div class="agents">${topAgents.map(([name, a]) => `
      <div class="agent-card">${img(a.icon)}<div><b>${esc(name)}</b>
        <span class="sub">${a.games} games · ${Math.round((100 * a.wins) / a.games)}% WR · ${(a.kills / Math.max(a.deaths, 1)).toFixed(2)} K/D</span></div></div>`).join("")}</div>` : ""}
    <div class="section-title">MATCHES · ${matches.length} shown of ${c.total}${c.total >= 100 ? "+" : ""} · click a match for the full scoreboard</div>
    ${matches.length ? matches.map((m) => matchRow(m, me.puuid)).join("") : `<div class="empty">No matches in this mode yet</div>`}
    ${c.matches.length < c.total ? `<button class="btn load-more" id="career-more" ${c.loadingMore ? "disabled" : ""}>${c.loadingMore ? "Loading..." : "Load 10 more"}</button>` : ""}
  </div>`;
}

// ---------- pages: player history, match scoreboard ----------

async function openPlayer(puuid) {
  const page = { type: "player", player: S.known[puuid], loading: true };
  S.pages.push(page);
  renderPages();
  page.data = await api().player_details(puuid);
  page.loading = false;
  renderPages();
}

async function openMatch(matchID, puuid) {
  const page = { type: "match", player: S.known[puuid], matchID, loading: true };
  S.pages.push(page);
  renderPages();
  page.data = await api().match_details(puuid, matchID);
  page.loading = false;
  renderPages();
}

// a player clicked in a match scoreboard: the page opens at once, the profile fills in when Riot answers
async function openMatchPlayer(matchID, subject) {
  const page = { type: "player", player: null, loading: true };
  S.pages.push(page);
  renderPages();
  const p = await api().match_player(matchID, subject);
  if (p.error) {
    Object.assign(page, { loading: false, data: p });
    return renderPages();
  }
  page.player = remember(p);
  renderPages();
  page.data = await api().player_details(p.puuid);
  page.loading = false;
  if (S.pages.includes(page)) renderPages();
}

function closePage() {
  S.pages.pop();
  renderPages();
}

function renderPages() {
  const el = $("#overlay");
  const page = S.pages[S.pages.length - 1];
  if (!page) return el.classList.add("hidden");
  el.classList.remove("hidden");
  const body = page.loading ? `<div class="loading">Loading...</div>`
    : page.data.error ? `<div class="error">${esc(page.data.error)}</div>`
    : page.type === "player" ? playerPage(page) : matchPage(page);
  el.innerHTML = `
    <div class="overlay-bar"><button class="btn small" id="page-back">← Back</button>
      <span class="muted">${S.pages.length > 1 ? "Esc to go back" : "Esc to close"}</span></div>
    <div class="overlay-body">${page.type === "player" && page.player ? playerHead(page.player) : ""}${body}</div>`;
  el.querySelector(".overlay-body").scrollTop = 0;
}

function playerHead(p) {
  const reasons = (p.smurfReasons || []).join(" · ") || (p.smurfScore != null ? "No smurf signs" : "");
  return `<div class="page-head">${img(p.agentIcon)}
    <div class="grow"><h2>${esc(p.full_name)}</h2>
      <div class="muted">${p.agent && p.agent !== "Unknown agent" ? esc(p.agent.toUpperCase()) + " · " : ""}${p.level ? "Lvl " + p.level : "Lvl hidden"}</div>
      <div class="chips">${statChips(p)}</div>
      ${reasons ? `<div class="reasons">${esc(reasons)}</div>` : ""}</div>
    ${p.smurfScore != null ? `<div class="rating"><div class="score ${scoreClass(p.smurfScore)}">${p.smurfScore}%</div><div class="score-label">SMURF RATING</div></div>` : ""}</div>`;
}

function playerPage(page) {
  const d = page.data, p = page.player;
  const recent = d.xp ? d.xp.recent.slice(0, 10) : [];
  const clickable = d.matches.some((m) => m.id);
  return `
    ${tiles(d.summary, `${d.total}${d.total >= 100 ? "+" : ""}`, true)}
    ${d.xp ? `<div class="section-title teal">Account level ${d.xp.level} · ${d.xp.xp} XP into this level · +${recent.reduce((a, b) => a + b, 0)} XP over the last ${recent.length} matches</div>` : ""}
    <div class="section-title">LAST ${d.matches.length} MATCHES${clickable ? " · click a match for the full scoreboard" : ""}</div>
    ${d.matches.length ? d.matches.map((m) => matchRow(m, p.puuid)).join("") : `<div class="empty">No matches found</div>`}`;
}

function matchPage(page) {
  const b = page.data, target = page.player;
  const won = b.won, color = won === true ? "var(--green)" : won === false ? "var(--red)" : "var(--muted)";
  const teamOrder = [b.targetTeam, ...Object.keys(b.teams).filter((t) => t !== b.targetTeam)];

  // fixed column widths so the ALLIES and ENEMIES tables line up
  const board = (players) => `<table class="board">
    <colgroup><col style="width:27%"><col style="width:14%"><col span="7"><col style="width:14%"></colgroup>
    <tr><th>PLAYER</th><th class="left">RANK</th><th>ACS</th><th>K</th><th>D</th><th>A</th><th>ADR</th><th>HS %</th><th>FB</th><th class="left">PARTY</th></tr>
    ${players.map((p) => {
      const name = p.isTarget ? target.full_name : p.name || "Privacy mode";
      const party = p.party ? `<span class="party-dot" style="background:${PARTY_COLORS[(p.party - 1) % PARTY_COLORS.length]}"></span>Party ${p.party} (${p.partySize})` : `<span class="muted">Solo</span>`;
      return `<tr class="${p.isTarget ? "target" : ""}" data-mplayer="${esc(p.subject)}" data-mmatch="${esc(page.matchID)}" title="Open this player's profile">
        <td><div class="who-cell">${img(p.agentIcon)}<div>${esc(name)}<div class="agent">${esc(p.agent)}</div></div></div></td>
        <td class="left"><div class="rank-cell">${p.tier ? img(p.tierIcon) + esc(p.tier) : "Unranked"}</div></td>
        <td>${p.acs}</td><td>${p.kills}</td><td>${p.deaths}</td><td>${p.assists}</td><td>${p.adr}</td><td>${pct(p.hs)}</td><td>${p.firstBloods}</td>
        <td class="left">${party}</td></tr>`;
    }).join("")}</table>`;

  const rounds = `<table class="board">
    <colgroup><col style="width:6%"><col style="width:12%"><col span="5"><col style="width:20%"></colgroup>
    <tr><th>RND</th><th>RESULT</th><th>KILLS</th><th>DAMAGE</th><th>WEAPON</th><th>LOADOUT</th><th>SPENT</th><th class="left"></th></tr>
    ${b.myRounds.map((r) => `<tr><td>${r.num}</td>
      <td class="${r.won ? "green" : "red"}">${r.won ? "WIN" : "LOSS"} · ${ROUND_RESULTS[r.result] || "?"}</td>
      <td class="${r.kills >= 3 ? "red" : ""}">${r.kills}</td><td>${r.damage}</td><td>${esc(r.weapon)}</td><td>${r.loadout}</td><td>${r.spent}</td>
      <td class="left teal">${[r.firstBlood && "First blood", !r.died && "Survived"].filter(Boolean).join(" · ")}</td></tr>`).join("")}</table>`;

  return `
    <div class="match-head"><span class="bar" style="background:${color}"></span>
      <div><h2>${esc(b.map.toUpperCase())}</h2><div class="muted">${esc(b.queue)} · ${fmtDate(b.start, true)} · ${Math.round(b.length / 60000)} min</div></div>
      ${b.scoreLine ? `<div class="final" style="color:${color}"><b>${b.scoreLine.replace("-", " : ")}</b>${won ? "VICTORY" : "DEFEAT"}</div>` : ""}</div>
    ${b.timeline.length ? `<div class="section-title">ROUNDS · E elimination · D defuse · B spike detonated · T time out</div>
      <div class="rounds">${b.timeline.map((r) => `<div class="round ${r.won ? "w" : "l"}"><span>${r.num}</span><b>${ROUND_RESULTS[r.result] || "?"}</b></div>`).join("")}</div>` : ""}
    ${teamOrder.map((team) => {
      const players = b.players.filter((p) => p.team === team);
      if (!players.length) return "";
      return `<div class="section-title">${team === b.targetTeam ? "ALLIES" : "ENEMIES"} · ${b.teams[team]?.roundsWon ?? "?"} rounds</div>${board(players)}`;
    }).join("")}
    ${b.myRounds.length ? `<div class="section-title">${esc(target.full_name.toUpperCase())} · ROUND BY ROUND</div>${rounds}` : ""}`;
}

// ---------- user actions ----------

function showTab(tab) {
  S.tab = tab;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  $("#live").classList.toggle("hidden", tab !== "live");
  $("#career").classList.toggle("hidden", tab !== "career");
  $("#live-controls").classList.toggle("hidden", tab !== "live");
  if (tab === "career") startCareer();
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = Object.assign(document.createElement("textarea"), { value: text });
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  toast(`Copied ${text}`);
}

document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-copy],[data-match],[data-player],[data-mplayer],[data-filter],[data-tab],#career-refresh,#career-more,#page-back");
  if (!t) return;
  if (t.dataset.copy) return copy(t.dataset.copy);
  if (t.dataset.mplayer) return openMatchPlayer(t.dataset.mmatch, t.dataset.mplayer);
  if (t.dataset.match) return openMatch(t.dataset.match, t.dataset.for);
  if (t.dataset.player) return openPlayer(t.dataset.player);
  if (t.dataset.filter) { S.career.filter = t.dataset.filter; return renderCareer(); }
  if (t.dataset.tab) return showTab(t.dataset.tab);
  if (t.id === "career-refresh") {
    api().career_reload();
    S.career.started = false;
    return startCareer();
  }
  if (t.id === "career-more") return startCareer(S.career.matches.length);
  if (t.id === "page-back") return closePage();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && S.pages.length) closePage();
});

$("#only-hidden").addEventListener("change", (e) => {
  S.onlyHidden = e.target.checked;
  renderLive();
});

$("#check-now").addEventListener("click", () => api().check_now());

$("#search").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("#search-input"), button = $("#search button");
  const query = input.value.trim();
  if (!query.includes("#")) return toast("Use the Name#TAG format (ex: TenZ#0001)", true);
  button.disabled = true;
  button.textContent = "...";
  const p = await api().search(query);
  button.disabled = false;
  button.textContent = "SEARCH";
  if (p.error) return toast(`Search failed: ${p.error}`, true);
  remember({ ...p, agent: p.agent || "Profile" });
  openPlayer(p.puuid);
});

$("#region-save").addEventListener("click", async () => {
  await api().set_region($("#region-select").value);
  $("#region").classList.add("hidden");
});

// ---------- start ----------

renderLive();
window.addEventListener("pywebviewready", async () => {
  const init = await api().init();
  if (init.needsRegion) $("#region").classList.remove("hidden");
  api().ready();
});
