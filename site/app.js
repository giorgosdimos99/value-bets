(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const view = $("#view");
  const state = { tab: "value", comp: "ALL", day: "ALL", data: null, history: null, more: {} };
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

  // Αποθήκευση: localStorage + δεύτερο αντίγραφο σε IndexedDB για τα σημαντικά (στοιχήματα, δελτίο).
  // Αν ο browser καθαρίσει το ένα, γίνεται αυτόματη επαναφορά από το άλλο.
  const KEEP = ["vb_bets", "vb_slip"];
  const idb = (() => {
    let dbp = null;
    const open = () => dbp || (dbp = new Promise((res, rej) => {
      try { const r = indexedDB.open("valuebets", 1); r.onupgradeneeded = () => r.result.createObjectStore("kv"); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); }
      catch (e) { rej(e); }
    }));
    const tx = (mode, fn) => open().then(db => new Promise((res, rej) => { const t = db.transaction("kv", mode); const out = fn(t.objectStore("kv")); t.oncomplete = () => res(out && out.result); t.onerror = () => rej(t.error); }));
    return { put: (k, v) => tx("readwrite", st => st.put(v, k)).catch(() => {}), get: k => tx("readonly", st => st.get(k)).catch(() => undefined) };
  })();
  const store = {
    get(k, def) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : def; } catch { return def; } },
    set(k, v) {
      try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* ιδιωτική περιήγηση */ }
      if (KEEP.includes(k)) { idb.put(k, { v, at: Date.now() }); try { localStorage.setItem(k + "_at", String(Date.now())); } catch { } }
    },
  };
  async function restoreStorage() {
    try { if (navigator.storage && navigator.storage.persist) state.persisted = await navigator.storage.persist(); } catch { }
    for (const k of KEEP) {
      const box = await idb.get(k);
      const local = store.get(k, null), lat = Number(localStorage.getItem(k + "_at") || 0);
      // το IndexedDB έχει πιο πρόσφατα (ή το localStorage άδειασε) -> επαναφορά
      if (box && box.v && (local === null || box.at > lat + 1000)) { try { localStorage.setItem(k, JSON.stringify(box.v)); localStorage.setItem(k + "_at", String(box.at)); } catch { } state.restored = true; }
      else if (local && (!box || lat > (box.at || 0))) idb.put(k, { v: local, at: lat || Date.now() });
    }
  }

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
    await restoreStorage();
    try {
      const r = await fetch("data/data.json?ts=" + Date.now());
      state.data = await r.json();
    } catch {
      state.data = { competitions: {}, updated: null };
    }
    try { state.history = await (await fetch("data/history.json?ts=" + Date.now())).json(); } catch { state.history = { picks: [] }; }
    try { state.backtest = await (await fetch("data/backtest.json?ts=" + Date.now())).json(); } catch { state.backtest = null; }
    try { state.research = await (await fetch("data/research.json?ts=" + Date.now())).json(); } catch { state.research = null; }
    try { state.fut = await (await fetch("data/futures.json?ts=" + Date.now())).json(); } catch { state.fut = null; }
    const comps = Object.entries(state.data.competitions || {}).filter(([, c]) => c.matches?.length);
    comps.forEach(([cid, c]) => { COMP[cid] = c.name; });
    if (!comps.some(([cid]) => cid === state.comp)) state.comp = "ALL";
    syncTabs();
    $("#updated").innerHTML = state.data.updated
      ? `Ενημέρωση<br>${new Date(state.data.updated).toLocaleString("el-GR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`
      : "Χωρίς δεδομένα";
    render();
  }

  // ---------- καρτέλες ----------
  function buildComp() {
    const comps = Object.entries(state.data?.competitions || {}).filter(([, c]) => c.matches?.length);
    const fb = comps.filter(([, c]) => c.sport !== "basketball" && !c.national), bb = comps.filter(([, c]) => c.sport === "basketball"),
      nt = comps.filter(([, c]) => c.national);
    const n = l => l.reduce((a, [, c]) => a + c.matches.length, 0);
    const label = state.comp === "ALL" ? `Όλες οι διοργανώσεις` : (COMP[state.comp] || state.comp);
    const cnt = state.comp === "ALL" ? n(comps) : (comps.find(([cid]) => cid === state.comp)?.[1].matches.length || 0);
    const grp = (title, list) => list.length ? `<div class="cp-g"><div class="cp-gt">${title}</div>${list.map(([cid, c]) =>
      `<button class="cp-i ${state.comp === cid ? "on" : ""}" data-cp="${cid}" data-q="${esc(c.name.toLowerCase())}"><span>${esc(c.name)}</span><small>${c.matches.length}</small></button>`).join("")}</div>` : "";
    $("#compFilter").innerHTML = `<div class="cp">
      <button class="cp-btn" id="compBtn" aria-haspopup="listbox"><span class="cp-dot"></span><span>${esc(label)}</span><small>${cnt}</small><svg width="12" height="8" viewBox="0 0 12 8"><path d="M1 1l5 5 5-5" stroke="currentColor" fill="none" stroke-width="1.6"/></svg></button>
      <div class="cp-panel" id="compPanel" hidden>
        <input class="cp-q" id="compQ" placeholder="Αναζήτηση διοργάνωσης…" autocomplete="off">
        <div class="cp-list">
          <button class="cp-i all ${state.comp === "ALL" ? "on" : ""}" data-cp="ALL" data-q="όλες"><span>Όλες οι διοργανώσεις</span><small>${n(comps)}</small></button>
          ${grp("⚽ Ποδόσφαιρο", fb)}${grp("🌍 Εθνικές ομάδες", nt)}${grp("🏀 Μπάσκετ", bb)}
        </div>
      </div></div>`;
  }

  function render() {
    buildComp();
    $("#compFilter").style.display = ["bets", "slip", "futures"].includes(state.tab) ? "none" : "flex";
    if (state.tab !== "slip") { state.slipOpen = false; $("#popBack")?.classList.remove("open"); }
    ({ value: renderValue, matches: renderMatches, teams: renderTeams, slip: renderSlip, bets: renderBets, model: renderModel, futures: renderFutures })[state.tab]();
    updateFab();
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
      ${[...sl.legs].sort((a, b) => a.date.localeCompare(b.date)).map(l => `<div class="leg" data-match="${l.match_id}"><div><b>${esc(nice(l, l.key, l.side, l.label))}</b><div class="match">${esc(l.home)} – ${esc(l.away)} · ${COMP[l.comp] || ""} · ${new Date(l.date).toLocaleTimeString("el-GR", { hour: "2-digit", minute: "2-digit" })}</div></div>
        <div class="lo"><b>${f2(l.est)}</b><span>${pct(l.p)}</span></div></div>`).join("")}
      <div class="slip-foot"><div><span>Απόδοση</span><b>${f2(sl.odds)}</b></div><div><span>Πιθανότητα</span><b>${pct(sl.p)}</b></div><div><span>EV</span><b class="${evCls(sl.ev)}">${evTxt(sl.ev)}</b></div></div>
      <button class="btn ghost" style="margin-top:10px;width:100%" data-slipbet="${day}|${kind}">+ Στα στοιχήματά μου</button></div>`;
  }


  // ---- Στατιστικά αγώνα: ίδιοι υπολογισμοί με το engine/stats.py (Negative Binomial) ----
  const LGN = { E0: "Premier League", SP1: "La Liga", D1: "Bundesliga", I1: "Serie A", F1: "Ligue 1", P1: "Primeira Liga", N1: "Eredivisie", B1: "Βέλγιο", T1: "Τουρκία", G1: "Ελλάδα", SC0: "Σκωτία", E1: "Championship", E2: "League One", E3: "League Two", EC: "National League", D2: "2. Bundesliga", I2: "Serie B", SP2: "Segunda", F2: "Ligue 2", SC1: "Σκωτία 2", SC2: "Σκωτία 3", SC3: "Σκωτία 4" };
  const STATN = { co: "Κόρνερ", sh: "Σουτ", st: "Σουτ στην εστία", fo: "Φάουλ (που κάνει η ομάδα)", ca: "Κάρτες", sv: "Αποκρούσεις" };
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
  const RANGE = { co: [[6.5, 13.5], [1.5, 8.5]], sh: [[15.5, 34.5], [5.5, 20.5]], st: [[4.5, 13.5], [1.5, 8.5]], fo: [[15.5, 32.5], [6.5, 17.5]], ca: [[1.5, 7.5], [0.5, 4.5]], sv: [[3.5, 9.5], [0.5, 6.5]] };
  const bookable = (k, total, L, po) => { const [lo, hi] = RANGE[k][total ? 0 : 1]; return L >= lo && L <= hi && po >= 0.2 && po <= 0.8; };
  function statSels(m) {
    const sx = m.stx;
    if (!sx) return [];
    const out = [];
    for (const [k, [mh, ma, mT0]] of Object.entries(sx.m || {})) {
      const name = STATN[k], mT = mT0 ?? mh + ma;
      const [pt, pT] = (sx.disp || {})[k] || [0.05, 0.03];
      const tot = nb(mT, pT);
      lines(mT, 3).forEach(L => { const po = pOver(tot, L); if (!bookable(k, true, L, po)) return; out.push(statSel(`${name}: σύνολο`, `S:${k}:T:${L}`, "Over", `Over ${L}`, po), statSel(`${name}: σύνολο`, `S:${k}:T:${L}`, "Under", `Under ${L}`, 1 - po)); });
      const dh = nb(mh, pt), da = nb(ma, pt);
      [["H", mh, dh, m.home], ["A", ma, da, m.away]].forEach(([side, mu, d, team]) => lines(mu, 2).forEach(L => {
        const po = pOver(d, L), g = `${name}: ${team}`;
        if (!bookable(k, false, L, po)) return;
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
    return out.filter(s => s.fair && s.p >= 0.15 && s.p <= 0.85);
  }
  const FIT = { 1: ["value", "✓ βολεύει"], 0: ["muted", "ουδέτερο"], "-1": ["warn", "✗ δεν βολεύει"] };
  const fitPill = t => (t.fit === undefined || t.fit === null ? "" : `<span class="pill ${FIT[t.fit][0]}">${FIT[t.fit][1]}</span>`);
  const hhmm = iso => new Date(iso).toLocaleTimeString("el-GR", { hour: "2-digit", minute: "2-digit", hour12: false });
  const dayShort = iso => { const k = dayKey(iso), l = chipLabel(k); return l.split(" ")[0].replace(/,$/, ""); };
  const timeBox = iso => `<div class="ri-time"><b>${hhmm(iso)}</b><span>${dayShort(iso)}</span></div>`;
  const pCls = p => (p >= 0.7 ? "hi" : p >= 0.6 ? "md" : "");
  const ri = (m, label, pills, right, rightSub, extraCls = "", p = null) => `<div class="ri click ${extraCls}" data-match="${m.id}">
      ${timeBox(m.date)}
      <div class="ri-main"><div class="ri-t">${label} ${pills || ""}</div><div class="ri-s">${isBasket(m) ? "🏀 " : ""}${esc(m.home)} – ${esc(m.away)} · ${esc(COMP[m.comp] || "")}</div></div>
      <div class="ri-r"><b class="${p == null ? "" : pCls(p)}">${right}</b><span>${rightSub || ""}</span></div></div>`;
  const ladderHtml = e => (e.ladder || []).map(x => `<span class="lad"><b>${e.side} ${x.line}</b> ${pct(x.p)} · από <b>${f2(x.min_odds)}</b></span>`).join("");
  function edgeBox(m, e) {
    return `<div class="card pick">
      <div><div class="sel">${STAT_ICON[e.stat] || ""} ${esc(e.label)} ${fitPill(e)}</div><div class="match">Αναμενόμενα ${e.exp} · μέσος όρος πρωταθλήματος ${e.avg}</div></div>
      <div><div class="odds">${pct(e.p)}</div><div class="book">μ.ό. λέει ${pct(e.p_avg)}</div></div>
      <div class="ladder">${ladderHtml(e)}</div>
      ${e.fit_text ? `<div class="fitline">${esc(e.fit_text)}</div>` : ""}
      ${e.n ? `<div class="fitline">Έρευνα: σε ${e.n.toLocaleString("el-GR")} παρόμοιες περιπτώσεις έγινε ${pct(e.hit)} (ο μέσος όρος έλεγε ${pct(e.r_avg)}).</div>` : ""}</div>`;
  }
  function absHtml(m) {
    const A = m.absences;
    if (!A || (!A.home.length && !A.away.length)) return "";
    const UP = { pts: "πόντοι", reb: "ριμπ.", ast: "ασίστ" };
    const side = (k, name) => {
      const ab = A[k], mv = (A.minutes || {})[k] || [];
      if (!ab.length) return `<div><b>${esc(name)}</b><div class="ri-s">Καμία απουσία βασικού</div></div>`;
      return `<div><b>${esc(name)}</b>${ab.map(x => `<div class="ri-s">${x.out ? "❌" : "❓"} ${esc(x.name)} <small>(${x.mins}' ανά αγώνα · ${esc(x.status)})</small></div>`).join("")}
        ${mv.length ? `<div class="ri-s" style="margin-top:6px">⏱️ Αναμενόμενα λεπτά: ${mv.map(p => `${esc(p.name)} ${(p.base + p.extra).toFixed(1)}' (+${p.extra}${Object.keys(p.up).length ? ", " + Object.entries(p.up).map(([q, v]) => `${UP[q]} +${Math.round(v * 100)}%`).join(", ") : ""})`).join(" · ")}</div>` : ""}</div>`;
    };
    return `<div class="card"><div class="absg">${side("home", m.home)}${side("away", m.away)}</div><div class="wx">Πηγή: ${esc(A.src)}. ❌ εκτός · ❓ αμφίβολος. Οι επιλογές παικτών υπολογίζουν ήδη τα επιπλέον λεπτά.</div></div>`;
  }
  function propBox(m, x) {
    const lad = (x.ladder || []).map(l => `<span class="lad"><b>${x.side} ${l.line}</b> ${pct(l.p)} · από <b>${f2(l.min_odds)}</b></span>`).join("");
    return `<div class="card pick">
      <div><div class="sel">🏀 ${esc(x.label)}</div><div class="match">${esc(x.team)} · αναμενόμενα ${x.exp} · μ.ό. 10 αγώνων ${x.avg10} · ~${x.mins}'${x.extra >= 1 ? ` <b class="mv dn">(+${x.extra}' λόγω απουσίας)</b>` : ""}</div></div>
      <div><div class="odds">${pct(x.p)}</div><div class="book">από ${f2(x.min_odds)}</div></div>
      <div class="ladder">${lad}</div>
      <div class="fitline">Έλεγχος: σε ${x.n.toLocaleString("el-GR")} παρόμοιες επιλογές βγήκε ${pct(x.hit)}.</div></div>`;
  }
  function diffHtml(m) {
    const D = m.difficulty;
    if (!D) return "";
    const lvlCls = l => /εύκολο/.test(l) ? "value" : /δύσκολο/.test(l) ? "warn" : "muted";
    const team = (t, name, side) => `<div class="mx-team ${side}">
        <div class="mx-name">${esc(name)}</div>
        <span class="pill ${lvlCls(t.level)}">${esc(t.level)}</span>
        <div class="mx-sub">${t.rank ? `${t.rank}η δύναμη από ${t.of}${t.league ? " · " + esc(t.league) : ""}` : ""}</div>
        ${t.form ? `<div class="mx-form">${formHtml(t.form)}</div>` : ""}
      </div>`;
    const [p1, px, p2] = D.p;
    const H = D.home, A = D.away;
    const coachTxt = t => t.coach
      ? `<b class="hl">Νέος: ${esc(t.coach.name || "—")}</b><small>${t.coach.caretaker ? "υπηρεσιακός · " : ""}${t.coach.games} αγώνες μαζί του</small>`
      : t.coach_known ? `<span>Καμία αλλαγή φέτος</span>` : `<span class="dim">Δεν υπάρχουν στοιχεία</span>`;
    const styleTxt = t => t.style ? t.style.tags.map(x => `<span class="chip">${esc(x)}</span>`).join("") : `<span class="dim">—</span>`;
    const W = m.weather;
    const wx = W ? `${W.mud >= 2 ? "🌧️" : W.rain > 0 ? "🌦️" : "⛅"} <b>${W.temp}°C</b> · αέρας ${Math.round(W.wind)} km/h · βροχή ${W.rain} mm <small>(${W.rain_before} mm τις 6 ώρες πριν)</small>`
      : `<span class="dim">Πρόγνωση μόνο για γήπεδα Αγγλίας</span>`;
    const row = (ic, label, a, b) => `<div class="cx-row"><div class="cx-l">${ic} ${label}</div><div class="cx-v">${a}</div><div class="cx-v">${b}</div></div>`;
    return `<div class="card mx">
        <div class="mx-grid">${team(H, m.home, "h")}<div class="mx-vs">VS</div>${team(A, m.away, "a")}</div>
        <div class="tri"><i style="width:${p1 * 100}%">1 · ${pct(p1)}</i><i style="width:${px * 100}%">X · ${pct(px)}</i><i style="width:${p2 * 100}%">2 · ${pct(p2)}</i></div>
      </div>
      <div class="card cx">
        <div class="cx-h">🧭 Πλαίσιο αγώνα</div>
        <div class="cx-row cx-head"><div class="cx-l"></div><div class="cx-v">${esc(m.home)}</div><div class="cx-v">${esc(m.away)}</div></div>
        ${row("⚙️", "Τρόπος παιχνιδιού", styleTxt(H), styleTxt(A))}
        ${row("🧑‍💼", "Προπονητής", coachTxt(H), coachTxt(A))}
        <div class="cx-row one"><div class="cx-l">🌦️ Καιρός</div><div class="cx-v">${wx}</div></div>
        <div class="cx-row one"><div class="cx-l">🎯 Αλλάζει την πρόβλεψη</div><div class="cx-v">${m.ctx_adj && m.ctx_adj.length ? m.ctx_adj.map(x => `<span class="chip on">${esc(x)}</span>`).join("") : `<span class="dim">Τίποτα ιδιαίτερο: μετράνε μόνο η δύναμη και οι αποδόσεις</span>`}</div></div>
      </div>`;
  }

  function ptopHtml(m) {
    if (!m.ptop || !m.ptop.length) return "";
    return `<h3 class="day-sub">🏀 3 πιθανότερες επιλογές παικτών</h3><div class="list">${m.ptop.map((x, i) => `<div class="ri">
        <div class="ri-main"><div class="ri-t">${i === 0 ? "★ " : ""}${esc(x.label)}${x.extra >= 1 ? ` <span class="pill value">+${x.extra}' λόγω απουσίας</span>` : ""}</div>
        <div class="ri-s">${esc(x.team)} · αναμενόμενα ${x.exp} · μ.ό. 10 αγώνων ${x.avg10} · ~${x.mins}'</div></div>
        <div class="ri-r"><b class="${x.p >= 0.6 ? "hi" : "md"}">${pct(x.p)}</b><span>συμφέρει από ${f2(x.min_odds)}</span></div></div>`).join("")}</div>
      <div class="wx">Πιθανότητα από τον έλεγχο (ό,τι βγήκε σε παρόμοιες επιλογές), όχι η ωμή του μοντέλου. Γραμμή = εκεί που τη βάζουν συνήθως οι εταιρείες (μέσος όρος 10 αγώνων). Αν η εταιρεία έχει άλλη γραμμή, έλεγξέ την στο 🧾 Δελτίο.</div>`;
  }
  function bkDefHtml(m) {
    const C = m.coef;
    if (!C) return "";
    const sg = x => `${x >= 0 ? "+" : "−"}${Math.abs(Math.round(x * 100))}%`;
    const cls = (x, good) => Math.abs(x) < 0.02 ? "dim" : (good ? "ev-pos" : "ev-neg");
    const team = (c, name) => `<div class="mx-team"><div class="mx-name">${esc(name)}</div>
        <div class="dv-k"><span>⚔️ Επίθεση</span><b class="${cls(c.att - 1, c.att > 1)}">${sg(c.att - 1)}</b><small>${c.ratt}η από ${c.of}</small></div>
        <div class="dv-k"><span>🛡️ Άμυνα (πόντοι που δέχεται)</span><b class="${cls(c.def - 1, c.def < 1)}">${sg(c.def - 1)}</b><small>${c.rdef}η από ${c.of}</small></div></div>`;
    let h = `<div class="card cx"><div class="cx-h">🛡️ Επίθεση & άμυνα</div>
      <div class="mx-grid">${team(C.home, m.home)}<div class="mx-vs">VS</div>${team(C.away, m.away)}</div>
      <div class="wx">Σε σχέση με τον μέσο όρο της λίγκας (πρόσφατοι αγώνες μετράνε περισσότερο). Επίθεση + = βάζει περισσότερους πόντους, άμυνα − = δέχεται λιγότερους (καλό).</div>`;
    const D = m.dvp;
    if (D) {
      const RN = { G: "Γκαρντ", F: "Φόργουορντ", C: "Ψηλοί" }, ST = [["pts", "Πόντοι"], ["reb", "Ριμπ."], ["ast", "Ασίστ"], ["tpm", "Τρίπ."]];
      // τι δέχεται η ΑΜΥΝΑ κάθε ομάδας: αυτό ενδιαφέρει τους παίκτες του ΑΝΤΙΠΑΛΟΥ
      const tbl = (d, def, att) => `<div class="dv-t"><div class="dv-tt">Τι δέχεται η άμυνα της <b>${esc(def)}</b> <small>(ευνοεί τους παίκτες της ${esc(att)} όπου είναι +)</small></div>
        <table><thead><tr><th></th>${ST.map(([, l]) => `<th class="num">${l}</th>`).join("")}</tr></thead><tbody>
        ${["G", "F", "C"].map(r => `<tr><td>${RN[r]}</td>${ST.map(([k]) => { const v = d[r][k]; return `<td class="num ${Math.abs(v) < 0.03 ? "dim" : v > 0 ? "ev-pos" : "ev-neg"}">${sg(v)}</td>`; }).join("")}</tr>`).join("")}
        </tbody></table></div>`;
      h += `<div class="dv-g">${tbl(D.home, m.home, m.away)}${tbl(D.away, m.away, m.home)}</div>
        <div class="wx">Ρόλος από το τι κάνει ο παίκτης ανά λεπτό (ασίστ/τρίποντα = γκαρντ, ριμπάουντ/κοψίματα = ψηλός). Είναι πληροφορία: ο έλεγχος σε 4 λίγκες έδειξε ότι δεν βελτιώνει τις προβλέψεις παικτών πέρα από τη συνολική άμυνα, γι' αυτό το μοντέλο χρησιμοποιεί τη συνολική.</div>`;
    }
    return h + `</div>`;
  }

  // κατανοητά ονόματα επιλογών: "2" -> "Νίκη Real Madrid"
  function nice(m, key, side, label) {
    if (key === "1X2") return side === "1" ? `Νίκη ${m.home}` : side === "2" ? `Νίκη ${m.away}` : "Ισοπαλία";
    if (key === "ML") return `Νίκη ${side === "H" ? m.home : m.away}`;
    if (key === "DC") return { "1X": `${m.home} ή ισοπαλία`, X2: `${m.away} ή ισοπαλία`, "12": "Όχι ισοπαλία" }[side] || label;
    if (key === "BTTS") return side === "Yes" ? "Γκολ-Γκολ" : "Όχι Γκολ-Γκολ";
    const unit = (m.sport === "basketball" || state.data?.competitions?.[m.comp]?.sport === "basketball") ? "πόντοι" : "γκολ";
    if (/^OU\d/.test(key)) return `${side} ${key.slice(2)} ${unit}`;
    if (key.startsWith("AH")) { const L = parseFloat(key.slice(2)), t = side === "H" ? m.home : m.away, v = side === "H" ? L : -L; return L === 0 ? `${t} (ισοπαλία επιστροφή)` : `${t} ${v > 0 ? "+" : ""}${v}`; }
    if (key.startsWith("HT_OU")) return `${m.home} ${side} ${key.slice(5)} ${unit}`;
    if (key.startsWith("AT_OU")) return `${m.away} ${side} ${key.slice(5)} ${unit}`;
    return label;
  }
  const byTime = (a, b) => a.m.date.localeCompare(b.m.date);
  // κίνηση απόδοσης από το άνοιγμα: ▼ = έπεσε (η αγορά πήγε προς την επιλογή), ▲ = ανέβηκε
  const mv = (open, now) => !open || !now || Math.abs(open - now) < 0.02 ? "" :
    `<span class="mv ${now < open ? "dn" : "up"}" title="Πρώτη απόδοση που είδαμε: ${f2(open)}">${now < open ? "▼" : "▲"} από ${f2(open)}</span>`;
  const LVL = { "πολύ πιθανό": "value", "πιθανό": "solid", "μέτριο": "muted" };
  const section = (title, sub, body, more) => `<section class="sec"><div class="sec-h"><h2>${title}</h2>${more || ""}</div>${sub ? `<p class="sec-sub">${sub}</p>` : ""}${body}</section>`;

  function renderValue() {
    const all = matches();
    const ms = matches(true);
    if (!all.length) {
      view.innerHTML = `<div class="empty"><b>Δεν υπάρχουν αγώνες ακόμα</b>Μόλις βγει το επόμενο πρόγραμμα θα εμφανιστούν εδώ.</div>`;
      return;
    }
    let h = dayChips(all), L = "", R = "";
    // 1. Ευκαιρίες: εταιρεία πάνω από τη δίκαιη τιμή (έρευνα: θετικό CLV) + μοτίβα
    const opps = [
      ...ms.flatMap(m => m.values.map(s => ({ m, key: s.key, side: s.side, label: s.label, p: s.p, odds: s.best, open: s.open, book: s.book, ev: s.ev, kind: "gap" }))),
      ...ms.flatMap(m => (m.patterns || []).map(pt => ({ m, key: pt.key, side: pt.side, label: pt.label, p: pt.p, odds: pt.odds, book: "εκτίμηση", ev: pt.p * pt.odds - 1, kind: "pattern" }))),
    ].sort((a, b) => b.ev - a.ev).slice(0, 5).sort(byTime);
    L += section("💎 Ευκαιρίες", "Απόδοση μεγαλύτερη απ' όσο δικαιολογεί η πιθανότητα.",
      opps.length ? `<div class="list">${opps.map(o => ri(o.m, esc(nice(o.m, o.key, o.side, o.label)), `<span class="pill ${o.kind === "gap" ? "hot" : "solid"}">${evTxt(o.ev)}</span>`, f2(o.odds), `${esc(o.book || "")} · ${pct(o.p)} ${mv(o.open, o.odds)}`)).join("")}</div>`
        : `<div class="empty-s">Καμία αυτή τη στιγμή — οι αγορές είναι σωστές τις περισσότερες φορές.</div>`);
    // 2. Στατιστικά: μόνο οι πιο πιθανές, μία ανά αγώνα
    const seen = new Set();
    const edges = ms.flatMap(m => (m.stat_edges || []).map(e => ({ m, e })))
      .filter(x => x.e.fit !== -1)
      .sort((a, b) => (b.e.p - a.e.p) || ((b.e.fit ?? 0) - (a.e.fit ?? 0)))
      .filter(x => !seen.has(x.m.id) && seen.add(x.m.id))
      .slice(0, 6).sort(byTime);
    L += section("📊 Στατιστικά", "Οι 6 πιο πιθανές (μία ανά αγώνα), με σειρά ώρας. Παίξ' το αν η απόδοση είναι ≥ «από». Για τα υπόλοιπα άνοιξε τον αγώνα.",
      edges.length ? `<div class="list">${edges.map(({ m, e }) => ri(m, `${STAT_ICON[e.stat] || ""} ${esc(e.label)}`, fitPill(e), pct(e.p), `από ${f2(e.min_odds)}`, "", e.p)).join("")}</div>`
        : `<div class="empty-s">Καμία μεγάλη απόκλιση στους αγώνες που φαίνονται.</div>`);
    // 2β. Παίκτες μπάσκετ: μόνο επιλογές που πέρασαν τον έλεγχο
    const props = ms.flatMap(m => (m.props || []).map(x => ({ m, x }))).sort((a, b) => b.x.p - a.x.p).slice(0, 6).sort(byTime);
    if (props.length) L += section("🏀 Παίκτες", "Πόντοι, ριμπάουντ, ασίστ κ.ά. μόνο όπου το μοντέλο κέρδισε στον έλεγχο. Παίξ' το αν η απόδοση είναι ≥ «από».",
      `<div class="list">${props.map(({ m, x }) => ri(m, esc(x.label), "", pct(x.p), `από ${f2(x.min_odds)}`, "", x.p)).join("")}</div>`);
    // 3. Πιθανότερες προβλέψεις: μόνο οι κορυφαίες
    const preds = ms.filter(m => m.top && m.top.length).map(m => ({ m, t: m.top[0] })).sort((a, b) => b.t.p - a.t.p).slice(0, 8).sort(byTime);
    R += section("⭐ Πιθανότερες προβλέψεις", "Οι 8 πιο πιθανές (απόδοση ≥ 1.40), με σειρά ώρας. Πάτα για ανάλυση του αγώνα.",
      preds.length ? `<div class="list">${preds.map(({ m, t }) => ri(m, esc(nice(m, t.key, t.side, t.label)), `<span class="pill ${LVL[t.level] || "muted"}">${esc(t.level || "")}</span>`, pct(t.p), `~${f2(t.est)} ${mv(t.open, t.best)}`, "", t.p)).join("")}</div>`
        : `<div class="empty-s">Καμία πρόβλεψη για αυτή την επιλογή.</div>`);
    // 4. Δελτία
    const slips = (state.data.slips || []).filter(s => state.day === "ALL" || s.day === state.day).slice(0, 1);
    if (slips.length && state.comp === "ALL") {
      R += section("🎫 Δελτίο ημέρας", `${dayLabel(slips[0].day)} · απόδοση 5+ και 20+.`,
        slips.map(d => `<div class="grid slips">${["simple", "extreme"].map(k => d[k] ? slipCard(d[k], k, d.day) : "").join("")}</div>`).join(""));
    }
    view.innerHTML = h + `<div class="home"><div class="col">${L}</div><div class="col">${R}</div></div>`;
  }

  function matchCard(m) {
    const bk = isBasket(m);
    const p = Object.fromEntries(m.markets.filter(s => s.key === (bk ? "ML" : "1X2")).map(s => [bk ? { H: "1", A: "2" }[s.side] : s.side, s]));
    const crest = u => (u ? `<img src="${esc(u)}" alt="" loading="lazy">` : "");
    const unit = bk ? "πόντοι" : "xG";
    const fmtx = x => (bk ? Number(x).toFixed(1) : f2(x));
    return `<div class="card click" data-match="${m.id}">
      <div class="match-head"><span>${bk ? "🏀 " : ""}${COMP[m.comp]}${m.stage && m.comp === "CL" ? " · " + (STAGE[m.stage] || "") : bk && m.stage ? " · " + esc(m.stage) : ""}</span><span class="kick">${hhmm(m.date)}</span></div>
      <div class="teams">
        <div class="team">${crest(m.home_crest)}${esc(m.home)}<span class="xg">${unit} ${fmtx(m.xg[0])}</span></div>
        <div class="team">${crest(m.away_crest)}${esc(m.away)}<span class="xg">${unit} ${fmtx(m.xg[1])}</span></div>
      </div>
      <div class="probs" ${bk ? 'style="grid-template-columns:repeat(3,1fr)"' : ""}>${(bk ? ["1", "2"] : ["1", "X", "2"]).map(k => `<div class="prob"><b>${p[k] ? pct(p[k].p) : "—"}</b><span>${k} · ${p[k] ? f2(p[k].fair) : "—"}</span></div>`).join("")}
      ${bk ? `<div class="prob"><b>${(m.xg[0] + m.xg[1]).toFixed(1)}</b><span>σύνολο πόντων</span></div>` : ""}</div>
      ${bk && m.ptop && m.ptop.length ? `<div class="pt1">🏀 ${esc(m.ptop[0].label)} <b>${pct(m.ptop[0].p)}</b></div>` : ""}
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
      if (!c.national && !(c.teams && c.teams.length) && !(c.standings && c.standings.length)) h += `<div class="note">Η βαθμολογία θα εμφανιστεί όταν μπει το κλειδί του football-data.org.</div>`;
    }
    view.innerHTML = h;
  }

  // ---------- λεπτομέρειες αγώνα (καρτέλες: Σύνοψη / Στατιστικά / Αγορές / Παίκτες) ----------
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
    ssels.forEach(s => { const st = s.group.split(":")[0]; (sgroups[st] = sgroups[st] || {}); (sgroups[st][s.group] = sgroups[st][s.group] || []).push(s); });
    const crest = u => (u ? `<img src="${esc(u)}" alt="">` : "");
    const bk = isBasket(m);
    const fx = x => (bk ? Number(x).toFixed(1) : f2(x));
    const hasStats = !bk && m.stx && Object.keys(m.stx.m || {}).length;
    const tabs = [["sum", "Σύνοψη"], ...(hasStats || hs.p ? [["st", "Στατιστικά"]] : []), ["mk", "Αγορές"], ...(m.players ? [["pl", "Παίκτες"]] : [])];

    let h = `<div class="grab"></div><button class="close" data-close>✕</button>
      <button class="btn sm sx-open" data-openslip="${esc(m.id)}">🧾 Στο δελτίο</button>
      <div class="match-head"><span>${bk ? "🏀 " : ""}${esc(COMP[m.comp] || "")}${m.stage && bk ? " · " + esc(m.stage) : ""}</span><span>${dt(m.date)}</span></div>
      <div class="vs"><div class="t">${crest(m.home_crest)}${esc(m.home)}</div><div class="mid"><span class="kick big">${hhmm(m.date)}</span><br>${bk ? "Πόντοι" : "xG"}<br><b style="font-size:18px;color:var(--text)">${fx(m.xg[0])} – ${fx(m.xg[1])}</b></div><div class="t">${crest(m.away_crest)}${esc(m.away)}</div></div>
      <div class="seg">${tabs.map(([k, l], i) => `<button data-pane-btn="${k}" class="${i ? "" : "active"}">${l}</button>`).join("")}</div>`;

    // --- Σύνοψη ---
    let s1 = bk ? ptopHtml(m) + bkDefHtml(m) : diffHtml(m);
    if (m.top && m.top.length) {
      s1 += `<h3 class="day-sub">Πιθανότερες προβλέψεις</h3><div class="list">` + m.top.map((t, i) => `<div class="ri">
        <div class="ri-main"><div class="ri-t">${i === 0 ? "★ " : ""}${esc(nice(m, t.key, t.side, t.label))} <span class="pill ${LVL[t.level] || "muted"}">${esc(t.level || "")}</span></div><div class="ri-s">${esc(t.why || t.group)}</div></div>
        <div class="ri-r"><b>${pct(t.p)}</b><span>~${f2(t.est)} ${mv(t.open, t.best)}</span></div></div>`).join("") + `</div>`;
    }
    if (m.values?.length) s1 += `<h3 class="day-sub">💎 Ευκαιρίες</h3><div class="list">` + m.values.map(s => `<div class="ri"><div class="ri-main"><div class="ri-t">${esc(nice(m, s.key, s.side, s.label))} <span class="pill hot">${evTxt(s.ev)}</span></div><div class="ri-s">Η ${esc(s.book)} δίνει πάνω από τη δίκαιη τιμή (${f2(s.fair)})</div></div><div class="ri-r"><b>${f2(s.best)}</b><span>${pct(s.p)} ${mv(s.open, s.best)}</span></div></div>`).join("") + `</div>`;
    if (m.props?.length) s1 += `<h3 class="day-sub">🏀 Παίκτες με αξία</h3><div class="grid">${m.props.map(x => propBox(m, x)).join("")}</div>`;
    if (m.stat_edges?.length) s1 += `<h3 class="day-sub">📊 Στατιστικά με αξία</h3><div class="grid">${m.stat_edges.map(e => edgeBox(m, e)).join("")}</div>`;
    if (m.stat_top?.length) s1 += `<h3 class="day-sub">Πιθανότερα στα στατιστικά</h3><div class="list">` + m.stat_top.map(t => `<div class="ri">
        <div class="ri-main"><div class="ri-t">${esc(t.label)} ${fitPill(t)}</div><div class="ri-s">${esc(t.fit_text || t.why || "")}</div></div>
        <div class="ri-r"><b>${pct(t.p)}</b><span>από ${f2(1.03 / t.p)}</span></div></div>`).join("") + `</div>`;
    if (m.scores) s1 += `<h3 class="day-sub">Πιθανότερα σκορ</h3><div class="scores">${m.scores.map(s => `<span><b>${s.s}</b> ${pct(s.p)}</span>`).join("")}</div>`;

    // --- Στατιστικά ---
    let s2 = "";
    if (bk && (hs.p || as.p)) {
      const md = state.data.competitions[m.comp]?.model || {};
      s2 += `<div class="card">
        <div class="stat-row"><div class="l">${formHtml(hs.form)}</div><div class="c">Φόρμα</div><div class="r">${formHtml(as.form)}</div></div>
        ${row("Πόντοι υπέρ", hs.ppg, as.ppg, fx)}${row("Πόντοι κατά", hs.oppg, as.oppg, fx)}${row("Σύνολο αγώνων", hs.total, as.total, fx)}</div>
        <p class="sec-sub">Τυπικό σφάλμα (από ${md.games || "—"} αγώνες): διαφορά ±${m.sd[0]}, σύνολο ±${m.sd[1]} πόντοι.</p>`;
    }
    if (hasStats) {
      const S = m.stx;
      const vb = k => ({ fo: "προκαλεί", ca: "προκαλεί", sv: "αναγκάζει σε" }[k] || "επιτρέπει");
      const pc = x => (x >= 1 ? "+" : "") + Math.round((x - 1) * 100) + "%";
      s2 += `<div class="table-wrap"><table class="xt"><thead><tr><th>Αναμενόμενα</th><th class="num">${esc(m.home)}</th><th class="num">${esc(m.away)}</th><th class="num">Σύνολο</th><th class="num">Μ.ό.</th></tr></thead><tbody>
        ${Object.entries(S.m).map(([k, [a, b, t0]]) => { const t = t0 ?? a + b; const av = S.avg[k] || [0, 0]; const d = t / (av[0] + av[1] || 1) - 1; const w = (S.why || {})[k];
          return `<tr><td>${STAT_ICON[k]} ${STATN[k]}${w ? `<small class="pc">${esc(m.away)} ${vb(k)} ${pc(w.h[1])} · ${esc(m.home)} ${vb(k)} ${pc(w.a[1])}</small>` : ""}</td><td class="num">${a.toFixed(1)}</td><td class="num">${b.toFixed(1)}</td><td class="num"><b>${t.toFixed(1)}</b></td><td class="num">${(av[0] + av[1]).toFixed(1)}<small class="${d > 0.08 ? "ev-pos" : d < -0.08 ? "ev-neg" : ""}"> ${d >= 0 ? "+" : ""}${Math.round(d * 100)}%</small></td></tr>`; }).join("")}
        ${S.ht ? `<tr><td>⏱ Γκολ Α΄ ημιχρόνου</td><td class="num">${S.ht[0].toFixed(2)}</td><td class="num">${S.ht[1].toFixed(2)}</td><td class="num"><b>${(S.ht[0] + S.ht[1]).toFixed(2)}</b></td><td class="num">—</td></tr>` : ""}
        </tbody></table></div><p class="sec-sub">Ομάδα × τι επιτρέπει ο αντίπαλος × ποιος είναι φαβορί${m.ref_stats ? " × διαιτητής (κάρτες)" : ""}.</p>`;
    }
    if (!bk && (hs.p || as.p)) {
      s2 += `<h3 class="day-sub">Φέτος (ανά αγώνα)</h3><div class="card">
        <div class="stat-row"><div class="l">${formHtml(hs.form)}</div><div class="c">Φόρμα</div><div class="r">${formHtml(as.form)}</div></div>
        ${row("Γκολ υπέρ", hs.gf, as.gf)}${row("Γκολ κατά", hs.ga, as.ga)}${row("xG υπέρ", hs.xgf, as.xgf)}${row("xG κατά", hs.xga, as.xga)}
        ${hs.sh != null ? row("Σουτ", hs.sh, as.sh) : ""}${row("Σουτ στην εστία", hs.sot, as.sot)}${row("Κόρνερ", hs.cf, as.cf)}${hs.fo != null ? row("Φάουλ", hs.fo, as.fo) : ""}${row("Κάρτες", hs.cards, as.cards)}
        ${row("G/G", hs.btts, as.btts, pct)}${row("Over 2.5", hs.o25, as.o25, pct)}</div>`;
    }
    if (!bk && m.ref_stats) {
      const r = m.ref_stats;
      s2 += `<h3 class="day-sub">Διαιτητής: ${esc(r.name)}</h3><div class="kpis">
        <div class="kpi"><span>Κάρτες/αγώνα</span><b>${f2(r.cards)}</b><span>μ.ό. ${f2(r.league_cards)}</span></div>
        <div class="kpi"><span>Over 4.5 κάρτες</span><b>${pct(r.o45)}</b></div>
        <div class="kpi"><span>Φάουλ/αγώνα</span><b>${r.fouls ?? "—"}</b></div><div class="kpi"><span>Αγώνες</span><b>${r.n}</b></div></div>`;
    }
    if (m.h2h && m.h2h.length) {
      s2 += `<h3 class="day-sub">Τελευταίες αναμετρήσεις</h3><div class="table-wrap"><table><tbody>${m.h2h.map(x => `<tr><td>${x.date.slice(0, 7)}</td><td>${esc(x.home)} – ${esc(x.away)}</td><td class="num"><b>${x.score}</b></td>${bk ? "" : `<td class="num">🚩${x.corners ?? "—"}</td><td class="num">🟨${x.cards ?? "—"}</td>`}</tr>`).join("")}</tbody></table></div>`;
    }

    // --- Αγορές ---
    const mkRows = list => `<div class="mk head"><span>Επιλογή</span><span class="v">Πιθ.</span><span class="v">Δίκαιη</span><span class="v">Εκτ.</span><span class="v">Δική σου</span></div>` +
      list.map(s => `<div class="mk ${s.value ? "is-value" : ""}" data-sel="${esc(s.key)}|${esc(s.side)}">
        <span class="n" data-add>${esc(nice(m, s.key, s.side, s.label))} <small class="evout ${evCls(s.est_ev)}">${s.est_ev != null ? evTxt(s.est_ev) : ""}</small></span>
        <span class="v">${pct(s.p)}</span><span class="v">${f2(s.fair)}</span>
        <span class="v" title="${esc(srcTxt(s.est_src) + (s.best ? `\nΚαλύτερη: ${s.best} (${s.book})` : ""))}">${s.est ? f2(s.est) : "—"}</span>
        <input inputmode="decimal" placeholder="—" data-odds></div>`).join("");
    let s3 = `<p class="sec-sub">Γράψε την απόδοση της Stoiximan/Superbet στο κουτάκι: πράσινο = έχει αξία. Πάτα την επιλογή για να την καταγράψεις.</p>`;
    s3 += Object.entries(groups).map(([g, list], i) => `<details class="mk-group" ${i < 2 ? "open" : ""}><summary>${esc(g)}</summary>${mkRows(list)}</details>`).join("");
    if (Object.keys(sgroups).length) {
      s3 += `<h3 class="day-sub">Στατιστικά (εκτίμηση απόδοσης)</h3>`;
      s3 += Object.entries(sgroups).map(([st, G]) => `<details class="mk-group"><summary>${esc(st)}</summary>${Object.entries(G).map(([g, list]) => `<div class="mk-sub">${esc(g.split(": ")[1] || g)}</div>${mkRows(list)}`).join("")}</details>`).join("");
    }

    h += `<div data-pane="sum">${s1 || `<div class="empty-s">Δεν υπάρχουν προβλέψεις.</div>`}</div>`;
    if (tabs.some(t => t[0] === "st")) h += `<div data-pane="st" hidden>${s2}</div>`;
    h += `<div data-pane="mk" hidden>${s3}</div>`;
    if (m.players) h += `<div data-pane="pl" hidden>${playersHtml(m)}</div>`;
    openSheet(h);
    const sheet = $("#sheet");
    sheet.querySelectorAll("[data-pane-btn]").forEach(b => b.addEventListener("click", () => {
      sheet.querySelectorAll("[data-pane-btn]").forEach(x => x.classList.toggle("active", x === b));
      sheet.querySelectorAll("[data-pane]").forEach(p => { p.hidden = p.dataset.pane !== b.dataset.paneBtn; });
    }));
    sheet.querySelectorAll("[data-odds]").forEach(inp => inp.addEventListener("input", () => {
      const rowEl = inp.closest(".mk");
      const [k, side] = rowEl.dataset.sel.split("|");
      const s = allSels.find(x => x.key === k && x.side === side);
      const o = parseFloat(inp.value.replace(",", "."));
      const out = rowEl.querySelector(".evout");
      if (!o || o <= 1) { out.textContent = s.est_ev != null ? evTxt(s.est_ev) : ""; out.className = "evout " + evCls(s.est_ev); rowEl.classList.toggle("is-value", !!s.value); return; }
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
        const av = st => (st ? st.avg : "—");
        return `<details class="mk-group"><summary>${esc(name)}: μέσοι όροι</summary><div class="table-wrap"><table class="ptable"><thead><tr><th>Παίκτης</th><th class="num">Λεπτά</th><th class="num">Πόντ.</th><th class="num">Ριμπ.</th><th class="num">Ασίστ</th><th class="num">Τρίπ.</th><th class="num" title="Προσωπικά φάουλ που κάνει ο παίκτης">Προσ. φάουλ</th></tr></thead><tbody>
          ${rows.map(r => `<tr><td><b>${esc(r.name)}</b>${r.starter ? ' <span class="pill muted">5άδα</span>' : ""}</td><td class="num">${r.mins}</td><td class="num">${av(r.pts)}</td><td class="num">${av(r.reb)}</td><td class="num">${av(r.ast)}</td><td class="num">${av(r.tpm)}</td><td class="num">${av(r.fouls)}</td></tr>`).join("")}</tbody></table></div></details>`;
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
    if (isBasket(m)) return `<h2>Παίκτες</h2>${absHtml(m)}${m.props?.length ? `<div class="grid">${m.props.map(x => propBox(m, x)).join("")}</div>` : `<div class="empty-s">Καμία επιλογή παίκτη με αξία σε αυτόν τον αγώνα.</div>`}
      <p class="sec-sub" style="margin-top:12px">${esc(P.source)}. Δείχνω μόνο επιλογές σε στατιστικά όπου το μοντέλο κέρδισε στον έλεγχο. Η γραμμή της εταιρείας μπορεί να διαφέρει: διάλεξε από την κλίμακα.</p>
      ${team("home", m.home)}${team("away", m.away)}`;
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
    h += `<div class="note" style="margin-top:14px">💾 Τα στοιχήματα αποθηκεύονται σε αυτή τη συσκευή, σε δύο σημεία (με αυτόματη επαναφορά)${state.persisted ? " και ο browser τα έχει κλειδώσει ως μόνιμα" : ""}${state.restored ? ". ✅ Έγινε επαναφορά από το αντίγραφο" : ""}. Άνοιγε την εφαρμογή πάντα από το ίδιο σημείο (εικονίδιο στην αρχική οθόνη ή Safari): κάθε browser/εφαρμογή έχει δική του αποθήκευση. Με «Εξαγωγή» κρατάς και αντίγραφο σε αρχείο.</div>`;
    view.innerHTML = h;
  }

  // ---------- Δελτίο: γράφεις τις αποδόσεις της εταιρείας, βλέπεις αμέσως πού έχει αξία ----------
  const PSTAT = { pts: "Πόντοι", reb: "Ριμπάουντ", ast: "Ασίστ", tpm: "Τρίποντα", stl: "Κλεψίματα", blk: "Κοψίματα", tov: "Λάθη", pf: "Προσωπικά φάουλ (που κάνει)",
    pra: "Πόντοι+Ριμπ.+Ασίστ", pr: "Πόντοι+Ριμπάουντ", pa: "Πόντοι+Ασίστ", ra: "Ριμπάουντ+Ασίστ" };
  const slipLegs = () => store.get("vb_slip", []);
  const saveSlip = l => store.set("vb_slip", l);
  const norm = s => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const num = v => { const x = parseFloat(String(v ?? "").replace(",", ".")); return x > 1 ? x : null; };
  state.sx = state.sx || { mid: null, q: "", mq: "", pl: "" };

  function allMatches() {
    const now = Date.now() - 3 * 3600e3;
    return Object.values(state.data?.competitions || {}).flatMap(c => c.matches || []).filter(m => new Date(m.date).getTime() > now)
      .sort((a, b) => a.date.localeCompare(b.date));
  }
  function selsOf(m) { return (m.markets || []).concat(isBasket(m) ? [] : statSels(m)); }
  function playerP(m, name, k, L, side) {
    const P = m.pmodel; if (!P) return null;
    const r = [...(P.home || []), ...(P.away || [])].find(x => x.name === name);
    if (!r || r.mu[k] == null) return null;
    const po = pOver(nb(r.mu[k], P.phi[k] ?? 0.05), L);
    return { p: side === "Over" ? po : 1 - po, mu: r.mu[k], avg10: r.avg10[k], mins: r.mins, extra: r.extra, ok: (P.ok || []).includes(k) };
  }
  // ξαναϋπολογίζει την πιθανότητα με τα τρέχοντα δεδομένα (αν ο αγώνας υπάρχει ακόμα)
  function legNow(l) {
    if (l.kind === "future") {
      const [, lid, mkey, ...tt] = l.key.split(":"), team = tt.join(":");
      const x = state.fut?.leagues.find(L => L.id === lid)?.markets.find(m => m.key === mkey)?.sel.find(y => y.t === team);
      return x ? { ...l, p: x.p, fair: 1 / x.p } : l;
    }
    const m = findMatch(l.mid);
    if (!m) return l;
    if (l.kind === "player") { const r = playerP(m, l.player, l.stat, l.line, l.side); return r ? { ...l, p: r.p, pp: 0, fair: 1 / r.p, info: r } : l; }
    const s = selsOf(m).find(x => x.key === l.key && x.side === l.side);
    return s ? { ...l, p: s.p, pp: s.pp || 0, fair: s.fair, est: s.est } : l;
  }
  const verdict = ev => ev == null ? ["muted", "γράψε απόδοση"] : ev >= 0.03 ? ["value", "✅ έχει αξία"] : ev >= -0.03 ? ["solid", "➖ δίκαιη"] : ["warn", "❌ χωρίς αξία"];
  function addLeg(l) {
    const legs = slipLegs();
    if (legs.some(x => x.mid === l.mid && x.key === l.key && x.side === l.side)) return;
    legs.push({ ...l, odds: l.odds || null, id: Date.now() + Math.random() });
    saveSlip(legs);
    state.bump = true;
  }

  function renderSlip() {
    const S = state.sx, ms = allMatches();
    const m = S.mid ? findMatch(S.mid) : null;
    let L = `<div class="card sx-card"><div class="sx-h">🔎 Βρες αγώνα ή παίκτη</div>
      <input class="sx-q" data-sxq placeholder="π.χ. Arsenal, Olympiacos, Anunoby…" value="${esc(S.q)}" autocomplete="off">`;
    if (S.q.trim().length >= 2) {
      const q = norm(S.q.trim());
      const hitsM = ms.filter(x => norm(`${x.home} ${x.away} ${x.home_full || ""} ${x.away_full || ""}`).includes(q)).slice(0, 8);
      const hitsP = ms.flatMap(x => [...(x.pmodel?.home || []), ...(x.pmodel?.away || [])].filter(p => norm(p.name).includes(q)).map(p => ({ m: x, p }))).slice(0, 6);
      L += `<div class="sx-res">${hitsM.map(x => `<button class="sx-r" data-sxm="${esc(x.id)}"><span class="ri-time"><b>${hhmm(x.date)}</b><span>${dayShort(x.date)}</span></span><span class="sx-rt"><b>${esc(x.home)} – ${esc(x.away)}</b><small>${esc(COMP[x.comp] || "")}</small></span></button>`).join("")}
        ${hitsP.map(({ m: x, p }) => `<button class="sx-r" data-sxm="${esc(x.id)}" data-sxp="${esc(p.name)}"><span class="ri-time"><b>🏀</b><span>${dayShort(x.date)}</span></span><span class="sx-rt"><b>${esc(p.name)}</b><small>${esc(x.home)} – ${esc(x.away)} · ~${p.mins}'</small></span></button>`).join("")}
        ${!hitsM.length && !hitsP.length ? `<div class="empty-s">Δεν βρέθηκε. Γράψε μέρος του ονόματος (λατινικά).</div>` : ""}</div>`;
    } else if (!m) {
      L += `<div class="sx-res">${ms.slice(0, 6).map(x => `<button class="sx-r" data-sxm="${esc(x.id)}"><span class="ri-time"><b>${hhmm(x.date)}</b><span>${dayShort(x.date)}</span></span><span class="sx-rt"><b>${esc(x.home)} – ${esc(x.away)}</b><small>${esc(COMP[x.comp] || "")}</small></span></button>`).join("")}</div>`;
    }
    L += `</div>`;

    if (m) {
      const sels = selsOf(m);
      const mq = norm(S.mq);
      const list = sels.filter(s => !mq || norm(nice(m, s.key, s.side, s.label) + " " + s.group).includes(mq));
      const groups = {};
      list.forEach(s => (groups[s.group] = groups[s.group] || []).push(s));
      const inSlip = new Set(slipLegs().map(l => `${l.mid}|${l.key}|${l.side}`));
      L += `<div class="card sx-card"><div class="sx-mh"><div><div class="sx-h">${esc(m.home)} – ${esc(m.away)}</div><small>${esc(COMP[m.comp] || "")} · ${dt(m.date)}</small></div>
          <button class="btn sm ghost" data-sxclose>✕</button></div>`;
      if (m.pmodel) {
        const players = [...(m.pmodel.home || []).map(p => ({ ...p, t: m.home })), ...(m.pmodel.away || []).map(p => ({ ...p, t: m.away }))];
        const pl = players.find(p => p.name === S.pl) || null;
        L += `<div class="sx-pl"><div class="sx-sub">🏀 Γραμμή παίκτη (όπως τη δίνει η εταιρεία)</div>
          <div class="sx-plg">
            <select data-sxpl><option value="">Παίκτης…</option>${players.map(p => `<option ${p.name === S.pl ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select>
            <select data-sxst>${Object.entries(PSTAT).map(([k, v]) => `<option value="${k}" ${S.st === k ? "selected" : ""}>${v}</option>`).join("")}</select>
            <input data-sxline inputmode="decimal" placeholder="Γραμμή π.χ. 9.5" value="${esc(S.line || "")}">
            <input data-sxpodds inputmode="decimal" placeholder="Απόδοση" value="${esc(S.podds || "")}">
          </div>
          ${pl ? `<div class="sx-plinfo">${esc(pl.name)} (${esc(pl.t)}) · ~${pl.mins}'${pl.extra >= 1 ? ` (+${pl.extra}' λόγω απουσίας)` : ""} · μ.ό. 10: ${pl.avg10[S.st || "pts"]} · μοντέλο: <b>${pl.mu[S.st || "pts"]}</b></div>` : ""}
          <div class="sx-plb"><button class="btn sm" data-sxadd="Over">+ Over</button><button class="btn sm ghost" data-sxadd="Under">+ Under</button></div></div>`;
      }
      L += `<input class="sx-q sm" data-sxmq placeholder="Φίλτρο αγορών: π.χ. over 2.5, κόρνερ, γκολ-γκολ" value="${esc(S.mq)}">`;
      L += Object.entries(groups).map(([g, l], i) => `<details class="mk-group" ${i < 3 || mq ? "open" : ""}><summary>${esc(g)}</summary>
          ${l.map(s => { const k = `${m.id}|${s.key}|${s.side}`; return `<div class="sx-sel ${inSlip.has(k) ? "in" : ""}"><span>${esc(nice(m, s.key, s.side, s.label))}</span><small>${pct(s.p)} · δίκαιη ${f2(s.fair)}</small>
            <button class="btn sm ${inSlip.has(k) ? "ghost" : ""}" data-sxsel="${esc(s.key)}|${esc(s.side)}">${inSlip.has(k) ? "✓" : "+"}</button></div>`; }).join("")}</details>`).join("") || `<div class="empty-s">Καμία αγορά με αυτό το φίλτρο.</div>`;
      L += `</div>`;
    }

    // --- το δελτίο ---
    const legs = slipLegs().map(legNow);
    let R = `<div class="card sx-card sx-slip"><div class="pop-grab"></div><div class="sx-mh"><div class="sx-h">🧾 Το δελτίο σου</div><div class="sx-mhr">${legs.length ? `<button class="btn sm ghost" data-sxclear>Άδειασμα</button>` : ""}<button class="btn sm ghost sx-min" data-sxmin aria-label="Κλείσιμο">▾</button></div></div>`;
    if (!legs.length) R += `<div class="empty-s">Πρόσθεσε επιλογές από αριστερά. Μετά γράψε την απόδοση που βλέπεις στη Stoiximan/Superbet.</div>`;
    let O = 1, P = 1, all = true, Og = 1, Pg = 1, ng = 0;
    const mids = {};
    legs.forEach(l => { mids[l.mid] = (mids[l.mid] || 0) + 1; });
    R += legs.map(l => {
      const o = num(l.odds), ev = o ? l.p * o + (l.pp || 0) - 1 : null, [cls, txt] = verdict(ev);
      P *= l.p;
      if (o) { O *= o; if (ev >= -0.03) { Og *= o; Pg *= l.p; ng++; } } else all = false;
      return `<div class="sx-leg">
        <div class="sx-lt"><b>${esc(l.label)}</b><small>${esc(l.match)}${l.kind === "future" ? "" : ` · ${hhmm(l.date)}`}</small>
          <small>Πιθανότητα <b>${pct(l.p)}</b> · δίκαιη <b>${f2(1 / l.p)}</b>${l.info ? ` · μοντέλο ${l.info.mu} (μ.ό.10 ${l.info.avg10})${l.info.ok ? "" : " · ⚠️ στατιστικό που δεν πέρασε τον έλεγχο"}` : ""}${mids[l.mid] > 1 ? " · ⚠️ ίδιος αγώνας" : ""}</small></div>
        <div class="sx-lr"><input inputmode="decimal" placeholder="απόδοση" value="${esc(l.odds || "")}" data-sxodds="${l.id}">
          <span class="pill ${cls}">${ev == null ? txt : `${txt} ${evTxt(ev)}`}</span>
          <button class="sx-x" data-sxdel="${l.id}" title="Αφαίρεση">✕</button></div></div>`;
    }).join("");
    if (legs.length) {
      const ev = all ? P * O - 1 : null;
      R += `<div class="sx-sum"><div><span>Απόδοση</span><b>${all ? f2(O) : "—"}</b></div><div><span>Πιθανότητα</span><b>${pct(P)}</b></div>
        <div><span>Αξία (EV)</span><b class="${evCls(ev)}">${evTxt(ev)}</b></div></div>`;
      if (all && ng && ng < legs.length) R += `<div class="note sx-tip">💡 Χωρίς τις επιλογές ❌: απόδοση <b>${f2(Og)}</b>, πιθανότητα <b>${pct(Pg)}</b>, αξία <b class="${evCls(Pg * Og - 1)}">${evTxt(Pg * Og - 1)}</b>.</div>`;
      if (Object.values(mids).some(n => n > 1)) R += `<div class="note sx-tip">⚠️ Επιλογές από τον ίδιο αγώνα επηρεάζουν η μία την άλλη: η πραγματική πιθανότητα μπορεί να διαφέρει.</div>`;
      R += `<div class="sx-act"><input data-sxstake inputmode="decimal" placeholder="Ποσό €" value="${esc(store.get("vb_last_stake", ""))}">
        <span class="sx-ret">${all && num(store.get("vb_last_stake", "")) ? `Επιστροφή ${(O * parseFloat(String(store.get("vb_last_stake", "")).replace(",", "."))).toFixed(2)}€` : ""}</span>
        <button class="btn" data-sxsave ${all ? "" : "disabled"}>Καταγραφή</button></div>`;
    }
    R += `</div>`;
    view.innerHTML = `<div class="sx ${state.slipOpen ? "pop-open" : ""}">${`<div class="sx-col">${L}</div>`}<div class="sx-col sx-side" id="sxSide">${R}</div></div>`;
    const side = $("#sxSide"); if (side && state.sxScroll) side.scrollTop = state.sxScroll;
    updateFab();
  }

  // ---------- πλωτό κουμπί δελτίου (κινητό): ανοίγει/κλείνει μικρό παράθυρο ----------
  function updateFab() {
    const fab = $("#slipFab"); if (!fab) return;
    const legs = slipLegs().map(legNow);
    const show = state.tab === "slip" || legs.length > 0;
    fab.hidden = !show;
    if (!show) return;
    const O = legs.reduce((a, l) => a * (num(l.odds) || 1), 1), all = legs.length && legs.every(l => num(l.odds));
    const P = legs.reduce((a, l) => a * l.p, 1), open = !!state.slipOpen && state.tab === "slip";
    fab.classList.toggle("on", open);
    fab.innerHTML = `<span class="fab-n">${legs.length}</span><span class="fab-t"><b>Δελτίο</b><small>${legs.length ? (all ? `απόδοση ${f2(O)} · ${pct(P)}` : `πιθανότητα ${pct(P)}`) : "άδειο"}</small></span><span class="fab-c">${open ? "▾" : "▴"}</span>`;
    if (state.bump) { fab.classList.remove("bump"); void fab.offsetWidth; fab.classList.add("bump"); state.bump = false; }
  }
  function setSlipOpen(v) {
    state.slipOpen = v;
    const sx = $(".sx"); if (sx) sx.classList.toggle("pop-open", v);
    $("#popBack")?.classList.toggle("open", v && state.tab === "slip" && innerWidth < 1000);
    updateFab();
  }
  $("#slipFab")?.addEventListener("click", () => {
    if (state.tab !== "slip") { state.tab = "slip"; store.set("vb_tab", "slip"); syncTabs(); render(); setSlipOpen(true); return; }
    setSlipOpen(!state.slipOpen);
  });
  $("#popBack")?.addEventListener("click", () => setSlipOpen(false));

  // ---------- κλείσιμο με σύρσιμο προς τα κάτω (καρτέλα αγώνα / δελτίο) ----------
  function swipeClose(getEl, onClose) {
    let y0 = null, dy = 0, el = null, t0 = 0;
    document.addEventListener("touchstart", e => {
      el = getEl(); if (!el || !el.contains(e.target)) { el = null; return; }
      if (el.scrollTop > 2 || e.target.closest("input,select,textarea")) { el = null; return; }
      y0 = e.touches[0].clientY; dy = 0; t0 = Date.now();
    }, { passive: true });
    document.addEventListener("touchmove", e => {
      if (!el || y0 === null) return;
      dy = e.touches[0].clientY - y0;
      if (dy <= 0) { el.style.transform = ""; el.style.transition = ""; y0 = null; return; }
      e.preventDefault();
      el.style.transition = "none"; el.style.transform = `translateY(${dy}px)`;
    }, { passive: false });
    document.addEventListener("touchend", () => {
      if (!el || y0 === null) { el = null; return; }
      const fast = dy > 50 && dy / Math.max(Date.now() - t0, 1) > 0.6;
      el.style.transition = ""; el.style.transform = "";
      if (dy > 110 || fast) onClose();
      el = null; y0 = null; dy = 0;
    });
  }
  swipeClose(() => $("#sheet").classList.contains("open") ? $("#sheet") : null, () => closeSheet());
  swipeClose(() => state.tab === "slip" && state.slipOpen && innerWidth < 1000 ? $("#sxSide") : null, () => setSlipOpen(false));

  view.addEventListener("input", e => {
    if (state.tab !== "slip") return;
    const t = e.target;
    state.sxScroll = $("#sxSide")?.scrollTop || 0;
    const keep = (sel) => { const el = $(sel); if (el) { el.focus(); const v = el.value; el.value = ""; el.value = v; } };
    if (t.matches("[data-sxq]")) { state.sx.q = t.value; renderSlip(); keep("[data-sxq]"); }
    else if (t.matches("[data-sxmq]")) { state.sx.mq = t.value; renderSlip(); keep("[data-sxmq]"); }
    else if (t.matches("[data-sxline]")) { state.sx.line = t.value; }
    else if (t.matches("[data-sxpodds]")) { state.sx.podds = t.value; }
    else if (t.matches("[data-sxodds]")) {
      const legs = slipLegs(), l = legs.find(x => String(x.id) === t.dataset.sxodds);
      if (l) { l.odds = t.value; saveSlip(legs); }
      const pos = t.selectionStart; renderSlip();
      const el = $(`[data-sxodds="${t.dataset.sxodds}"]`); if (el) { el.focus(); el.setSelectionRange(pos, pos); }
    } else if (t.matches("[data-sxstake]")) { store.set("vb_last_stake", t.value); const pos = t.selectionStart; renderSlip(); const el = $("[data-sxstake]"); if (el) { el.focus(); el.setSelectionRange(pos, pos); } }
  });
  view.addEventListener("change", e => {
    if (state.tab !== "slip") return;
    if (e.target.matches("[data-sxpl]")) { state.sx.pl = e.target.value; renderSlip(); }
    if (e.target.matches("[data-sxst]")) { state.sx.st = e.target.value; renderSlip(); }
  });
  view.addEventListener("click", e => {
    if (state.tab !== "slip") return;
    const t = e.target;
    const mb = t.closest("[data-sxm]");
    if (mb) { state.sx.mid = mb.dataset.sxm; state.sx.q = ""; state.sx.mq = ""; state.sx.pl = mb.dataset.sxp || ""; return renderSlip(); }
    if (t.closest("[data-sxclose]")) { state.sx.mid = null; return renderSlip(); }
    if (t.closest("[data-sxmin]")) return setSlipOpen(false);
    state.sxScroll = $("#sxSide")?.scrollTop || 0;
    const sb = t.closest("[data-sxsel]");
    if (sb) {
      const m = findMatch(state.sx.mid), [key, side] = sb.dataset.sxsel.split("|");
      const s = selsOf(m).find(x => x.key === key && x.side === side);
      if (s) addLeg({ mid: m.id, key, side, label: nice(m, key, side, s.label), match: `${m.home} – ${m.away}`, date: m.date, comp: m.comp, p: s.p, pp: s.pp || 0 });
      return renderSlip();
    }
    const pa = t.closest("[data-sxadd]");
    if (pa) {
      const m = findMatch(state.sx.mid), S = state.sx, k = S.st || "pts", L = num(S.line) || parseFloat(String(S.line || "").replace(",", "."));
      if (!S.pl || !(L > 0)) { alert("Διάλεξε παίκτη και γράψε τη γραμμή (π.χ. 9.5)."); return; }
      const side = pa.dataset.sxadd, r = playerP(m, S.pl, k, L, side);
      if (!r) { alert("Δεν υπάρχει πρόβλεψη για αυτόν τον παίκτη."); return; }
      addLeg({ kind: "player", mid: m.id, key: `P:${S.pl}:${k}:${L}`, side, player: S.pl, stat: k, line: L, label: `${S.pl}: ${PSTAT[k]} ${side} ${L}`,
        match: `${m.home} – ${m.away}`, date: m.date, comp: m.comp, p: r.p, pp: 0, odds: S.podds || null });
      S.podds = ""; return renderSlip();
    }
    const d = t.closest("[data-sxdel]");
    if (d) { saveSlip(slipLegs().filter(x => String(x.id) !== d.dataset.sxdel)); return renderSlip(); }
    if (t.closest("[data-sxclear]") && confirm("Άδειασμα δελτίου;")) { saveSlip([]); return renderSlip(); }
    if (t.closest("[data-sxsave]")) {
      const legs = slipLegs().map(legNow), O = legs.reduce((a, l) => a * (num(l.odds) || 1), 1), P = legs.reduce((a, l) => a * l.p, 1);
      return openBetForm({ match: legs.length > 1 ? `Δελτίο (${legs.length})` : legs[0].match, selection: legs.map(l => `${l.match}: ${l.label} @${l.odds}`).join(" | "),
        odds: O.toFixed(2), p: P, group: "Δελτίο", date: legs.map(l => l.date).sort()[0] });
    }
  });


  // ---------- Σεζόν: μακροχρόνια (προσομοίωση της υπόλοιπης σεζόν) ----------
  state.fs = state.fs || { lg: store.get("vb_fut", "E0"), open: {}, row: null };
  const FUT_FB_COLS = L => {
    const mk = Object.fromEntries(L.markets.map(m => [m.key, m]));
    const cols = [["win", "Πρωτ.", 1, "top"], [L.markets.find(m => m.key === "t4") ? "t4" : "t2", L.markets.find(m => m.key === "t4") ? "Top 4" : "Top 2", L.markets.find(m => m.key === "t4") ? 4 : 2, "top"]];
    const rel = L.markets.find(m => /^b\d/.test(m.key));
    if (rel) cols.push([rel.key, "Υποβ.", +rel.key.slice(1), "bot"]);
    return cols;
  };
  const sumTop = (d, k) => d.slice(0, k).reduce((a, b) => a + b, 0);
  const sumBot = (d, k) => d.slice(d.length - k).reduce((a, b) => a + b, 0);
  const futLegKey = (L, m, t) => `F:${L.id}:${m}:${t}`;
  function futSel(L, m, x, inSlip) {
    const k = futLegKey(L, m.key, x.t), w = Math.max(2, Math.round(x.p * 100));
    const mkt = x.mkt != null ? `<small class="fz-mkt">αγορά ${pct(x.mkt)}${x.p > x.mkt * 1.15 ? " · μοντέλο πιο αισιόδοξο" : x.p < x.mkt * 0.87 ? " · μοντέλο πιο επιφυλακτικό" : ""}</small>` : "";
    return `<div class="fz-s"><div class="fz-st"><b>${esc(x.t)}</b><small>δίκαιη ${f2(x.fair)} · συμφέρει από <b>${f2(x.min_odds)}</b></small>${mkt}
        <span class="fz-bar"><i style="width:${w}%"></i></span></div>
      <div class="fz-sr"><b class="${pCls(x.p)}">${x.p >= 0.995 ? ">99%" : x.p < 0.01 ? "<1%" : pct(x.p)}</b>
        <button class="btn sm ${inSlip.has(k) ? "ghost" : ""}" data-fadd="${esc(L.id)}|${esc(m.key)}|${esc(x.t)}">${inSlip.has(k) ? "✓" : "+"}</button></div></div>`;
  }
  function renderFutures() {
    const F = state.fut, FS = state.fs;
    if (!F || !F.leagues?.length) { view.innerHTML = `<div class="empty"><b>Δεν υπάρχουν ακόμα μακροχρόνια</b>Θα εμφανιστούν στην επόμενη ενημέρωση.</div>`; return; }
    const L = F.leagues.find(x => x.id === FS.lg) || F.leagues[0];
    const inSlip = new Set(slipLegs().map(l => l.key));
    const chip = x => `<button class="fz-c ${x.id === L.id ? "active" : ""}" data-flg="${esc(x.id)}">${esc(x.name)}</button>`;
    let h = `<section class="sec"><div class="sec-h"><h2>🏆 Σεζόν</h2></div><p class="sec-sub">Μακροχρόνια στοιχήματα: η υπόλοιπη σεζόν παίζεται ${(F.nsim || 10000).toLocaleString("el-GR")} φορές στον υπολογιστή, αγώνα-αγώνα, με τη δύναμη κάθε ομάδας. Η πιθανότητα = πόσες φορές συνέβη.</p>
      <div class="fz-lg"><span class="fz-lgt">⚽</span>${F.leagues.filter(x => x.sport !== "basketball").map(chip).join("")}</div>
      <div class="fz-lg"><span class="fz-lgt">🏀</span>${F.leagues.filter(x => x.sport === "basketball").map(chip).join("")}</div></section>`;
    h += `<div class="card fz-head"><div><div class="fz-t">${L.sport === "basketball" ? "🏀" : "⚽"} ${esc(L.name)}</div>
        <small>Έχει παιχτεί το ${pct(L.progress)} της κανονικής περιόδου · μένουν ${L.rem} αγώνες</small></div>
        <span class="fz-prog"><i style="width:${Math.round(L.progress * 100)}%"></i></span></div>`;
    if (L.note) h += `<div class="note">${esc(L.note)}</div>`;
    h += `<div class="fz-grid">${L.markets.map(m => {
      const open = FS.open[L.id + m.key], list = open ? m.sel : m.sel.slice(0, 5);
      return `<div class="card fz-m"><div class="fz-mh">${esc(m.label)}</div>${m.note ? `<div class="wx">${esc(m.note)}</div>` : ""}
        ${list.map(x => futSel(L, m, x, inSlip)).join("")}
        ${m.sel.length > 5 ? `<button class="more" data-fmore="${esc(L.id + m.key)}">${open ? "Λιγότερα" : `Όλες (${m.sel.length})`}</button>` : ""}</div>`;
    }).join("")}</div>`;
    if (L.h2h?.length) {
      const open = FS.open[L.id + "h2h"], list = open ? L.h2h : L.h2h.slice(0, 6);
      h += `<div class="card fz-m fz-wide"><div class="fz-mh">⚔️ Ποιος τερματίζει ψηλότερα</div>
        ${list.map(x => { const fa = x.p >= 0.5, t = fa ? x.a : x.b, p = fa ? x.p : 1 - x.p, o = fa ? x.b : x.a; return `<div class="fz-s"><div class="fz-st"><b>${esc(t)}</b> <small>πάνω από ${esc(o)} · δίκαιη ${f2(1 / p)} · συμφέρει από <b>${f2(1.08 / p)}</b></small>
          <span class="fz-bar"><i style="width:${Math.round(p * 100)}%"></i></span></div><div class="fz-sr"><b class="${pCls(p)}">${pct(p)}</b></div></div>`; }).join("")}
        <button class="more" data-fmore="${esc(L.id)}h2h">${open ? "Λιγότερα" : `Όλα (${L.h2h.length})`}</button></div>`;
    }
    // βαθμολογία + προσομοίωση
    const fb = L.sport !== "basketball", cols = fb ? FUT_FB_COLS(L) : L.cols;
    let cur = null;
    h += `<h2 style="margin-top:22px">Βαθμολογία & τελική εκτίμηση</h2><div class="table-wrap"><table class="fz-tbl"><thead><tr><th>#</th><th>Ομάδα</th>${fb ? `<th class="num">Αγ.</th><th class="num">Β</th><th class="num">Τελ. Β</th>` : `<th class="num">Ν-Η</th><th class="num">Τελ. Ν</th>`}${cols.map(c => `<th class="num">${c[1]}</th>`).join("")}</tr></thead><tbody>`;
    L.table.forEach((r, i) => {
      if (r.conf && r.conf !== cur) { cur = r.conf; h += `<tr class="fz-conf"><td colspan="9">${r.conf === "East" ? "Ανατολή" : "Δύση"}</td></tr>`; }
      const vals = fb ? cols.map(c => c[3] === "top" ? sumTop(r.dist, c[2]) : sumBot(r.dist, c[2])) : cols.map(c => r[c[0]]);
      const rk = r.conf ? L.table.filter(x => x.conf === r.conf).indexOf(r) + 1 : i + 1;
      h += `<tr class="click" data-frow="${esc(r.t)}"><td>${rk}</td><td><b>${esc(r.t)}</b></td>${fb ? `<td class="num">${r.g}</td><td class="num"><b>${r.pts}</b></td><td class="num">${r.xpts}</td>` : `<td class="num">${r.w}-${r.l}</td><td class="num">${r.xw}</td>`}
        ${vals.map(v => `<td class="num ${v >= 0.5 ? "fz-hi" : v >= 0.15 ? "fz-md" : "fz-lo"}">${v >= 0.995 ? ">99%" : v < 0.005 ? "—" : pct(v)}</td>`).join("")}</tr>`;
      if (FS.row === r.t) {
        const dist = r.dist ? `<div class="fz-dist">${r.dist.map((d, k) => `<span title="${k + 1}η: ${pct(d)}"><i style="height:${Math.max(2, Math.round(d * 100))}%"></i><small>${k + 1}</small></span>`).join("")}</div>` : "";
        h += `<tr class="fz-x"><td colspan="9">${dist ? `<div class="fz-xl">Πιθανότητα για κάθε θέση</div>${dist}` : ""}
          <div class="fz-xl">${esc(L.lines_label)}: Over/Under</div><div class="fz-lines">${r.lines.map(([ln, po]) => `<span class="lad"><b>Over ${ln}</b> ${pct(po)} · από <b>${f2(1.08 / Math.max(po, 0.01))}</b></span><span class="lad"><b>Under ${ln}</b> ${pct(1 - po)} · από <b>${f2(1.08 / Math.max(1 - po, 0.01))}</b></span>`).join("")}</div></td></tr>`;
      }
    });
    h += `</tbody></table></div><div class="note" style="margin-top:8px">Πάτα μια ομάδα για την πιθανότητα κάθε θέσης και Over/Under ${fb ? "βαθμών" : "νικών"}. «Συμφέρει από» = δίκαιη απόδοση +8%: στα μακροχρόνια τα χρήματα μένουν δεσμευμένα μήνες και η αβεβαιότητα είναι μεγαλύτερη, οπότε θέλουμε μεγαλύτερο περιθώριο.
      ${fb ? "Δύναμη ομάδων: μείγμα αποδόσεων κλεισίματος (Pinnacle) και στατιστικών (γκολ/xG). Ελέγχθηκε σε 15 πρωταθλήματα × 4 σεζόν (240 σημεία): όταν έλεγε ~75% συνέβαινε 76%, όταν έλεγε ~85% συνέβαινε 88%." : "Έλεγχος στη EuroLeague 2023–26: βρήκε σωστά τη δυναμική των πρωταθλητριών. Play-in, playoffs και Final Four προσομοιώνονται όπως γίνονται στην πραγματικότητα."}
      Μεταγραφές, τραυματισμοί και αλλαγές προπονητή μετράνε μόνο αφού φανούν στα αποτελέσματα/αποδόσεις.</div>`;
    view.innerHTML = h;
    updateFab();
  }
  view.addEventListener("click", e => {
    if (state.tab !== "futures") return;
    const t = e.target, FS = state.fs;
    const lg = t.closest("[data-flg]"); if (lg) { const y = scrollY; FS.lg = lg.dataset.flg; FS.row = null; store.set("vb_fut", FS.lg); renderFutures(); scrollTo(0, y); return; }
    const mo = t.closest("[data-fmore]"); if (mo) { FS.open[mo.dataset.fmore] = !FS.open[mo.dataset.fmore]; return renderFutures(); }
    const fa = t.closest("[data-fadd]");
    if (fa) {
      const [lid, mkey, team] = fa.dataset.fadd.split("|");
      const L = state.fut.leagues.find(x => x.id === lid), m = L.markets.find(x => x.key === mkey), x = m.sel.find(y => y.t === team);
      const key = futLegKey(L, mkey, team), legs = slipLegs();
      if (legs.some(l => l.key === key)) saveSlip(legs.filter(l => l.key !== key));
      else addLeg({ kind: "future", mid: "F:" + lid, key, side: "", label: `${team}: ${m.label}`, match: `${L.name} (μακροχρόνιο)`, date: new Date(Date.now() + 200 * 864e5).toISOString(), comp: lid, p: x.p, pp: 0 });
      return renderFutures();
    }
    const row = t.closest("[data-frow]"); if (row) { FS.row = FS.row === row.dataset.frow ? null : row.dataset.frow; return renderFutures(); }
  });

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
    for (const [cid, c] of Object.entries(state.data?.competitions || {})) {
      const PC = c.props_check;
      if (!PC || !Object.keys(PC).length) continue;
      h += `<h2>🏀 ${esc(c.name)}: έλεγχος επιλογών παικτών</h2><div class="note">Κάθε εμφάνιση παίκτη προβλέφθηκε μόνο με τους προηγούμενους αγώνες. Γραμμή «εταιρείας» = μέσος όρος των 10 τελευταίων αγώνων. ✓ = κερδίζει καθαρά πάνω από το νεκρό σημείο απόδοσης ~1.87 (μόνο αυτά εμφανίζονται ως επιλογές).</div>
        <div class="table-wrap"><table><thead><tr><th>Στατιστικό</th><th class="num">Εμφανίσεις</th><th class="num">Λάθος μοντέλου</th><th class="num">Λάθος μ.ό.10</th><th>Επιλογές</th></tr></thead><tbody>
        ${Object.entries(PC).filter(([k]) => !k.startsWith("_")).map(([, x]) => `<tr><td><b>${esc(x.name)}</b></td><td class="num">${x.n.toLocaleString("el-GR")}</td><td class="num">${x.mae_model}</td><td class="num">${x.mae_avg10}</td><td>${x.ok ? `✓ ${pct(x.ok.hit)} σε ${x.ok.n}` : "✗ όχι"}</td></tr>`).join("")}</tbody></table></div>
        ${PC._minutes ? `<div class="note">⏱️ Απουσίες: σε ${PC._minutes.n.toLocaleString("el-GR")} εμφανίσεις με απόντα βασικό, οι συμπαίκτες της ροτέισον πήραν ~${Math.round(PC._minutes.beta * 100)}% των λεπτών του (περισσότερα όσοι έχουν ίδιο ρόλο· τα υπόλοιπα πάνε σε παίκτες του πάγκου). ${Object.values(PC._minutes.usage || {}).some(v => v > 0) ? `Αύξηση παραγωγής ανά λεπτό επιβεβαιώθηκε σε: ${Object.entries(PC._minutes.usage).filter(([, v]) => v > 0).map(([k]) => esc(PC[k]?.name || k)).join(", ")}.` : "Αύξηση παραγωγής ανά λεπτό δεν επιβεβαιώθηκε (δεν μπαίνει)."}</div>` : ""}`;
    }
    const IC = state.data?.intl?.check;
    if (IC) h += `<h2>🌍 Εθνικές ομάδες: έλεγχος μοντέλου</h2><div class="note">Ξαναπρόβλεψη ${IC.matches.toLocaleString("el-GR")} αγώνων εθνικών των τελευταίων 12 μηνών, μόνο με ό,τι ήταν γνωστό πριν από κάθε αγώνα. Σωστό φαβορί: <b>${pct(IC.hit)}</b>. Log-loss <b>${IC.logloss}</b> (χωρίς μοντέλο: ${IC.logloss_base}, μικρότερο = καλύτερο). ${state.data.intl.teams} εθνικές ομάδες.</div>
      <div class="table-wrap"><table><thead><tr><th>Πιθανότητα φαβορί</th><th class="num">Αγώνες</th><th class="num">Πρόβλεψη</th><th class="num">Έγινε</th></tr></thead><tbody>${IC.calibration.map(c => `<tr><td>${c.bucket}</td><td class="num">${c.n}</td><td class="num">${pct(c.pred)}</td><td class="num"><b>${pct(c.actual)}</b></td></tr>`).join("")}</tbody></table></div>`;
    const pr =(state.history?.preds || []).filter(p => state.comp === "ALL" || p.comp === state.comp);
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
    const sel = $("#compSel"); if (sel) sel.value = state.comp;
  }
  $("#tabs").addEventListener("click", e => { const t = e.target.closest("button"); if (!t) return; state.tab = t.dataset.tab; store.set("vb_tab", state.tab); syncTabs(); render(); });
  // σκούρο μενού διοργανώσεων (αντί για το λευκό select του browser)
  document.addEventListener("click", e => {
    const panel = $("#compPanel");
    if (!panel) return;
    if (e.target.closest("#compBtn")) { panel.hidden = !panel.hidden; if (!panel.hidden) setTimeout(() => $("#compQ")?.focus(), 30); return; }
    const it = e.target.closest("[data-cp]");
    if (it) { state.comp = it.dataset.cp; state.more = {}; store.set("vb_comp", state.comp); panel.hidden = true; render(); return; }
    if (!e.target.closest("#compPanel")) panel.hidden = true;
  });
  document.addEventListener("input", e => {
    if (e.target.id !== "compQ") return;
    const q = e.target.value.trim().toLowerCase();
    document.querySelectorAll("#compPanel .cp-i").forEach(b => { b.hidden = q && !b.dataset.q.includes(q); });
    document.querySelectorAll("#compPanel .cp-g").forEach(g => { g.hidden = ![...g.querySelectorAll(".cp-i")].some(b => !b.hidden); });
  });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && $("#compPanel")) $("#compPanel").hidden = true; });
  $("#compFilter").addEventListener("change", e => { if (e.target.id !== "compSel") return; state.comp = e.target.value; state.more = {}; store.set("vb_comp", state.comp); render(); });
  $("#backdrop").addEventListener("click", closeSheet);
  $("#sheet").addEventListener("click", e => {
    if (e.target.closest("[data-close]")) closeSheet();
    const os = e.target.closest("[data-openslip]");
    if (os) { closeSheet(); state.sx = { ...state.sx, mid: os.dataset.openslip, q: "", mq: "", pl: "" }; state.tab = "slip"; store.set("vb_tab", "slip"); syncTabs(); render(); window.scrollTo(0, 0); }
  });
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeSheet(); });

  view.addEventListener("click", e => {
    const chip = e.target.closest("[data-day]");
    if (chip) { state.day = chip.dataset.day; state.more = {}; return render(); }
    const more = e.target.closest("[data-more]");
    if (more) { state.more[more.dataset.more] = !state.more[more.dataset.more]; return render(); }
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
