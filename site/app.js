(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const view = $("#view");
  const state = { tab: "value", comp: "ALL", data: null, history: null };
  const BOOKS = ["Stoiximan", "Superbet", "Άλλη"];

  // ---------- βοηθητικά ----------
  const pct = p => (p * 100).toFixed(0) + "%";
  const f2 = x => (x == null ? "—" : Number(x).toFixed(2));
  const evTxt = ev => (ev == null ? "—" : (ev > 0 ? "+" : "") + (ev * 100).toFixed(1) + "%");
  const evCls = ev => (ev == null ? "" : ev > 0 ? "ev-pos" : "ev-neg");
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const dt = iso => new Date(iso).toLocaleString("el-GR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const COMP = { PL: "Premier League", CL: "Champions League" };
  const STAGE = { LEAGUE_STAGE: "Φάση πρωταθλήματος", PLAYOFFS: "Playoffs", LAST_16: "16 ομάδες", QUARTER_FINALS: "Προημιτελικά", SEMI_FINALS: "Ημιτελικά", FINAL: "Τελικός" };
  const formHtml = f => `<span class="form">${(f || "").split("").map(c => `<span class="${c}">${{ W: "Ν", D: "Ι", L: "Η" }[c]}</span>`).join("")}</span>`;

  const store = {
    get(k, def) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : def; } catch { return def; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* ιδιωτική περιήγηση */ } },
  };

  function matches() {
    if (!state.data) return [];
    return Object.entries(state.data.competitions)
      .filter(([c]) => state.comp === "ALL" || state.comp === c)
      .flatMap(([, v]) => v.matches)
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

  function renderValue() {
    const ms = matches();
    const values = ms.flatMap(m => m.values.map(s => ({ m, s }))).sort((a, b) => b.s.ev - a.s.ev);
    const solid = ms.flatMap(m => m.solid.slice(0, 2).map(s => ({ m, s }))).sort((a, b) => b.s.p - a.s.p).slice(0, 12);
    let h = "";
    if (!ms.length) {
      view.innerHTML = `<div class="empty"><b>Δεν υπάρχουν αγώνες ακόμα</b>Μόλις βγει το επόμενο πρόγραμμα θα εμφανιστούν εδώ.</div>`;
      return;
    }
    h += `<h2>Value επιλογές (${values.length})</h2>`;
    h += values.length
      ? `<div class="grid">${values.map(({ m, s }) => pickCard(m, s, "value")).join("")}</div>`
      : `<div class="note">Δεν βρέθηκε value στις διαθέσιμες αποδόσεις. Άνοιξε έναν αγώνα και βάλε την απόδοση της Stoiximan/Superbet για να δεις αν συμφέρει.</div>`;
    h += `<h2>Λογικές επιλογές</h2><div class="note">Υψηλή πιθανότητα με βάση τα στατιστικά. Παίζεται μόνο αν η απόδοση της στοιχηματικής είναι <b>πάνω</b> από τη δίκαιη.</div>`;
    h += `<div class="grid">${solid.map(({ m, s }) => pickCard(m, s, "solid")).join("")}</div>`;
    view.innerHTML = h;
  }

  function matchCard(m) {
    const p = Object.fromEntries(m.markets.filter(s => s.key === "1X2").map(s => [s.side, s]));
    const crest = u => (u ? `<img src="${esc(u)}" alt="" loading="lazy">` : "");
    return `<div class="card click" data-match="${m.id}">
      <div class="match-head"><span>${COMP[m.comp]}${m.stage && m.comp === "CL" ? " · " + (STAGE[m.stage] || "") : ""}</span><span>${dt(m.date)}</span></div>
      <div class="teams">
        <div class="team">${crest(m.home_crest)}${esc(m.home)}<span class="xg">xG ${f2(m.xg[0])}</span></div>
        <div class="team">${crest(m.away_crest)}${esc(m.away)}<span class="xg">xG ${f2(m.xg[1])}</span></div>
      </div>
      <div class="probs">${["1", "X", "2"].map(k => `<div class="prob"><b>${pct(p[k].p)}</b><span>${k} · ${f2(p[k].fair)}</span></div>`).join("")}</div>
      <div class="tags">${m.values.length ? `<span class="pill value">${m.values.length} value</span>` : ""}
      ${m.has_odds ? "" : `<span class="pill muted">χωρίς αποδόσεις</span>`}
      ${m.confidence !== "υψηλή" ? `<span class="pill muted">αξιοπιστία: ${m.confidence}</span>` : ""}</div></div>`;
  }

  function renderMatches() {
    const ms = matches();
    view.innerHTML = ms.length ? `<div class="grid">${ms.map(matchCard).join("")}</div>` : `<div class="empty"><b>Κανένας αγώνας</b>Δεν υπάρχουν προγραμματισμένοι αγώνες τις επόμενες μέρες.</div>`;
  }

  function renderTeams() {
    const comps = Object.entries(state.data.competitions).filter(([c]) => state.comp === "ALL" || state.comp === c);
    let h = "";
    for (const [cid, c] of comps) {
      h += `<h2>${c.name}</h2>`;
      if (c.teams && c.teams.length) {
        h += `<div class="table-wrap"><table><thead><tr><th>Ομάδα</th><th>Φόρμα</th><th class="num">xG+</th><th class="num">xG−</th><th class="num">Γκολ+</th><th class="num">Γκολ−</th><th class="num">G/G</th><th class="num">O2.5</th><th class="num">Κόρνερ</th><th class="num">Κάρτες</th><th class="num">Επίθ.</th><th class="num">Άμυνα</th></tr></thead><tbody>`;
        h += c.teams.map(t => `<tr><td><b>${esc(t.team)}</b></td><td>${formHtml(t.form)}</td><td class="num">${f2(t.xgf)}</td><td class="num">${f2(t.xga)}</td><td class="num">${f2(t.gf)}</td><td class="num">${f2(t.ga)}</td><td class="num">${pct(t.btts)}</td><td class="num">${pct(t.o25)}</td><td class="num">${f2(t.cf)}</td><td class="num">${f2(t.cards)}</td><td class="num">${f2(t.att)}</td><td class="num">${f2(t.def)}</td></tr>`).join("");
        h += `</tbody></table></div><div class="note" style="margin-top:8px">Μέσοι όροι ανά αγώνα στη φετινή σεζόν. Επίθ./Άμυνα: δείκτες ισχύος του μοντέλου (1 = μέσος όρος· άμυνα κάτω από 1 = καλύτερη).</div>`;
      }
      for (const st of c.standings || []) {
        h += `<div class="table-wrap" style="margin-top:8px"><table><thead><tr><th>#</th><th>${esc(st.group || "Βαθμολογία")}</th><th class="num">Α</th><th class="num">Ν-Ι-Η</th><th class="num">Γκολ</th><th class="num">Β</th><th>Φόρμα</th></tr></thead><tbody>`;
        h += st.rows.map(r => `<tr><td>${r.pos}</td><td><b>${esc(r.team)}</b></td><td class="num">${r.p}</td><td class="num">${r.w}-${r.d}-${r.l}</td><td class="num">${r.gf}:${r.ga}</td><td class="num"><b>${r.pts}</b></td><td>${formHtml((r.form || "").replace(/,/g, ""))}</td></tr>`).join("");
        h += `</tbody></table></div>`;
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
    const groups = {};
    m.markets.forEach(s => (groups[s.group] = groups[s.group] || []).push(s));
    const crest = u => (u ? `<img src="${esc(u)}" alt="">` : "");
    let h = `<div class="grab"></div><button class="close" data-close>✕</button>
      <div class="match-head"><span>${COMP[m.comp]}</span><span>${dt(m.date)}</span></div>
      <div class="vs"><div class="t">${crest(m.home_crest)}${esc(m.home)}</div><div class="mid">xG<br><b style="font-size:18px;color:var(--text)">${f2(m.xg[0])} – ${f2(m.xg[1])}</b></div><div class="t">${crest(m.away_crest)}${esc(m.away)}</div></div>
      <div class="tags" style="justify-content:center;margin-bottom:10px"><span class="pill muted">Κόρνερ ~${m.corners}</span><span class="pill muted">Κάρτες ~${m.cards}</span>${m.referee ? `<span class="pill muted">Διαιτ.: ${esc(m.referee)}</span>` : ""}<span class="pill muted">Αξιοπιστία: ${m.confidence}</span></div>`;
    if (hs.p || as.p) {
      h += `<h2>Σύγκριση (μ.ό. ανά αγώνα)</h2><div class="card">
        <div class="stat-row"><div class="l">${formHtml(hs.form)}</div><div class="c">Φόρμα</div><div class="r">${formHtml(as.form)}</div></div>
        ${row("xG υπέρ", hs.xgf, as.xgf)}${row("xG κατά", hs.xga, as.xga)}${row("Γκολ υπέρ", hs.gf, as.gf)}${row("Γκολ κατά", hs.ga, as.ga)}
        ${row("Σουτ στην εστία", hs.sot, as.sot)}${row("Κόρνερ υπέρ", hs.cf, as.cf)}${row("Κάρτες", hs.cards, as.cards)}
        ${row("G/G", hs.btts, as.btts, pct)}${row("Over 2.5", hs.o25, as.o25, pct)}${row("Ανέπαφη εστία", hs.cs, as.cs, pct)}</div>`;
    }
    h += `<h2>Πιθανότερα σκορ</h2><div class="scores">${m.scores.map(s => `<span><b>${s.s}</b> ${pct(s.p)}</span>`).join("")}</div>`;
    h += `<h2>Αγορές</h2><div class="note">Γράψε την απόδοση της Stoiximan/Superbet στο κουτάκι: αν βγει πράσινο, έχει value. Πάτα το όνομα της επιλογής για να την περάσεις στα στοιχήματά σου.</div>`;
    for (const [g, list] of Object.entries(groups)) {
      h += `<div class="mk-group"><h3>${esc(g)}</h3><div class="mk head"><span>Επιλογή</span><span class="v">Πιθ.</span><span class="v">Δίκαιη</span><span class="v">Αγορά</span><span class="v">Δική σου</span></div>`;
      h += list.map((s, i) => `<div class="mk ${s.value ? "is-value" : ""}" data-sel="${esc(s.key)}|${esc(s.side)}">
        <span class="n" data-add>${esc(s.label)} <small class="evout ${evCls(s.ev)}">${s.ev != null ? evTxt(s.ev) : ""}</small></span>
        <span class="v">${pct(s.p)}</span><span class="v">${f2(s.fair)}</span>
        <span class="v" title="${esc(Object.entries(s.odds || {}).map(([b, o]) => b + ": " + o).join("\n"))}">${s.best ? f2(s.best) : "—"}</span>
        <input inputmode="decimal" placeholder="—" data-odds></div>`).join("");
      h += `</div>`;
    }
    openSheet(h);
    const sheet = $("#sheet");
    sheet.querySelectorAll("[data-odds]").forEach(inp => inp.addEventListener("input", () => {
      const rowEl = inp.closest(".mk");
      const [k, side] = rowEl.dataset.sel.split("|");
      const s = m.markets.find(x => x.key === k && x.side === side);
      const o = parseFloat(inp.value.replace(",", "."));
      const out = rowEl.querySelector(".evout");
      if (!o || o <= 1) { out.textContent = s.ev != null ? evTxt(s.ev) : ""; out.className = "evout " + evCls(s.ev); rowEl.classList.toggle("is-value", s.value); return; }
      const ev = s.p * o + s.pp - 1;
      out.textContent = evTxt(ev); out.className = "evout " + evCls(ev);
      rowEl.classList.toggle("is-value", ev >= 0.03);
    }));
    sheet.querySelectorAll("[data-add]").forEach(n => n.addEventListener("click", () => {
      const rowEl = n.closest(".mk");
      const [k, side] = rowEl.dataset.sel.split("|");
      const s = m.markets.find(x => x.key === k && x.side === side);
      const typed = parseFloat((rowEl.querySelector("[data-odds]").value || "").replace(",", "."));
      openBetForm({ match: `${m.home} – ${m.away}`, comp: m.comp, date: m.date, selection: s.label, group: s.group, odds: typed || s.best || "", p: s.p });
    }));
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
    h += `<h2>Επιλογές (${picks.length})</h2>`;
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
    const card = e.target.closest("[data-match]");
    if (card) return openMatch(card.dataset.match);
    if (e.target.closest("[data-newbet]")) return openBetForm();
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
