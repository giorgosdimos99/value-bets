(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const view = $("#view");
  const state = { tab: "value", comp: "ALL", day: "ALL", data: null, history: null };
  const BOOKS = ["Stoiximan", "Superbet", "Άλλη"];

  // ---------- βοηθητικά ----------
  const pct = p => (p * 100).toFixed(0) + "%";
  const f2 = x => (x == null ? "—" : Number(x).toFixed(2));
  const evTxt = ev => (ev == null ? "—" : (ev > 0 ? "+" : "") + (ev * 100).toFixed(1) + "%");
  const evCls = ev => (ev == null ? "" : ev > 0 ? "ev-pos" : "ev-neg");
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const dt = iso => new Date(iso).toLocaleString("el-GR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const COMP = { PL: "Premier League", CL: "Champions League", GR: "Super League", EL: "EuroLeague" };
  const isBasket = m => m.sport === "basketball";
  const srcTxt = c => !c ? "" : c[0] === "m" ? `διάμεσος ${c.slice(1)} εταιρειών` : c === "gc" ? "εκτίμηση από γκανιότ (χωρίς δεδομένα αγοράς)" : "εκτίμηση από γκανιότ";
  const STAGE = { LEAGUE_STAGE: "Φάση πρωταθλήματος", PLAYOFFS: "Playoffs", LAST_16: "16 ομάδες", QUARTER_FINALS: "Προημιτελικά", SEMI_FINALS: "Ημιτελικά", FINAL: "Τελικός" };
  const formHtml = f => `<span class="form">${(f || "").split("").map(c => `<span class="${c}">${{ W: "Ν", D: "Ι", L: "Η" }[c]}</span>`).join("")}</span>`;

  const store = {
    get(k, def) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : def; } catch { return def; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* ιδιωτική περιήγηση */ } },
  };

  // ---------- ημέρες ----------
  const dayKey = iso => { const d = new Date(iso); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
  function dayLabel(key) {
    const today = dayKey(new Date().toISOString());
    const tmr = dayKey(new Date(Date.now() + 864e5).toISOString());
    const d = new Date(key + "T12:00:00");
    const base = d.toLocaleDateString("el-GR", { weekday: "long", day: "numeric", month: "long" });
    return key === today ? `Σήμερα · ${base}` : key === tmr ? `Αύριο · ${base}` : base.charAt(0).toUpperCase() + base.slice(1);
  }
  function chipLabel(key) {
    const today = dayKey(new Date().toISOString());
    const tmr = dayKey(new Date(Date.now() + 864e5).toISOString());
    if (key === today) return "Σήμερα";
    if (key === tmr) return "Αύριο";
    return new Date(key + "T12:00:00").toLocaleDateString("el-GR", { weekday: "short", day: "numeric", month: "short" });
  }
  const groupByDay = list => list.reduce((acc, x) => { const k = dayKey(x.date); (acc[k] = acc[k] || []).push(x); return acc; }, {});
  function dayChips(all) {
    const days = Object.keys(groupByDay(all)).sort();
    if (state.day !== "ALL" && !days.includes(state.day)) state.day = "ALL";
    return `<div class="day-chips">${["ALL", ...days].map(d => `<button data-day="${d}" class="${state.day === d ? "active" : ""}">${d === "ALL" ? "Όλες" : chipLabel(d)}<small>${d === "ALL" ? all.length : groupByDay(all)[d].length}</small></button>`).join("")}</div>`;
  }

  function matches(byDay = false) {
    if (!state.data) return [];
    return Object.entries(state.data.competitions)
      .filter(([c]) => state.comp === "ALL" || state.comp === c)
      .flatMap(([, v]) => v.matches)
      .filter(m => !byDay || state.day === "ALL" || dayKey(m.date) === state.day)
      .sort((a, b) => a.date.localeCompare(b.date));
  }
  const findMatch = id => Object.values(state.data.competitions).flatMap(c => c.matches).find(m => String(m.id) === String(id));

  // ---------- φόρτωση ----------
  async function load() {
    try {
      const r = await fetch("data/data.json?ts=" + Date.now());
      state.data = await r.json();
    } catch {
      state.data = { competitions: {}, updated: null };
    }
    try { state.history = await (await fetch("data/history.json?ts=" + Date.now())).json(); } catch { state.history = { picks: [] }; }
    try { state.backtest = await (await fetch("data/backtest.json?ts=" + Date.now())).json(); } catch { state.backtest = null; }
    try { state.research = await (await fetch("data/research.json?ts=" + Date.now())).json(); } catch { state.research = null; }
    const comps = Object.entries(state.data.competitions || {}).filter(([, c]) => c.matches?.length);
    comps.forEach(([cid, c]) => { COMP[cid] = c.name; });
    if (!comps.some(([cid]) => cid === state.comp)) state.comp = "ALL";
    const fb = comps.filter(([, c]) => c.sport !== "basketball"), bb = comps.filter(([, c]) => c.sport === "basketball");
    $("#compFilter").innerHTML = `<button data-comp="ALL">Όλα</button>` +
      [...fb, ...bb].map(([cid, c]) => `<button data-comp="${cid}">${c.sport === "basketball" ? "🏀 " : ""}${esc(c.name)} <small>${c.matches.length}</small></button>`).join("");
    syncTabs();
    $("#updated").innerHTML = state.data.updated
      ? `Ενημέρωση<br>${new Date(state.data.updated).toLocaleString("el-GR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`
      : "Χωρίς δεδομένα";
    render();
  }

  // ---------- καρτέλες ----------
  function render() {
    $("#compFilter").style.display = ["bets"].includes(state.tab) ? "none" : "flex";
    ({ value: renderValue, matches: renderMatches, teams: renderTeams, bets: renderBets, model: renderModel })[state.tab]();
    if (state.data?.demo && state.tab !== "bets") view.insertAdjacentHTML("afterbegin", `<div class="note" style="border-color:var(--amber);color:var(--amber)">ΔΕΙΓΜΑ: φανταστικοί αγώνες και αποδόσεις για δοκιμή της εμφάνισης.</div>`);
  }

  function pickCard(m, s, kind) {
    return `<div class="card click pick" data-match="${m.id}">
      <div><div class="sel">${esc(s.label)} <span class="pill ${kind}">${kind === "value" ? "VALUE" : "ΛΟΓΙΚΗ"}</span></div>
      <div class="match">${esc(m.home)} – ${esc(m.away)} · ${esc(s.group)}</div></div>
      <div><div class="odds">${s.best ? f2(s.best) : f2(s.fair)}</div><div class="book">${s.best ? esc(s.book) : "δίκαιη απόδοση"}</div></div>
      <div class="meta"><span>Πιθανότητα <b>${pct(s.p)}</b></span><span>Δίκαιη <b>${f2(s.fair)}</b></span>
      ${s.ev != null ? `<span>EV <b class="${evCls(s.ev)}">${evTxt(s.ev)}</b></span>` : ""}
      <span>${COMP[m.comp]} · ${dt(m.date)}</span></div></div>`;
  }

  function slipCard(sl, kind, day) {
    return `<div class="card slip ${kind}">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px"><span class="pill ${kind === "simple" ? "value" : "solid"}">${kind === "simple" ? "ΑΠΛΟ" : "ΑΚΡΑΙΟ"}</span><span style="color:var(--muted);font-size:12px">${sl.legs.length} επιλογές</span></div>
      ${sl.legs.map(l => `<div class="leg" data-match="${l.match_id}"><div><b>${esc(l.label)}</b><div class="match">${esc(l.home)} – ${esc(l.away)} · ${COMP[l.comp] || ""} · ${new Date(l.date).toLocaleTimeString("el-GR", { hour: "2-digit", minute: "2-digit" })}</div></div>
        <div class="lo"><b>${f2(l.est)}</b><span>${pct(l.p)}</span></div></div>`).join("")}
      <div class="slip-foot"><div><span>Απόδοση</span><b>${f2(sl.odds)}</b></div><div><span>Πιθανότητα</span><b>${pct(sl.p)}</b></div><div><span>EV</span><b class="${evCls(sl.ev)}">${evTxt(sl.ev)}</b></div></div>
      <button class="btn ghost" style="margin-top:10px;width:100%" data-slipbet="${day}|${kind}">+ Στα στοιχήματά μου</button></div>`;
  }


  // ---- Στατιστικά αγώνα: ίδιοι υπολογισμοί με το engine/stats.py (Negative Binomial) ----
  const LGN = { E0: "Premier League", SP1: "La Liga", D1: "Bundesliga", I1: "Serie A", F1: "Ligue 1", P1: "Primeira Liga", N1: "Eredivisie", B1: "Βέλγιο", T1: "Τουρκία", G1: "Ελλάδα", SC0: "Σκωτία", E1: "Championship", E2: "League One", E3: "League Two", EC: "National League", D2: "2. Bundesliga", I2: "Serie B", SP2: "Segunda", F2: "Ligue 2", SC1: "Σκωτία 2", SC2: "Σκωτία 3", SC3: "Σκωτία 4" };
  const STATN = { co: "Κόρνερ", sh: "Σουτ", st: "Σουτ στην εστία", fo: "Φάουλ", ca: "Κάρτες", sv: "Αποκρούσεις" };
  const STAT_ICON = { co: "🚩", sh: "🎯", st: "🥅", fo: "🦵", ca: "🟨", sv: "🧤" };
  const PROP_RATIO = 1.045;
  function nb(mu, phi, kmax) {
    mu = Math.max(mu, 1e-6); kmax = kmax || Math.floor(mu * 3 + 25);
    const out = [];
    if (phi <= 1e-6) { let p = Math.exp(-mu); for (let k = 0; k <= kmax; k++) { out.push(p); p *= mu / (k + 1); } return out; }
    const r = 1 / phi, q = mu / (r + mu);
    let p = Math.exp(r * Math.log(r / (r + mu)));
    for (let k = 0; k <= kmax; k++) { out.push(p); p *= (k + r) / (k + 1) * q; }
    return out;
  }
  const pOver = (d, L) => Math.max(0, 1 - d.slice(0, Math.floor(L) + 1).reduce((a, b) => a + b, 0));
  const lines = (mu, n) => { const b = Math.floor(mu) + 0.5, o = []; for (let i = -n; i <= n; i++) if (b + i > 0) o.push(b + i); return o; };
  function statSel(group, key, side, label, p) {
    const fair = p > 0.001 ? 1 / p : null;
    const est = fair ? Math.max(Math.round((fair / PROP_RATIO) * 100) / 100, 1.01) : null;
    return { group, key, side, label, p, fair, est, est_src: "gc", est_ev: est ? p * est - 1 : null, pp: 0 };
  }
  function cmp3(dh, da) {
    let p1 = 0, px = 0, cum = 0;
    for (let i = 0; i < dh.length; i++) { const ai = i < da.length ? da[i] : 0; p1 += dh[i] * cum; px += dh[i] * ai; cum += ai; }
    return [p1, px, Math.max(1 - p1 - px, 0)];
  }
  function statSels(m) {
    const sx = m.stx;
    if (!sx) return [];
    const out = [];
    for (const [k, [mh, ma, mT0]] of Object.entries(sx.m || {})) {
      const name = STATN[k], mT = mT0 ?? mh + ma;
      const [pt, pT] = (sx.disp || {})[k] || [0.05, 0.03];
      const tot = nb(mT, pT);
      lines(mT, 2).forEach(L => { const po = pOver(tot, L); out.push(statSel(`${name}: σύνολο`, `S:${k}:T:${L}`, "Over", `Over ${L}`, po), statSel(`${name}: σύνολο`, `S:${k}:T:${L}`, "Under", `Under ${L}`, 1 - po)); });
      const dh = nb(mh, pt), da = nb(ma, pt);
      [["H", mh, dh, m.home], ["A", ma, da, m.away]].forEach(([side, mu, d, team]) => lines(mu, 1).forEach(L => {
        const po = pOver(d, L), g = `${name}: ${team}`;
        out.push(statSel(g, `S:${k}:${side}:${L}`, "Over", `${team} Over ${L}`, po), statSel(g, `S:${k}:${side}:${L}`, "Under", `${team} Under ${L}`, 1 - po));
      }));
      const [p1, px, p2] = cmp3(dh, da), g = `${name}: ποιος περισσότερα`;
      out.push(statSel(g, `S:${k}:1X2`, "1", `1 · ${m.home}`, p1), statSel(g, `S:${k}:1X2`, "X", "X · ίσα", px), statSel(g, `S:${k}:1X2`, "2", `2 · ${m.away}`, p2));
    }
    if (sx.ht) {
      const [hh, ha] = sx.ht, tot = nb(hh + ha, 0, 15), g = "Α΄ ημίχρονο";
      [0.5, 1.5, 2.5].forEach(L => { const po = pOver(tot, L); out.push(statSel(g, `H1:OU${L}`, "Over", `Α΄ ημίχρονο Over ${L}`, po), statSel(g, `H1:OU${L}`, "Under", `Α΄ ημίχρονο Under ${L}`, 1 - po)); });
      const [p1, px, p2] = cmp3(nb(hh, 0, 12), nb(ha, 0, 12));
      out.push(statSel(g, "H1:1X2", "1", "Ημίχρονο 1", p1), statSel(g, "H1:1X2", "X", "Ημίχρονο X", px), statSel(g, "H1:1X2", "2", "Ημίχρονο 2", p2));
    }
    return out.filter(s => s.fair && s.p >= 0.03 && s.p <= 0.97);
  }
  const FIT = { 1: ["value", "✓ Βολεύει"], 0: ["muted", "Ουδέτερο"], "-1": ["warn", "✗ Δεν βολεύει"] };
  const fitPill = t => (t.fit === undefined || t.fit === null ? "" : `<span class="pill ${FIT[t.fit][0]}">${FIT[t.fit][1]}</span>`);
  const fitLine = t => (t.fit_text ? `<div class="fitline"><b>Αντίπαλος & σενάριο:</b> ${esc(t.fit_text)}</div>` : "");
  function edgeCard(m, e, withMatch) {
    const RSt = state.research?.stats?.[e.stat];
    const tests = RSt?.tests ? Object.entries(RSt.tests).map(([t, v]) => { const x = e.scope === "T" ? v.edge_total : v.edge_team; return x?.n ? `20${t.slice(0, 2)}/${t.slice(2)}: ${pct(x.model)}→<b>${pct(x.hit)}</b>` : ""; }).filter(Boolean).join(" · ") : "";
    return `<div class="card ${withMatch ? "click " : ""}pick opp" data-match="${m.id}">
      <div><div class="sel">${STAT_ICON[e.stat] || ""} ${esc(e.label)} <span class="pill hot">ΑΠΟΚΛΙΣΗ</span> ${fitPill(e)}</div>
      ${withMatch ? `<div class="match">${esc(m.home)} – ${esc(m.away)} · ${esc(COMP[m.comp] || "")} · ${dt(m.date)}</div>` : ""}</div>
      <div><div class="odds">${pct(e.p)}</div><div class="book">μ.ό. λέει ${pct(e.p_avg)}</div></div>
      <div class="pbar ${e.p < 0.6 ? "mid" : ""}"><i style="width:${Math.round(e.p * 100)}%"></i></div>
      <div class="meta"><span>Αναμενόμενα <b>${e.exp}</b> (μ.ό. ${e.avg})</span><span>Δίκαιη <b>${f2(e.fair)}</b></span><span>Αξίζει από <b class="edge">${f2(e.min_odds)}</b></span></div>
      ${fitLine(e)}
      <div class="evidence">Η γραμμή ${String(e.label).split(" ").pop()} είναι η «συνηθισμένη» του πρωταθλήματος${e.scope === "T" ? "" : " για μία ομάδα"}, αλλά με αυτόν τον αντίπαλο η πρόβλεψη απέχει πολύ. ${e.n ? `Έρευνα, ${e.n.toLocaleString("el-GR")} τέτοιες περιπτώσεις: μοντέλο ${pct(e.r_model)}, μέσος όρος ${pct(e.r_avg)}, έγινε <b>${pct(e.hit)}</b>.` : ""}${tests ? ` Ανά σεζόν ελέγχου (πρόβλεψη→έγινε): ${tests}.` : ""} Παίξ' το μόνο με απόδοση τουλάχιστον ${f2(e.min_odds)}.</div></div>`;
  }
  function diffHtml(m) {
    const D = m.difficulty;
    if (!D) return "";
    const team = (t, name) => `<div class="diff-t"><b>${esc(name)}</b><span class="pill ${/εύκολο/.test(t.level) ? "value" : /δύσκολο/.test(t.level) ? "warn" : "muted"}">${esc(t.level)}</span>
      <small>${t.rank ? `${t.rank}η δύναμη από ${t.of}${t.league ? " (" + esc(t.league) + ")" : ""}` : ""}${t.form ? ` · φόρμα ${formHtml(t.form)}` : ""}</small></div>`;
    const [p1, px, p2] = D.p;
    return `<h2>Δυσκολία αγώνα</h2><div class="card"><div class="diff">${team(D.home, m.home)}${team(D.away, m.away)}</div>
      <div class="tri"><i style="width:${p1 * 100}%">1 · ${pct(p1)}</i><i style="width:${px * 100}%">X · ${pct(px)}</i><i style="width:${p2 * 100}%">2 · ${pct(p2)}</i></div>
      <div style="color:var(--muted);font-size:12px;margin-top:6px">Πιθανότητες από την αγορά (όπου υπάρχουν αποδόσεις) αλλιώς από το μοντέλο. Το πόσο φαβορί είναι κάθε ομάδα αλλάζει και τα στατιστικά: το φαβορί κάνει περισσότερα σουτ/κόρνερ, το αουτσάιντερ περισσότερα φάουλ και αποκρούσεις.</div></div>`;
  }

  const LVL = { "πολύ πιθανό": "value", "πιθανό": "solid", "μέτριο": "muted" };
  function predCard(m, t) {
    return `<div class="card click pick" data-match="${m.id}">
      <div><div class="sel">${esc(t.label)} <span class="pill ${LVL[t.level] || "muted"}">${esc(t.level || "")}</span></div>
      <div class="match">${isBasket(m) ? "🏀 " : ""}${esc(m.home)} – ${esc(m.away)} · ${esc(t.group)}</div></div>
      <div><div class="odds">${pct(t.p)}</div><div class="book">εκτ. απόδοση ${f2(t.est)}</div></div>
      <div class="pbar ${t.p < 0.6 ? "mid" : ""}"><i style="width:${Math.round(t.p * 100)}%"></i></div>
      <div class="meta"><span class="why">${esc(t.why || "")}</span></div>
      ${m.difficulty ? `<div class="meta"><span>Δυσκολία: ${esc(m.home)} <b>${esc(m.difficulty.home.level)}</b>${m.difficulty.home.rank ? ` (${m.difficulty.home.rank}η)` : ""} · ${esc(m.away)} <b>${esc(m.difficulty.away.level)}</b>${m.difficulty.away.rank ? ` (${m.difficulty.away.rank}η)` : ""}</span></div>` : ""}
      <div class="meta"><span>Δίκαιη <b>${f2(t.fair)}</b></span><span>${COMP[m.comp] || m.comp} · ${dt(m.date)}</span>${m.confidence !== "υψηλή" ? `<span>αξιοπιστία ${m.confidence}</span>` : ""}</div></div>`;
  }

  function renderValue() {
    const all = matches();
    const ms = matches(true);
    let h = "";
    if (!all.length) {
      view.innerHTML = `<div class="empty"><b>Δεν υπάρχουν αγώνες ακόμα</b>Μόλις βγει το επόμενο πρόγραμμα θα εμφανιστούν εδώ.</div>`;
      return;
    }
    h += dayChips(all);
    // Ευκαιρίες: (α) εταιρεία δίνει πάνω από τη δίκαιη τιμή της αγοράς, (β) μοτίβα της έρευνας
    const R = state.research;
    const gap = R?.gap?.find(g => g.evmin === 0.03) || R?.gap?.[0];
    const opps = [
      ...ms.flatMap(m => m.values.map(s => ({ m, kind: "gap", label: s.label, group: s.group, p: s.p, odds: s.best, book: s.book, fair: s.fair, ev: s.ev, date: m.date }))),
      ...ms.flatMap(m => (m.patterns || []).map(pt => ({ m, kind: "pattern", label: pt.label, group: "Μοτίβο έρευνας", p: pt.p, odds: pt.odds, fair: pt.p ? 1 / pt.p : null, ev: pt.p * pt.odds - 1, text: pt.text, date: m.date }))),
    ].sort((a, b) => (b.p * b.odds) - (a.p * a.odds));
    h += `<div class="hero"><h1>Ευκαιρίες</h1><p>Εκεί που η απόδοση είναι <b>μεγαλύτερη απ' όσο δικαιολογεί η πιθανότητα</b>. Η πιθανότητα βγαίνει από την αγορά (power, η πιο ακριβής μέθοδος στην έρευνα), όχι από «αίσθηση».</p>
      ${gap ? `<div class="stats"><div><b>${(R.matches || 0).toLocaleString("el-GR")}</b><span>αγώνες έρευνας</span></div><div><b class="ev-pos">${evTxt(gap.disc.clv)}</b><span>CLV 2023–25</span></div><div><b class="ev-pos">${evTxt(gap.test.clv)}</b><span>CLV 2025/26 (έλεγχος)</span></div></div>` : ""}</div>`;
    h += opps.length ? `<div class="grid">${opps.slice(0, 12).map(o => `<div class="card click pick opp" data-match="${o.m.id}">
        <div><div class="sel">${esc(o.label)} <span class="pill ${o.kind === "gap" ? "hot" : "solid"}">${o.kind === "gap" ? "ΚΕΝΟ ΑΓΟΡΑΣ" : "ΜΟΤΙΒΟ"}</span></div>
        <div class="match">${isBasket(o.m) ? "🏀 " : ""}${esc(o.m.home)} – ${esc(o.m.away)} · ${esc(COMP[o.m.comp] || "")} · ${dt(o.m.date)}</div></div>
        <div><div class="odds">${f2(o.odds)}</div><div class="book">${o.book ? esc(o.book) : "εκτ. απόδοση"}</div></div>
        <div class="pbar ${o.p < 0.6 ? "mid" : ""}"><i style="width:${Math.round(o.p * 100)}%"></i></div>
        <div class="meta"><span>Πιθανότητα <b>${pct(o.p)}</b></span><span>Δίκαιη <b>${f2(o.fair)}</b></span><span>Πλεονέκτημα <b class="edge">${evTxt(o.ev)}</b></span></div>
        <div class="evidence">${o.kind === "gap" ? `Η ${esc(o.book || "εταιρεία")} δίνει πάνω από τη δίκαιη τιμή της αγοράς. Στην έρευνα, τέτοιες τιμές κέρδιζαν σταθερά την τελική απόδοση (θετικό CLV). Δες αν η Stoiximan/Superbet δίνει κάτι κοντά.` : esc(o.text)}</div></div>`).join("")}</div>`
      : `<div class="note">Δεν υπάρχει αυτή τη στιγμή απόδοση πάνω από τη δίκαιη τιμή. Αυτό είναι φυσιολογικό: οι αγορές είναι σωστές τις περισσότερες φορές. Οι πιθανότερες προβλέψεις παρακάτω έχουν τις πιο «τίμιες» τιμές (βλ. Μοντέλο → Έρευνα).</div>`;
    const edges = ms.flatMap(m => (m.stat_edges || []).map(e => ({ m, e }))).sort((a, b) => ((b.e.fit ?? 0) - (a.e.fit ?? 0)) || ((b.e.p - b.e.p_avg) - (a.e.p - a.e.p_avg)));
    const SR = R?.stats || {};
    const okStats = Object.values(SR).filter(s => s.validated).map(s => s.name);
    h += `<h2>Στατιστικά: εκεί που ο μέσος όρος κάνει λάθος</h2><div class="note">Κόρνερ, σουτ, σουτ στην εστία, φάουλ, κάρτες, αποκρούσεις. Οι στοιχηματικές βάζουν αυτές τις γραμμές κυρίως με τον <b>μέσο όρο του πρωταθλήματος</b> και έχουν μεγαλύτερο γκανιότ. Εδώ είναι οι αγώνες όπου, <b>με αυτόν τον αντίπαλο</b> και το σενάριο του αγώνα (ποιος είναι φαβορί), η πρόβλεψη απέχει πολύ από τον μέσο όρο. Πρώτα όσα «βολεύει» ο αντίπαλος. ${okStats.length ? `Επιβεβαιωμένο στην έρευνα για: <b>${okStats.join(", ")}</b>.` : ""} Δεν έχουμε δωρεάν αποδόσεις γι' αυτές τις αγορές: έλεγξε ότι η απόδοση είναι <b>πάνω από το «αξίζει από»</b>.</div>`;
    h += edges.length ? `<div class="grid">${edges.slice(0, 12).map(({ m, e }) => edgeCard(m, e, true)).join("")}</div>`
      : `<div class="note">Καμία μεγάλη απόκλιση στους αγώνες που φαίνονται τώρα.</div>`;
    const slips = (state.data.slips || []).filter(s => state.day === "ALL" || s.day === state.day);
    if (slips.length && state.comp === "ALL") {
      h += `<h2>Δελτία ημέρας</h2><div class="note">Μόνο αγώνες της ίδιας μέρας. Ο <b>πιθανότερος</b> συνδυασμός με βάση τα στατιστικά που φτάνει <b>Απλό</b>: απόδοση 5+, <b>Ακραίο</b>: απόδοση 20+. Οι αποδόσεις είναι <b>εκτίμηση</b> για Stoiximan/Superbet· έλεγξε την πραγματική πριν παίξεις.</div>`;
      h += slips.map(d => `<h3 class="day-sub">${dayLabel(d.day)} <span style="color:var(--muted);font-weight:500">· ${d.matches} αγώνες</span></h3>
        <div class="grid">${["simple", "extreme"].map(k => d[k] ? slipCard(d[k], k, d.day) : "").join("")}</div>`).join("");
    }
    // πιθανότερες προβλέψεις: η κύρια πρόβλεψη κάθε αγώνα, ταξινομημένες από την πιο πιθανή
    const preds = ms.filter(m => m.top && m.top.length).map(m => ({ m, t: m.top[0], date: m.date }));
    const pg = groupByDay(preds);
    h += `<h2>Πιθανότερες προβλέψεις</h2><div class="note">Για κάθε αγώνα η επιλογή με τη <b>μεγαλύτερη πιθανότητα</b> από τα στατιστικά (μοντέλο + αγορά), ανάμεσα σε αγορές που δίνουν οι στοιχηματικές, με απόδοση τουλάχιστον 1.30. Πάτα για ανάλυση.</div>`;
    h += Object.keys(pg).sort().map(k => {
      const list = pg[k].sort((a, b) => b.t.p - a.t.p);
      return `<h3 class="day-sub">${dayLabel(k)} <span style="color:var(--muted);font-weight:500">· ${list.length} αγώνες</span></h3><div class="grid">${list.map(({ m, t }) => predCard(m, t)).join("")}</div>`;
    }).join("");
    view.innerHTML = h;
  }

  function matchCard(m) {
    const bk = isBasket(m);
    const p = Object.fromEntries(m.markets.filter(s => s.key === (bk ? "ML" : "1X2")).map(s => [bk ? { H: "1", A: "2" }[s.side] : s.side, s]));
    const crest = u => (u ? `<img src="${esc(u)}" alt="" loading="lazy">` : "");
    const unit = bk ? "πόντοι" : "xG";
    const fmtx = x => (bk ? Number(x).toFixed(1) : f2(x));
    return `<div class="card click" data-match="${m.id}">
      <div class="match-head"><span>${bk ? "🏀 " : ""}${COMP[m.comp]}${m.stage && m.comp === "CL" ? " · " + (STAGE[m.stage] || "") : bk && m.stage ? " · " + esc(m.stage) : ""}</span><span>${dt(m.date)}</span></div>
      <div class="teams">
        <div class="team">${crest(m.home_crest)}${esc(m.home)}<span class="xg">${unit} ${fmtx(m.xg[0])}</span></div>
        <div class="team">${crest(m.away_crest)}${esc(m.away)}<span class="xg">${unit} ${fmtx(m.xg[1])}</span></div>
      </div>
      <div class="probs" ${bk ? 'style="grid-template-columns:repeat(3,1fr)"' : ""}>${(bk ? ["1", "2"] : ["1", "X", "2"]).map(k => `<div class="prob"><b>${pct(p[k].p)}</b><span>${k} · ${f2(p[k].fair)}</span></div>`).join("")}
      ${bk ? `<div class="prob"><b>${(m.xg[0] + m.xg[1]).toFixed(1)}</b><span>σύνολο πόντων</span></div>` : ""}</div>
      <div class="tags">${m.values.length ? `<span class="pill value">${m.values.length} value</span>` : ""}
      ${m.has_odds ? "" : `<span class="pill muted">χωρίς αποδόσεις</span>`}
      ${m.confidence !== "υψηλή" ? `<span class="pill muted">αξιοπιστία: ${m.confidence}</span>` : ""}</div></div>`;
  }

  function renderMatches() {
    const all = matches();
    if (!all.length) { view.innerHTML = `<div class="empty"><b>Κανένας αγώνας</b>Δεν υπάρχουν προγραμματισμένοι αγώνες τις επόμενες μέρες.</div>`; return; }
    const groups = groupByDay(matches(true));
    view.innerHTML = dayChips(all) + Object.keys(groups).sort().map(k =>
      `<h2 class="day-head">${dayLabel(k)} <span>${groups[k].length} αγώνες</span></h2><div class="grid">${groups[k].map(matchCard).join("")}</div>`).join("");
  }

  function renderTeams() {
    const comps = Object.entries(state.data.competitions).filter(([c]) => state.comp === "ALL" || state.comp === c);
    let h = "";
    for (const [cid, c] of comps) {
      h += `<h2>${c.sport === "basketball" ? "🏀 " : ""}${c.name}</h2>`;
      if (c.sport === "basketball" && c.teams?.length) {
        h += `<div class="table-wrap"><table><thead><tr><th>Ομάδα</th><th>Φόρμα</th><th class="num">Πόντοι+</th><th class="num">Πόντοι−</th><th class="num">Διαφ.</th><th class="num">Επίθ.</th><th class="num">Άμυνα</th></tr></thead><tbody>`;
        h += c.teams.map(t => `<tr><td><b>${esc(t.team)}</b></td><td>${formHtml(t.form)}</td><td class="num">${t.ppg ?? "—"}</td><td class="num">${t.oppg ?? "—"}</td><td class="num ${t.ppg - t.oppg >= 0 ? "ev-pos" : "ev-neg"}">${t.ppg != null ? (t.ppg - t.oppg > 0 ? "+" : "") + (t.ppg - t.oppg).toFixed(1) : "—"}</td><td class="num">${f2(t.att)}</td><td class="num">${f2(t.def)}</td></tr>`).join("");
        h += `</tbody></table></div><div class="note" style="margin-top:8px">Μέσοι όροι φετινής σεζόν. Επίθ./Άμυνα: δείκτες ισχύος (τρέχουσα + προηγούμενη σεζόν, 1 = μέσος όρος· άμυνα κάτω από 1 = καλύτερη).</div>`;
      } else if (c.teams && c.teams.length) {
        h += `<div class="table-wrap"><table><thead><tr><th>Ομάδα</th><th>Φόρμα</th><th class="num">xG+</th><th class="num">xG−</th><th class="num">Γκολ+</th><th class="num">Γκολ−</th><th class="num">G/G</th><th class="num">O2.5</th><th class="num">Κόρνερ</th><th class="num">Κάρτες</th><th class="num">Επίθ.</th><th class="num">Άμυνα</th></tr></thead><tbody>`;
        h += c.teams.map(t => `<tr><td><b>${esc(t.team)}</b></td><td>${formHtml(t.form)}</td><td class="num">${f2(t.xgf)}</td><td class="num">${f2(t.xga)}</td><td class="num">${f2(t.gf)}</td><td class="num">${f2(t.ga)}</td><td class="num">${pct(t.btts)}</td><td class="num">${pct(t.o25)}</td><td class="num">${f2(t.cf)}</td><td class="num">${f2(t.cards)}</td><td class="num">${f2(t.att)}</td><td class="num">${f2(t.def)}</td></tr>`).join("");
        h += `</tbody></table></div><div class="note" style="margin-top:8px">Μέσοι όροι ανά αγώνα στη φετινή σεζόν. Επίθ./Άμυνα: δείκτες ισχύος του μοντέλου (1 = μέσος όρος· άμυνα κάτω από 1 = καλύτερη).</div>`;
      }
      for (const st of c.standings || []) {
        h += `<div class="table-wrap" style="margin-top:8px"><table><thead><tr><th>#</th><th>${esc(st.group || "Βαθμολογία")}</th><th class="num">Α</th>${c.sport === "basketball" ? `<th class="num">Ν-Η</th><th class="num">Πόντοι</th><th class="num">Νίκες</th>` : `<th class="num">Ν-Ι-Η</th><th class="num">Γκολ</th><th class="num">Β</th>`}<th>Φόρμα</th></tr></thead><tbody>`;
        h += st.rows.map(r => `<tr><td>${r.pos}</td><td><b>${esc(r.team)}</b></td><td class="num">${r.p}</td><td class="num">${c.sport === "basketball" ? `${r.w}-${r.l}` : `${r.w}-${r.d}-${r.l}`}</td><td class="num">${r.gf}:${r.ga}</td><td class="num"><b>${r.pts}</b></td><td>${formHtml((r.form || "").replace(/,/g, ""))}</td></tr>`).join("");
        h += `</tbody></table></div>`;
      }
      if (cid === "PL" && state.data.referees?.length) {
        h += `<h2>Διαιτητές Premier League (4 σεζόν)</h2><div class="table-wrap"><table><thead><tr><th>Διαιτητής</th><th class="num">Αγώνες</th><th class="num">Κάρτες</th><th class="num">O3.5</th><th class="num">O4.5</th><th class="num">Φάουλ</th><th class="num">Κόκκ.</th><th class="num">Νίκη γηπ.</th></tr></thead><tbody>`;
        h += state.data.referees.map(r => `<tr><td><b>${esc(r.name)}</b></td><td class="num">${r.n}</td><td class="num ${r.cards > r.league_cards ? "ev-neg" : ""}">${f2(r.cards)}</td><td class="num">${pct(r.o35)}</td><td class="num">${pct(r.o45)}</td><td class="num">${r.fouls ?? "—"}</td><td class="num">${f2(r.reds)}</td><td class="num">${pct(r.home_win)}</td></tr>`).join("");
        h += `</tbody></table></div><div class="note" style="margin-top:8px">Κόκκινο = περισσότερες κάρτες από τον μέσο όρο του πρωταθλήματος (${f2(state.data.referees[0].league_cards)}).</div>`;
      }
      if (!(c.teams && c.teams.length) && !(c.standings && c.standings.length)) h += `<div class="note">Η βαθμολογία θα εμφανιστεί όταν μπει το κλειδί του football-data.org.</div>`;
    }
    view.innerHTML = h;
  }

  // ---------- λεπτομέρειες αγώνα ----------
  function openMatch(id) {
    const m = findMatch(id);
    if (!m) return;
    const hs = m.home_stats || {}, as = m.away_stats || {};
    const row = (lbl, a, b, fmt = f2) => {
      const t = (Number(a) || 0) + (Number(b) || 0) || 1;
      return `<div class="stat-row"><div class="l">${fmt(a)}</div><div class="c">${lbl}<div class="bar"><i style="width:${(a / t) * 100}%"></i><i style="width:${(b / t) * 100}%"></i></div></div><div class="r">${fmt(b)}</div></div>`;
    };
    const groups = {}, sgroups = {};
    const ssels = statSels(m), allSels = m.markets.concat(ssels);
    m.markets.forEach(s => (groups[s.group] = groups[s.group] || []).push(s));
    ssels.forEach(s => (sgroups[s.group] = sgroups[s.group] || []).push(s));
    const crest = u => (u ? `<img src="${esc(u)}" alt="">` : "");
    const bk = isBasket(m);
    const fx = x => (bk ? Number(x).toFixed(1) : f2(x));
    let h = `<div class="grab"></div><button class="close" data-close>✕</button>
      <div class="match-head"><span>${bk ? "🏀 " : ""}${COMP[m.comp]}${m.stage && bk ? " · " + esc(m.stage) : ""}</span><span>${dt(m.date)}</span></div>
      <div class="vs"><div class="t">${crest(m.home_crest)}${esc(m.home)}</div><div class="mid">${bk ? "Πόντοι" : "xG"}<br><b style="font-size:18px;color:var(--text)">${fx(m.xg[0])} – ${fx(m.xg[1])}</b></div><div class="t">${crest(m.away_crest)}${esc(m.away)}</div></div>
      <div class="tags" style="justify-content:center;margin-bottom:10px">${bk
        ? `<span class="pill muted">Σύνολο ~${(m.xg[0] + m.xg[1]).toFixed(1)}</span><span class="pill muted">Διαφορά ~${(m.xg[0] - m.xg[1]).toFixed(1)}</span>`
        : `<span class="pill muted">Κόρνερ ~${m.corners}</span><span class="pill muted">Κάρτες ~${m.cards}</span>${m.referee ? `<span class="pill muted">Διαιτ.: ${esc(m.referee)}</span>` : ""}`}<span class="pill muted">Αξιοπιστία: ${m.confidence}</span></div>`;
    if (!bk) h += diffHtml(m);
    if (m.top && m.top.length) {
      h += `<h2>Πιθανότερες προβλέψεις</h2>` + m.top.map((t, i) => `<div class="card pick" style="margin-bottom:8px">
        <div><div class="sel">${i === 0 ? "★ " : ""}${esc(t.label)} <span class="pill ${LVL[t.level] || "muted"}">${esc(t.level || "")}</span></div><div class="match">${esc(t.group)}</div></div>
        <div><div class="odds">${pct(t.p)}</div><div class="book">εκτ. ${f2(t.est)} · δίκαιη ${f2(t.fair)}</div></div>
        <div class="meta"><span class="why">${esc(t.why || "")}</span></div></div>`).join("");
    }
    if (bk && (hs.p || as.p)) {
      h += `<h2>Σύγκριση (μ.ό. ανά αγώνα)</h2><div class="card">
        <div class="stat-row"><div class="l">${formHtml(hs.form)}</div><div class="c">Φόρμα</div><div class="r">${formHtml(as.form)}</div></div>
        ${row("Πόντοι υπέρ", hs.ppg, as.ppg, fx)}${row("Πόντοι κατά", hs.oppg, as.oppg, fx)}${row("Σύνολο αγώνων", hs.total, as.total, fx)}</div>`;
    } else if (hs.p || as.p) {
      h += `<h2>Σύγκριση (μ.ό. ανά αγώνα)</h2><div class="card">
        <div class="stat-row"><div class="l">${formHtml(hs.form)}</div><div class="c">Φόρμα</div><div class="r">${formHtml(as.form)}</div></div>
        ${row("xG υπέρ", hs.xgf, as.xgf)}${row("xG κατά", hs.xga, as.xga)}${row("Γκολ υπέρ", hs.gf, as.gf)}${row("Γκολ κατά", hs.ga, as.ga)}
        ${row("Σουτ στην εστία", hs.sot, as.sot)}${row("Κόρνερ υπέρ", hs.cf, as.cf)}${row("Κάρτες", hs.cards, as.cards)}
        ${row("G/G", hs.btts, as.btts, pct)}${row("Over 2.5", hs.o25, as.o25, pct)}${row("Ανέπαφη εστία", hs.cs, as.cs, pct)}</div>`;
    }
    if (bk) {
      const md = state.data.competitions[m.comp]?.model || {};
      h += `<div class="note">Αναμενόμενοι πόντοι: μοντέλο <b>${fx(m.model_xg[0])}–${fx(m.model_xg[1])}</b>${m.market_xg ? `, αγορά <b>${fx(m.market_xg[0])}–${fx(m.market_xg[1])}</b>. Τελικά (15% μοντέλο, 85% αγορά)` : ". Τελικά"}: <b>${fx(m.xg[0])}–${fx(m.xg[1])}</b>. Τυπικό σφάλμα (από ${md.games || "—"} αγώνες): διαφορά ±${m.sd[0]}, σύνολο ±${m.sd[1]} πόντοι. Χωρίς δωρεάν ιστορικές αποδόσεις δεν έχει γίνει backtest στο μπάσκετ.</div>`;
    } else if (m.market_xg) h += `<div class="note">Αναμενόμενα γκολ: μοντέλο <b>${f2(m.model_xg[0])}–${f2(m.model_xg[1])}</b>, αγορά <b>${f2(m.market_xg[0])}–${f2(m.market_xg[1])}</b>. Τελικά χρησιμοποιείται η αγορά: <b>${f2(m.xg[0])}–${f2(m.xg[1])}</b> (στην έρευνα σε χιλιάδες αγώνες το μοντέλο δεν βελτίωσε την ακρίβεια όπου υπάρχουν αποδόσεις· μένει ως εξήγηση).${m.comp === "CL" && state.data.goal_factor?.CL?.matches ? ` Στο Champions League μπαίνουν περισσότερα γκολ από τα εγχώρια πρωταθλήματα (${state.data.goal_factor.CL.actual_goals}/αγώνα σε ${state.data.goal_factor.CL.matches} αγώνες), γι' αυτό το μοντέλο διορθώνεται ×${state.data.goal_factor.CL.factor}.` : ""}</div>`;
    if (!bk) {
      const r = m.ref_stats;
      h += `<h2>Διαιτητής</h2>`;
      h += r ? `<div class="card"><b>${esc(r.name)}</b> <span class="pill muted">${r.n} αγώνες (4 σεζόν)</span>
        <div class="kpis" style="margin:10px 0 0">
          <div class="kpi"><span>Κάρτες/αγώνα</span><b>${f2(r.cards)}</b><span>μ.ό. πρωταθλ. ${f2(r.league_cards)}</span></div>
          <div class="kpi"><span>Over 3.5 κάρτες</span><b>${pct(r.o35)}</b></div>
          <div class="kpi"><span>Over 4.5 κάρτες</span><b>${pct(r.o45)}</b></div>
          <div class="kpi"><span>Φάουλ/αγώνα</span><b>${r.fouls ?? "—"}</b></div></div>
        <div style="color:var(--muted);font-size:12px;margin-top:8px">Γηπεδούχοι ${f2(r.home_cards)} · Φιλοξενούμενοι ${f2(r.away_cards)} κάρτες · Κόκκινες ${f2(r.reds)}/αγώνα · Νίκη γηπεδούχου ${pct(r.home_win)}</div></div>`
        : `<div class="note">${m.referee ? `Ο διαιτητής ${esc(m.referee)} δεν υπάρχει στο ιστορικό μας.` : m.comp === "PL" ? "Δεν έχει ανακοινωθεί ακόμα διαιτητής (συνήθως 2–4 μέρες πριν)." : "Για αυτή τη διοργάνωση δεν υπάρχουν δωρεάν στατιστικά διαιτητών."}</div>`;
    }
    if (m.h2h && m.h2h.length) {
      h += `<h2>Τελευταίες αναμετρήσεις</h2><div class="table-wrap"><table><thead><tr><th>Ημ/νία</th><th>Αγώνας</th><th class="num">Σκορ</th>${bk ? "" : `<th class="num">Κόρνερ</th><th class="num">Κάρτες</th>`}</tr></thead><tbody>${m.h2h.map(x => `<tr><td>${x.date}</td><td>${esc(x.home)} – ${esc(x.away)}</td><td class="num"><b>${x.score}</b></td>${bk ? "" : `<td class="num">${x.corners ?? "—"}</td><td class="num">${x.cards ?? "—"}</td>`}</tr>`).join("")}</tbody></table></div>`;
    }
    if (!bk && m.stx && Object.keys(m.stx.m || {}).length) {
      const S = m.stx, hsx = m.home_stats || {}, asx = m.away_stats || {};
      const season = { co: ["cf", "ca"], sh: ["sh", "sh_a"], st: ["sot", "sot_a"], fo: ["fo", "fo_a"], ca: ["cards", "cards_a"], sv: ["sv", null] };
      const fs = (o, k) => (o[k] == null ? "—" : Number(o[k]).toFixed(1));
      h += `<h2>Στατιστικά αγώνα</h2><div class="table-wrap"><table><thead><tr><th>Μετρική</th><th class="num">${esc(m.home)}</th><th class="num">${esc(m.away)}</th><th class="num">Σύνολο</th><th class="num">Μ.ό. πρωτ.</th><th>Αντίπαλος · σενάριο</th></tr></thead><tbody>
        ${Object.entries(S.m).map(([k, [a, b, t0]]) => { const t = t0 ?? a + b; const av = (S.avg[k] || [0, 0]); const d = t / (av[0] + av[1] || 1) - 1; const [f, ag] = season[k];
          return `<tr><td>${STAT_ICON[k]} <b>${STATN[k]}</b><small class="pc">φέτος: ${fs(hsx, f)}${ag ? "/" + fs(hsx, ag) : ""} · ${fs(asx, f)}${ag ? "/" + fs(asx, ag) : ""} (υπέρ/κατά)</small></td><td class="num">${a.toFixed(1)}</td><td class="num">${b.toFixed(1)}</td><td class="num"><b>${t.toFixed(1)}</b></td><td class="num">${(av[0] + av[1]).toFixed(1)} <small class="${d > 0.08 ? "ev-pos" : d < -0.08 ? "ev-neg" : ""}">${d >= 0 ? "+" : ""}${Math.round(d * 100)}%</small></td><td><small class="pc">${(() => { const w = (S.why || {})[k]; if (!w) return "—"; const pc = x => (x >= 1 ? "+" : "") + Math.round((x - 1) * 100) + "%"; const vb = { fo: "προκαλεί", ca: "προκαλεί", sv: "αναγκάζει σε" }[k] || "επιτρέπει"; return `${esc(m.away)} ${vb} ${pc(w.h[1])} · ${esc(m.home)} ${vb} ${pc(w.a[1])} · σενάριο ${pc(w.gs[0])}/${pc(w.gs[1])}`; })()}</small></td></tr>`; }).join("")}
        ${S.ht ? `<tr><td>⏱ <b>Γκολ Α΄ ημιχρόνου</b></td><td class="num">${S.ht[0].toFixed(2)}</td><td class="num">${S.ht[1].toFixed(2)}</td><td class="num"><b>${(S.ht[0] + S.ht[1]).toFixed(2)}</b></td><td class="num">—</td><td></td></tr>` : ""}
        </tbody></table></div><div class="note" style="margin-top:8px">Αναμενόμενα για αυτόν τον αγώνα = τι κάνει η ομάδα × τι <b>επιτρέπει ο αντίπαλος</b> (π.χ. «επιτρέπει +20% κόρνερ» = δέχεται 20% περισσότερα από τον μέσο όρο) × <b>σενάριο αγώνα</b> (πόσο φαβορί είναι, από τις αποδόσεις), με διόρθωση προς τον μέσο όρο που μετρήθηκε στην έρευνα${m.ref_stats ? " και ο διαιτητής στις κάρτες/φάουλ" : ""}. Αποκρούσεις = σουτ στην εστία του αντιπάλου μείον τα γκολ.</div>`;
      if (m.stat_edges?.length) h += `<h3 class="day-sub">Απόκλιση από τον μέσο όρο</h3><div class="grid">${m.stat_edges.map(e => edgeCard(m, e, false)).join("")}</div>`;
      if (m.stat_top?.length) h += `<h3 class="day-sub">Πιθανότερα στα στατιστικά</h3>` + m.stat_top.map(t => `<div class="card pick" style="margin-bottom:8px">
        <div><div class="sel">${esc(t.label)} <span class="pill ${LVL[t.level] || "muted"}">${esc(t.level || "")}</span> ${fitPill(t)}</div><div class="match">${esc(t.group)}</div></div>
        <div><div class="odds">${pct(t.p)}</div><div class="book">δίκαιη ${f2(t.fair)} · αξίζει από ${f2(1.03 / t.p)}</div></div>
        <div class="meta"><span class="why">${esc(t.why || "")}</span></div>${fitLine(t)}</div>`).join("");
    }
    if (m.scores) h += `<h2>Πιθανότερα σκορ</h2><div class="scores">${m.scores.map(s => `<span><b>${s.s}</b> ${pct(s.p)}</span>`).join("")}</div>`;
    if (m.players) h += playersHtml(m);
    h += `<h2>Αγορές</h2><div class="note"><b>Εκτ.</b> = εκτιμώμενη απόδοση Stoiximan/Superbet (διάμεσος εταιρειών ή πραγματικό γκανιότ από ${(state.data.margins?.["1X2"]?.n || 0).toLocaleString("el-GR")} αγώνες). Γράψε την πραγματική απόδοση στο κουτάκι: αν βγει πράσινο, έχει value. Πάτα το όνομα για να την περάσεις στα στοιχήματά σου.</div>`;
    const mkGroups = (G) => { for (const [g, list] of Object.entries(G)) {
      h += `<div class="mk-group"><h3>${esc(g)}</h3><div class="mk head"><span>Επιλογή</span><span class="v">Πιθ.</span><span class="v">Δίκαιη</span><span class="v">Εκτ.</span><span class="v">Δική σου</span></div>`;
      h += list.map((s, i) => `<div class="mk ${s.value ? "is-value" : ""}" data-sel="${esc(s.key)}|${esc(s.side)}">
        <span class="n" data-add>${esc(s.label)} <small class="evout ${evCls(s.est_ev)}">${s.est_ev != null ? evTxt(s.est_ev) : ""}</small></span>
        <span class="v">${pct(s.p)}</span><span class="v">${f2(s.fair)}</span>
        <span class="v" title="${esc(srcTxt(s.est_src) + (s.best ? `\nΚαλύτερη: ${s.best} (${s.book})` : ""))}">${s.est ? f2(s.est) : "—"}</span>
        <input inputmode="decimal" placeholder="—" data-odds></div>`).join("");
      h += `</div>`;
    } };
    mkGroups(groups);
    if (Object.keys(sgroups).length) {
      h += `<h2>Αγορές στατιστικών</h2><div class="note">Κόρνερ, σουτ, σουτ στην εστία, φάουλ, κάρτες, αποκρούσεις, Α΄ ημίχρονο. Δεν υπάρχουν δωρεάν αποδόσεις γι' αυτές: η <b>Εκτ.</b> υποθέτει γκανιότ ~9% (συνηθισμένο σε αυτές τις αγορές). Γράψε την πραγματική απόδοση της Stoiximan/Superbet για να δεις αν έχει value.</div>`;
      mkGroups(sgroups);
    }
    openSheet(h);
    const sheet = $("#sheet");
    sheet.querySelectorAll("[data-odds]").forEach(inp => inp.addEventListener("input", () => {
      const rowEl = inp.closest(".mk");
      const [k, side] = rowEl.dataset.sel.split("|");
      const s = allSels.find(x => x.key === k && x.side === side);
      const o = parseFloat(inp.value.replace(",", "."));
      const out = rowEl.querySelector(".evout");
      if (!o || o <= 1) { out.textContent = s.est_ev != null ? evTxt(s.est_ev) : ""; out.className = "evout " + evCls(s.est_ev); rowEl.classList.toggle("is-value", s.value); return; }
      const ev = s.p * o + s.pp - 1;
      out.textContent = evTxt(ev); out.className = "evout " + evCls(ev);
      rowEl.classList.toggle("is-value", ev >= 0.03);
    }));
    sheet.querySelectorAll("[data-add]").forEach(n => n.addEventListener("click", () => {
      const rowEl = n.closest(".mk");
      const [k, side] = rowEl.dataset.sel.split("|");
      const s = allSels.find(x => x.key === k && x.side === side);
      const typed = parseFloat((rowEl.querySelector("[data-odds]").value || "").replace(",", "."));
      openBetForm({ match: `${m.home} – ${m.away}`, comp: m.comp, date: m.date, selection: s.label, group: s.group, odds: typed || s.est || "", p: s.p });
    }));
  }

  function playersHtml(m) {
    const P = m.players;
    const cell = st => st ? `<b>${st.avg}</b><small class="pc">O${st.line}: ${pct(st.p_over)} · ${f2(st.fair_over)}/${f2(st.fair_under)}</small>` : "—";
    const team = (side, name) => {
      const rows = P[side] || [];
      if (!rows.length) return "";
      if (isBasket(m)) {
        return `<h3 class="day-sub">${esc(name)}</h3><div class="table-wrap"><table class="ptable"><thead><tr><th>Παίκτης</th><th class="num">Λεπτά</th><th>Πόντοι</th><th>Ριμπάουντ</th><th>Ασίστ</th><th>P+R+A</th><th>Τρίποντα</th><th>Φάουλ</th></tr></thead><tbody>
          ${rows.map(r => `<tr><td><b>${esc(r.name)}</b>${r.starter ? ' <span class="pill muted">5άδα</span>' : ""}<small class="pc">${r.games} αγώνες</small></td><td class="num">${r.mins}</td><td>${cell(r.pts)}</td><td>${cell(r.reb)}</td><td>${cell(r.ast)}</td><td>${cell(r.pra)}</td><td>${cell(r.tpm)}</td><td>${cell(r.fouls)}</td></tr>`).join("")}</tbody></table></div>`;
      }
      return `<h3 class="day-sub">${esc(name)}</h3><div class="table-wrap"><table class="ptable"><thead><tr><th>Παίκτης</th><th class="num">Λεπτά</th><th>Σκοράρει</th><th>Ασίστ</th><th>Κάρτα</th><th>Τάκλιν</th><th class="num">CBI</th></tr></thead><tbody>
        ${rows.map(r => `<tr><td><b>${esc(r.name)}</b> <span class="pill muted">${r.pos}</span>${r.pen ? ' <span class="pill muted">πέναλτι</span>' : ""}${r.news ? `<small class="pc" style="color:var(--amber)">${esc(r.news)}</small>` : ""}</td>
          <td class="num">${r.mins}'</td>
          <td><b>${pct(r.p_goal)}</b><small class="pc">δίκαιη ${f2(r.fair_goal)} · ${r.goals} γκολ, xG ${r.xg}</small></td>
          <td><b>${pct(r.p_assist)}</b><small class="pc">δίκαιη ${f2(r.fair_assist)} · ${r.assists} ασ., xA ${r.xa}</small></td>
          <td><b>${pct(r.p_card)}</b><small class="pc">δίκαιη ${f2(r.fair_card)} · ${r.yc} κίτρ.</small></td>
          <td><b>${r.tackles90}</b>/90<small class="pc">1+ ${pct(r.p_tk1)} · 2+ ${pct(r.p_tk2)} · 3+ ${pct(r.p_tk3)}</small></td>
          <td class="num">${r.cbi}</td></tr>`).join("")}</tbody></table></div>`;
    };
    return `<h2>Παίκτες</h2><div class="note">${esc(P.source)}. Οι στοιχηματικές βάζουν συνήθως μεγαλύτερο γκανιότ στις αγορές παικτών, οπότε σύγκρινε την απόδοσή τους με τη <b>δίκαιη</b>: αν δίνουν πιο πάνω, έχει value.${isBasket(m) ? " Μορφή: μέσος όρος · πιθανότητα Over στη γραμμή · δίκαιη Over/Under." : " Φάουλ και σουτ ανά παίκτη δεν υπάρχουν σε δωρεάν πηγή."}</div>
      ${team("home", m.home)}${team("away", m.away)}`;
  }

  function openSheet(html) {
    $("#sheet").innerHTML = html;
    $("#sheet").scrollTop = 0;
    $("#sheet").classList.add("open"); $("#backdrop").classList.add("open");
  }
  function closeSheet() { $("#sheet").classList.remove("open"); $("#backdrop").classList.remove("open"); }

  // ---------- τα στοιχήματά μου ----------
  const bets = () => store.get("vb_bets", []);
  const saveBets = b => store.set("vb_bets", b);

  function openBetForm(pre = {}) {
    const h = `<div class="grab"></div><button class="close" data-close>✕</button><h2>Νέο στοίχημα</h2>
      <form id="betForm" class="form-grid">
        <label class="f full">Αγώνας<input name="match" required value="${esc(pre.match || "")}"></label>
        <label class="f full">Επιλογή<input name="selection" required value="${esc(pre.selection || "")}"></label>
        <label class="f">Απόδοση<input name="odds" inputmode="decimal" required value="${esc(pre.odds || "")}"></label>
        <label class="f">Ποσό (€)<input name="stake" inputmode="decimal" required value="${esc(store.get("vb_last_stake", ""))}"></label>
        <label class="f full">Στοιχηματική<select name="book">${BOOKS.map(b => `<option ${store.get("vb_last_book", "Stoiximan") === b ? "selected" : ""}>${b}</option>`).join("")}</select></label>
        <button class="btn full" type="submit">Αποθήκευση</button>
      </form>`;
    openSheet(h);
    $("#betForm").addEventListener("submit", e => {
      e.preventDefault();
      const f = Object.fromEntries(new FormData(e.target));
      const odds = parseFloat(String(f.odds).replace(",", ".")), stake = parseFloat(String(f.stake).replace(",", "."));
      if (!odds || !stake) return;
      const b = bets();
      b.unshift({ id: Date.now(), match: f.match, selection: f.selection, odds, stake, book: f.book, comp: pre.comp || null,
        group: pre.group || null, p: pre.p || null, date: pre.date || new Date().toISOString(), result: null });
      saveBets(b); store.set("vb_last_stake", stake); store.set("vb_last_book", f.book);
      closeSheet(); state.tab = "bets"; syncTabs(); render();
    });
  }

  function renderBets() {
    const b = bets();
    const settled = b.filter(x => x.result !== null);
    const staked = settled.reduce((a, x) => a + x.stake, 0);
    const profit = settled.reduce((a, x) => a + (x.result === 1 ? x.stake * (x.odds - 1) : x.result === 0 ? -x.stake : 0), 0);
    const wins = settled.filter(x => x.result === 1).length;
    const byBook = {};
    settled.forEach(x => { const k = x.book; byBook[k] = byBook[k] || { s: 0, p: 0, n: 0 }; byBook[k].n++; byBook[k].s += x.stake; byBook[k].p += x.result === 1 ? x.stake * (x.odds - 1) : x.result === 0 ? -x.stake : 0; });
    let h = `<div class="kpis">
      <div class="kpi"><span>Κέρδος/Ζημιά</span><b class="${profit >= 0 ? "ev-pos" : "ev-neg"}">${profit >= 0 ? "+" : ""}${profit.toFixed(2)}€</b></div>
      <div class="kpi"><span>ROI</span><b class="${profit >= 0 ? "ev-pos" : "ev-neg"}">${staked ? ((profit / staked) * 100).toFixed(1) : "0"}%</b></div>
      <div class="kpi"><span>Επιτυχία</span><b>${settled.length ? Math.round((wins / settled.length) * 100) : 0}%</b></div>
      <div class="kpi"><span>Στοιχήματα</span><b>${b.length}</b></div></div>`;
    h += `<div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn" data-newbet>+ Νέο στοίχημα</button><button class="btn ghost" data-export>Εξαγωγή</button><label class="btn ghost" style="display:inline-block">Εισαγωγή<input type="file" accept=".json" data-import hidden></label></div>`;
    if (Object.keys(byBook).length) {
      h += `<h2>Ανά στοιχηματική</h2><div class="table-wrap"><table><thead><tr><th>Στοιχηματική</th><th class="num">Πλήθος</th><th class="num">Ποντάρισμα</th><th class="num">Κέρδος</th><th class="num">ROI</th></tr></thead><tbody>${Object.entries(byBook).map(([k, v]) => `<tr><td>${esc(k)}</td><td class="num">${v.n}</td><td class="num">${v.s.toFixed(2)}€</td><td class="num ${v.p >= 0 ? "ev-pos" : "ev-neg"}">${v.p.toFixed(2)}€</td><td class="num">${((v.p / v.s) * 100).toFixed(1)}%</td></tr>`).join("")}</tbody></table></div>`;
    }
    h += `<h2>Ιστορικό</h2>`;
    h += b.length ? b.map(x => `<div class="card bet ${x.result === null ? "" : "res-" + String(x.result).replace(".", "")}">
      <div><b>${esc(x.selection)}</b><div class="match" style="color:var(--muted);font-size:13px">${esc(x.match)} · ${esc(x.book)}</div></div>
      <div style="text-align:right"><b>@${f2(x.odds)}</b><div style="color:var(--muted);font-size:12px">${x.stake}€</div></div>
      <div class="actions">${x.result === null ? `<button class="btn sm" data-res="1" data-id="${x.id}">Κέρδος</button><button class="btn sm ghost" data-res="0" data-id="${x.id}">Χάθηκε</button><button class="btn sm ghost" data-res="0.5" data-id="${x.id}">Επιστροφή</button>`
        : `<span class="pill ${x.result === 1 ? "value" : "muted"}">${x.result === 1 ? "Κέρδος +" + (x.stake * (x.odds - 1)).toFixed(2) + "€" : x.result === 0 ? "Χάθηκε −" + x.stake + "€" : "Επιστροφή"}</span><button class="btn sm ghost" data-res="null" data-id="${x.id}">Αναίρεση</button>`}
        <button class="btn sm ghost" data-del="${x.id}" style="margin-left:auto">Διαγραφή</button></div></div>`).join("")
      : `<div class="empty"><b>Κανένα στοίχημα ακόμα</b>Πρόσθεσε από τον αγώνα (πάτα μια επιλογή) ή με το κουμπί.</div>`;
    h += `<div class="note" style="margin-top:14px">Τα στοιχήματα αποθηκεύονται σε αυτή τη συσκευή. Με «Εξαγωγή» κρατάς αντίγραφο ασφαλείας.</div>`;
    view.innerHTML = h;
  }

  // ---------- μοντέλο (ιστορικό value επιλογών) ----------
  function renderModel() {
    const picks = (state.history?.picks || []).filter(p => state.comp === "ALL" || p.comp === state.comp);
    const settled = picks.filter(p => p.result !== null);
    const profit = settled.reduce((a, p) => a + (p.result === 1 ? p.odds - 1 : p.result === 0 ? -1 : 0), 0);
    const wins = settled.filter(p => p.result === 1).length;
    const avgOdds = settled.length ? settled.reduce((a, p) => a + p.odds, 0) / settled.length : 0;
    let h = `<div class="note">Κάθε value επιλογή που βγάζει η εφαρμογή καταγράφεται αυτόματα και ελέγχεται μετά το ματς (1 μονάδα ανά επιλογή). Έτσι βλέπουμε τίμια αν το μοντέλο κερδίζει μακροπρόθεσμα. Χρειάζονται 100+ επιλογές για ασφαλές συμπέρασμα.</div>
      <div class="kpis"><div class="kpi"><span>Κέρδος (μονάδες)</span><b class="${profit >= 0 ? "ev-pos" : "ev-neg"}">${profit >= 0 ? "+" : ""}${profit.toFixed(2)}</b></div>
      <div class="kpi"><span>ROI</span><b>${settled.length ? ((profit / settled.length) * 100).toFixed(1) : 0}%</b></div>
      <div class="kpi"><span>Επιτυχία</span><b>${settled.length ? Math.round((wins / settled.length) * 100) : 0}%</b></div>
      <div class="kpi"><span>Μ.ό. απόδοσης</span><b>${f2(avgOdds)}</b></div></div>`;
    const pr = (state.history?.preds || []).filter(p => state.comp === "ALL" || p.comp === state.comp);
    const prs = pr.filter(p => p.result !== null && p.result !== undefined);
    if (pr.length) {
      const hits = prs.filter(p => p.result === 1).length;
      const avgP = prs.length ? prs.reduce((a, p) => a + p.p, 0) / prs.length : 0;
      const units = prs.reduce((a, p) => a + (p.result === 1 ? p.est - 1 : p.result === 0 ? -1 : 0), 0);
      const bucket = (lo, hi) => { const b = prs.filter(p => p.p >= lo && p.p < hi); return b.length ? `<tr><td>${Math.round(lo * 100)}–${Math.round(hi * 100)}%</td><td class="num">${b.length}</td><td class="num">${pct(b.reduce((a, p) => a + p.p, 0) / b.length)}</td><td class="num"><b>${pct(b.filter(p => p.result === 1).length / b.length)}</b></td></tr>` : ""; };
      h += `<h2>Πιθανότερες προβλέψεις: πόσο πέφτουν μέσα</h2><div class="kpis">
        <div class="kpi"><span>Ελεγμένες</span><b>${prs.length}</b><span>εκκρεμούν ${pr.length - prs.length}</span></div>
        <div class="kpi"><span>Επιτυχία</span><b>${prs.length ? pct(hits / prs.length) : "—"}</b></div>
        <div class="kpi"><span>Αναμενόταν</span><b>${prs.length ? pct(avgP) : "—"}</b></div>
        <div class="kpi"><span>Μονάδες (εκτ. απόδ.)</span><b class="${units >= 0 ? "ev-pos" : "ev-neg"}">${units >= 0 ? "+" : ""}${units.toFixed(2)}</b></div></div>
        ${prs.length ? `<div class="table-wrap"><table><thead><tr><th>Πιθανότητα</th><th class="num">Πλήθος</th><th class="num">Πρόβλεψη</th><th class="num">Έγινε</th></tr></thead><tbody>${bucket(0.5, 0.6)}${bucket(0.6, 0.7)}${bucket(0.7, 1.01)}</tbody></table></div>` : `<div class="note">Οι πρώτες προβλέψεις θα ελεγχθούν μόλις τελειώσουν οι αγώνες.</div>`}`;
    }
    const sp = (state.history?.spreds || []).filter(p => (state.comp === "ALL" || p.comp === state.comp) && p.result !== null && p.result !== undefined);
    if ((state.history?.spreds || []).length) {
      const row = (lbl, L) => { const n = L.length, hit = L.filter(p => p.result === 1).length, ap = n ? L.reduce((a, p) => a + p.p, 0) / n : 0, av = L.filter(p => p.p_avg != null);
        return `<tr><td>${lbl}</td><td class="num">${n}</td><td class="num">${n ? pct(ap) : "—"}</td><td class="num">${av.length ? pct(av.reduce((a, p) => a + p.p_avg, 0) / av.length) : "—"}</td><td class="num"><b>${n ? pct(hit / n) : "—"}</b></td></tr>`; };
      h += `<h2>Στατιστικά: πόσο πέφτουν μέσα</h2><div class="table-wrap"><table><thead><tr><th>Είδος</th><th class="num">Ελεγμένες</th><th class="num">Μοντέλο</th><th class="num">Μ.ό. πρωτ.</th><th class="num">Έγινε</th></tr></thead><tbody>
        ${row("Πιθανότερη ανά αγώνα", sp.filter(p => p.kind === "top"))}${row("Αποκλίσεις από μ.ό.", sp.filter(p => p.kind === "edge"))}</tbody></table></div>`;
    }
    const slips = (state.history?.slips || []).slice().reverse();
    if (slips.length) {
      const done = slips.filter(s => s.result !== null);
      const sp = done.reduce((a, s) => a + (s.result === 1 ? s.odds - 1 : -1), 0);
      h += `<h2>Προτεινόμενα δελτία (${slips.length})</h2><div class="note">Κέρδη ${done.filter(s => s.result === 1).length}/${done.length} · Αποτέλεσμα <b class="${sp >= 0 ? "ev-pos" : "ev-neg"}">${sp >= 0 ? "+" : ""}${sp.toFixed(2)}</b> μονάδες (με τις εκτιμώμενες αποδόσεις)</div>`;
      h += slips.slice(0, 10).map(s => `<div class="card"><div style="display:flex;justify-content:space-between"><b>@${f2(s.odds)} · ${pct(s.p)}</b>${s.result === null ? `<span class="pill muted">εκκρεμεί</span>` : s.result === 1 ? `<span class="pill value">ΚΕΡΔΟΣ</span>` : `<span class="pill" style="background:rgba(240,82,82,.12);color:var(--red)">ΧΑΘΗΚΕ</span>`}</div>
        ${s.legs.map(l => `<div style="font-size:13px;margin-top:6px">${l.result === 1 ? "✓" : l.result === 0 ? "✕" : "·"} ${esc(l.home)} – ${esc(l.away)}: <b>${esc(l.label)}</b> @${f2(l.est)} ${l.score ? `<span style="color:var(--muted)">(${l.score})</span>` : ""}</div>`).join("")}</div>`).join("");
    }
    const RS = state.research;
    if (RS) {
      const pc = x => (x == null ? "—" : (x > 0 ? "+" : "") + (x * 100).toFixed(1) + "%");
      const dv = RS.devig?.find(d => d.method.startsWith("Power")) || RS.devig?.[0];
      h += `<h2>Έρευνα: πού κάνουν λάθος οι στοιχηματικές</h2>
      <div class="note">${RS.matches.toLocaleString("el-GR")} πραγματικοί αγώνες, ${RS.leagues.length} πρωταθλήματα, 2023/24–2025/26. Αποδόσεις Bet365 πριν τον αγώνα (μαλακή εταιρεία, σαν Stoiximan), δίκαιη τιμή από Pinnacle/μέσο όρο, τελικό αποτέλεσμα. Οι κανόνες βρέθηκαν σε 2023–25 και ελέγχθηκαν στο 2025/26.</div>
      <h3 class="day-sub">1. Αν έπαιζες ΟΛΑ τα στοιχήματα στη Bet365, ανά απόδοση</h3>
      <div class="table-wrap"><table><thead><tr><th>Αγορά</th><th>Απόδοση</th><th class="num">Στοιχ.</th><th class="num">Υπονοούμενη</th><th class="num">Βγήκε</th><th class="num">ROI</th></tr></thead><tbody>
      ${RS.bias.map(b => `<tr><td>${b.market}</td><td>${b.range}</td><td class="num">${b.n.toLocaleString("el-GR")}</td><td class="num">${pct(b.implied)}</td><td class="num">${pct(b.hit)}</td><td class="num ${evCls(b.roi)}">${pc(b.roi)}</td></tr>`).join("")}</tbody></table></div>
      <div class="note" style="margin-top:8px">Τα φαβορί (χαμηλές αποδόσεις) είναι σχεδόν δίκαια τιμολογημένα. Τα αουτσάιντερ έχουν πολύ μεγαλύτερο γκανιότ. Γι' αυτό οι προβλέψεις προτιμούν μεγάλες πιθανότητες.</div>
      ${dv ? `<h3 class="day-sub">2. Πιθανότητες: λέει ${"–"} έγινε (μέθοδος power, σφάλμα ${dv.error} μονάδες)</h3>
      <div class="table-wrap"><table><thead><tr><th>Πιθανότητα</th><th class="num">Περιπτώσεις</th><th class="num">Πρόβλεψη</th><th class="num">Έγινε</th></tr></thead><tbody>
      ${dv.calibration.map(c => `<tr><td>${c.bucket}</td><td class="num">${c.n.toLocaleString("el-GR")}</td><td class="num">${pct(c.pred)}</td><td class="num"><b>${pct(c.actual)}</b></td></tr>`).join("")}</tbody></table></div>` : ""}
      <h3 class="day-sub">3. Βοηθάει το δικό μας μοντέλο όταν υπάρχουν αποδόσεις;</h3>
      <div class="table-wrap"><table><thead><tr><th>Βάρος μοντέλου</th><th class="num">Ακρίβεια (log-loss)</th></tr></thead><tbody>
      ${RS.weights.map(w => `<tr><td>${w.w === 0 ? "0 (μόνο αγορά) ✓" : w.w}</td><td class="num">${w.logloss}</td></tr>`).join("")}</tbody></table></div>
      <div class="note" style="margin-top:8px">Όχι: η αγορά μόνη της είναι πιο ακριβής. Το μοντέλο μένει για εξηγήσεις και για αγορές/πρωταθλήματα χωρίς αποδόσεις.</div>
      <h3 class="day-sub">4. Κενά αγοράς: Bet365 πάνω από τη δίκαιη τιμή</h3>
      <div class="table-wrap"><table><thead><tr><th>Κανόνας</th><th>Περίοδος</th><th class="num">Στοιχ.</th><th class="num">ROI</th><th class="num">CLV</th></tr></thead><tbody>
      ${RS.gap.flatMap(g => [["disc", "2023–25"], ["test", "2025/26"]].map(([k, l]) => `<tr><td>EV ≥ ${g.evmin * 100}%</td><td>${l}</td><td class="num">${g[k].n}</td><td class="num ${evCls(g[k].roi)}">${pc(g[k].roi)} <small style="color:var(--muted)">±${(g[k].ci * 100).toFixed(0)}%</small></td><td class="num ${evCls(g[k].clv)}">${pc(g[k].clv)}</td></tr>`)).join("")}</tbody></table></div>
      <div class="note" style="margin-top:8px">Θετικό CLV και στις δύο περιόδους: η μόνη σταθερή «ρωγμή» που βρήκαμε. Αυτές είναι οι «Ευκαιρίες» στην αρχική.</div>
      ${RS.patterns?.length ? `<h3 class="day-sub">5. Μοτίβα ανά πρωτάθλημα</h3>` + RS.patterns.map(pt => `<div class="note">${esc(pt.name)} · ${pt.side === "X" ? "Ισοπαλία" : esc(pt.side)} (απόδοση ${pt.odds[0]}–${pt.odds[1]}): ${pc(pt.disc.roi)} σε ${pt.disc.n} αγώνες (2023–25), ${pc(pt.test.roi)} σε ${pt.test.n} (2025/26). Μεγάλη αβεβαιότητα.</div>`).join("") : ""}`;
      const ST = Object.entries(RS.stats || {}).filter(([k]) => k !== "ht" && !k.startsWith("_"));
      if (ST.length) {
        const meta = RS.stats._meta || {};
        const sg = x => (x == null ? "—" : `<span class="${evCls(x)}">${x > 0 ? "+" : ""}${x}%</span>`);
        const ed = e => (e?.n ? `${pct(e.model)} / ${pct(e.avg)} / <b>${pct(e.hit)}</b> <small style="color:var(--muted)">±${Math.round((e.ci || 0) * 100)} (${e.n.toLocaleString("el-GR")})</small> ${e.ok ? "✓" : ""}` : "—");
        h += `<h3 class="day-sub">6. Στατιστικά: κόρνερ, σουτ, φάουλ, κάρτες, αποκρούσεις</h3>
        <div class="note"><b>${(meta.matches || 0).toLocaleString("el-GR")}</b> αγώνες, <b>${(meta.leagues || []).length}</b> πρωταθλήματα, σεζόν ${(meta.seasons || []).map(x => "20" + x.slice(0, 2) + "/" + x.slice(2)).join(", ")}. Κάθε μετρική προβλέπεται εβδομάδα-εβδομάδα μόνο με παλιούς αγώνες. <b>Τρεις ανεξάρτητοι έλεγχοι</b> (${(meta.tests || []).map(x => "20" + x.slice(0, 2) + "/" + x.slice(2)).join(", ")}): σε κάθε έναν οι παράμετροι βγήκαν μόνο από τις προηγούμενες σεζόν. ✓ = ισχύει και στους τρεις.</div>
        <div class="table-wrap"><table><thead><tr><th>Μετρική</th><th class="num">Μ.ό.</th><th class="num">Ακρίβεια vs μ.ό. (σύνολο / ομάδα)</th><th class="num">Αξία αντιπάλου</th><th class="num">Αξία σεναρίου</th><th class="num">Διαιτητής</th><th class="num">Αποκλίσεις ομάδας: μοντ./μ.ό./έγινε</th><th class="num">Αποκλίσεις συνόλου</th></tr></thead><tbody>
        ${ST.map(([k, s]) => `<tr><td>${STAT_ICON[k] || ""} <b>${esc(s.name)}</b></td><td class="num">${s.avg}</td><td class="num">${sg(s.gain)} / ${sg(s.team_gain)}</td><td class="num">${sg(s.opp_gain)}</td><td class="num">${sg(s.gs_gain)}</td><td class="num">${s.ref_gain == null ? "—" : sg(s.ref_gain)}${s.ref_ok ? " ✓" : ""}</td><td class="num">${ed(s.edge_team)}</td><td class="num">${ed(s.edge_total)}</td></tr>`).join("")}</tbody></table></div>
        <h3 class="day-sub">Ανά σεζόν ελέγχου (αποκλίσεις ομάδας: πρόβλεψη → έγινε)</h3>
        <div class="table-wrap"><table><thead><tr><th>Μετρική</th>${(meta.tests || []).map(t => `<th class="num">20${t.slice(0, 2)}/${t.slice(2)}</th>`).join("")}</tr></thead><tbody>
        ${ST.map(([k, s]) => `<tr><td>${STAT_ICON[k] || ""} ${esc(s.name)}</td>${(meta.tests || []).map(t => { const e = s.tests?.[t]?.edge_team; return `<td class="num">${e?.n ? `${pct(e.model)} → <b>${pct(e.hit)}</b> <small style="color:var(--muted)">(${e.n})</small>` : "—"}</td>`; }).join("")}</tr>`).join("")}</tbody></table></div>
        <div class="note" style="margin-top:8px"><b>Ακρίβεια</b>: πόσο καλύτερα από τον μέσο όρο προβλέπει το Over/Under στη συνηθισμένη γραμμή (log-loss). <b>Αξία αντιπάλου</b>: πόσο χειρότερη θα ήταν η πρόβλεψη αν κοιτάζαμε μόνο την ίδια την ομάδα. <b>Αξία σεναρίου</b>: πόσο βοηθάει το «ποιος είναι φαβορί» από τις αποδόσεις. ± = διάστημα εμπιστοσύνης 95%.${RS.stats.ht ? ` Α΄ ημίχρονο: Over 0.5 πρόβλεψη ${pct(RS.stats.ht.lines[0].pred)}, έγινε ${pct(RS.stats.ht.lines[0].actual)} · Over 1.5 ${pct(RS.stats.ht.lines[1].pred)} / ${pct(RS.stats.ht.lines[1].actual)}.` : ""}</div>`;
        const lgs = {};
        ST.forEach(([k, s]) => Object.entries(s.by_league || {}).forEach(([lg, e]) => { (lgs[lg] = lgs[lg] || {})[k] = e; }));
        if (Object.keys(lgs).length) {
          h += `<h3 class="day-sub">Ανά πρωτάθλημα (αποκλίσεις ομάδας: έγινε − μ.ό. πρωταθλήματος)</h3><div class="table-wrap"><table><thead><tr><th>Πρωτάθλημα</th>${ST.map(([k]) => `<th class="num">${STAT_ICON[k] || ""}</th>`).join("")}</tr></thead><tbody>
          ${Object.entries(lgs).sort().map(([lg, row]) => `<tr><td>${esc(LGN[lg] || lg)}</td>${ST.map(([k]) => { const e = row[k]; if (!e) return `<td class="num">—</td>`; const d = e.hit - e.avg; return `<td class="num"><span class="${d > 0.05 ? "ev-pos" : d < 0 ? "ev-neg" : ""}">${d >= 0 ? "+" : ""}${Math.round(d * 100)}</span><small style="color:var(--muted)"> ${e.n}</small></td>`; }).join("")}</tr>`).join("")}</tbody></table></div>
          <div class="note" style="margin-top:8px">Πόσες μονάδες πιο συχνά «βγήκε» η πλευρά του μοντέλου από ό,τι έλεγε ο μέσος όρος του πρωταθλήματος (μικρός αριθμός = πλήθος αγώνων).</div>`;
        }
      }
    }
    const bt = state.backtest;
    if (bt) {
      const cur = bt.weights.find(w => w.w === bt.current_weight) || bt.weights[0];
      h += `<h2>Backtest: ${esc(bt.league)} ${bt.seasons.map(s => "20" + s.slice(0, 2) + "/" + s.slice(2)).join(", ")}</h2>
      <div class="note">Το μοντέλο ξανάτρεξε εβδομάδα-εβδομάδα σε <b>${bt.matches.toLocaleString("el-GR")}</b> πραγματικούς αγώνες, μόνο με όσα ήξερε πριν από κάθε αγώνα. Ποντάρισμα 1 μονάδας στις αποδόσεις Bet365 όποτε έβγαινε value ≥3%. <b>CLV</b> = πόσο καλύτερη ήταν η απόδοση από την τελική (κλείσιμο). Θετικό CLV είναι η πιο αξιόπιστη ένδειξη ότι ένα μοντέλο έχει πραγματικό πλεονέκτημα.</div>
      <div class="table-wrap"><table><thead><tr><th>Βάρος μοντέλου</th><th class="num">Ακρίβεια 1X2</th><th class="num">Στοιχ. 1X2</th><th class="num">ROI</th><th class="num">CLV</th><th class="num">Στοιχ. O/U</th><th class="num">ROI</th><th class="num">CLV</th></tr></thead><tbody>
      ${bt.weights.map(w => { const a = w.bets["1X2"] || {}, o = w.bets["OU2.5"] || {}; const pc = x => (x == null ? "—" : (x > 0 ? "+" : "") + (x * 100).toFixed(1) + "%");
        return `<tr ${w.w === bt.current_weight ? 'style="background:var(--accent-soft)"' : ""}><td><b>${w.w === 0 ? "0 (μόνο αγορά)" : w.w === 1 ? "1 (μόνο μοντέλο)" : w.w}</b>${w.w === bt.current_weight ? " ✓" : ""}</td><td class="num">${w.logloss_1x2}</td><td class="num">${a.n || 0}</td><td class="num ${evCls(a.roi)}">${pc(a.roi)}</td><td class="num ${evCls(a.clv)}">${pc(a.clv)}</td><td class="num">${o.n || 0}</td><td class="num ${evCls(o.roi)}">${pc(o.roi)}</td><td class="num ${evCls(o.clv)}">${pc(o.clv)}</td></tr>`; }).join("")}
      </tbody></table></div><div class="note" style="margin-top:8px">Ακρίβεια = log-loss (μικρότερο = καλύτερο). ✓ = η ρύθμιση που χρησιμοποιεί τώρα η εφαρμογή.</div>
      <h2>Βαθμονόμηση (πρόβλεψη vs πραγματικότητα)</h2><div class="table-wrap"><table><thead><tr><th>Πιθανότητα μοντέλου</th><th class="num">Περιπτώσεις</th><th class="num">Πρόβλεψη</th><th class="num">Έγινε</th></tr></thead><tbody>
      ${cur.calibration.map(c => `<tr><td>${c.bucket}</td><td class="num">${c.n}</td><td class="num">${pct(c.pred)}</td><td class="num"><b>${pct(c.actual)}</b></td></tr>`).join("")}</tbody></table></div>`;
    }
    h += `<h2>Value επιλογές (${picks.length})</h2>`;
    h += picks.length ? `<div class="table-wrap"><table><thead><tr><th>Ημ/νία</th><th>Αγώνας</th><th>Επιλογή</th><th class="num">Απόδ.</th><th class="num">EV</th><th class="num">Σκορ</th><th>Αποτ.</th></tr></thead><tbody>${picks.slice().reverse().map(p => `<tr><td>${new Date(p.date).toLocaleDateString("el-GR", { day: "numeric", month: "short" })}</td><td>${esc(p.home)} – ${esc(p.away)}</td><td><b>${esc(p.label)}</b></td><td class="num">${f2(p.odds)}</td><td class="num ev-pos">${evTxt(p.ev)}</td><td class="num">${p.score || "—"}</td><td>${p.result === null ? `<span class="pill muted">εκκρεμεί</span>` : p.result === 1 ? `<span class="pill value">✓</span>` : p.result === 0 ? `<span class="pill" style="background:rgba(240,82,82,.12);color:var(--red)">✕</span>` : `<span class="pill muted">επιστρ.</span>`}</td></tr>`).join("")}</tbody></table></div>`
      : `<div class="empty"><b>Δεν υπάρχει ιστορικό ακόμα</b>Θα γεμίσει μόνο του με τις value επιλογές.</div>`;
    view.innerHTML = h;
  }

  // ---------- events ----------
  function syncTabs() {
    document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("active", b.dataset.tab === state.tab));
    document.querySelectorAll("#compFilter button").forEach(b => b.classList.toggle("active", b.dataset.comp === state.comp));
  }
  $("#tabs").addEventListener("click", e => { const t = e.target.closest("button"); if (!t) return; state.tab = t.dataset.tab; store.set("vb_tab", state.tab); syncTabs(); render(); });
  $("#compFilter").addEventListener("click", e => { const t = e.target.closest("button"); if (!t) return; state.comp = t.dataset.comp; store.set("vb_comp", state.comp); syncTabs(); render(); });
  $("#backdrop").addEventListener("click", closeSheet);
  $("#sheet").addEventListener("click", e => { if (e.target.closest("[data-close]")) closeSheet(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeSheet(); });

  view.addEventListener("click", e => {
    const chip = e.target.closest("[data-day]");
    if (chip) { state.day = chip.dataset.day; return render(); }
    const card = e.target.closest("[data-match]");
    if (card) return openMatch(card.dataset.match);
    if (e.target.closest("[data-newbet]")) return openBetForm();
    const sb = e.target.closest("[data-slipbet]");
    if (sb) {
      const [day, kind] = sb.dataset.slipbet.split("|");
      const sl = (state.data.slips || []).find(d => d.day === day)?.[kind];
      if (!sl) return;
      return openBetForm({ match: `Δελτίο ${kind === "simple" ? "απλό" : "ακραίο"} (${sl.legs.length})`, selection: sl.legs.map(l => `${l.home}-${l.away}: ${l.label}`).join(" | "), odds: sl.odds, p: sl.p, group: "Δελτίο" });
    }
    if (e.target.closest("[data-export]")) {
      const blob = new Blob([JSON.stringify(bets(), null, 1)], { type: "application/json" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "stoixhmata.json"; a.click();
      return;
    }
    const res = e.target.closest("[data-res]");
    if (res) {
      const b = bets(); const x = b.find(y => String(y.id) === res.dataset.id);
      x.result = res.dataset.res === "null" ? null : Number(res.dataset.res); saveBets(b); return renderBets();
    }
    const del = e.target.closest("[data-del]");
    if (del && confirm("Διαγραφή στοιχήματος;")) { saveBets(bets().filter(y => String(y.id) !== del.dataset.del)); renderBets(); }
  });
  view.addEventListener("change", e => {
    if (!e.target.matches("[data-import]")) return;
    const file = e.target.files[0]; if (!file) return;
    file.text().then(t => { try { const arr = JSON.parse(t); if (Array.isArray(arr)) { saveBets(arr); renderBets(); } } catch { alert("Μη έγκυρο αρχείο"); } });
  });

  state.tab = store.get("vb_tab", "value"); state.comp = store.get("vb_comp", "ALL");
  syncTabs();
  load();
})();
