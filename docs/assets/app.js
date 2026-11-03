/* Hamburg working-student dashboard – reads docs/data/*.json, no backend. */
"use strict";

// Fill in to show a credit line in the footer (leave empty to hide).
const AUTHOR = { name: "", website: "", github: "" };

const DATA_FILES = [
  "meta", "kpis", "top_skills", "skills_by_role", "top_companies", "weekly_postings",
  "hours_distribution", "language_levels", "skill_cooccurrence", "postings",
];
const ROLE_ORDER = ["data", "software", "it_ops", "other"];
const LEVEL_ORDER = ["C2", "C1", "B2", "B1", "mentioned", "not_mentioned"];
const PAGE_SIZE = 25;

const state = {
  lang: "de",
  scope: "all",
  data: {},
  table: { sort: "posted_date", dir: "desc", limit: PAGE_SIZE },
};

/* ------------------------------------------------------------------ i18n */

const I18N = {
  de: {
    skip: "Zum Inhalt springen",
    eyebrow: "Datenprojekt · Python · SQL · Visualisierung",
    title: "Werkstudenten-Jobmarkt Hamburg",
    lede: "Welche Skills suchen Hamburger Unternehmen bei Werkstudierenden in IT, Data und Software? Täglich gesammelt aus der Jobsuche-API der Bundesagentur für Arbeit.",
    updated: "Zuletzt aktualisiert",
    controls: "Ansicht",
    scopeLabel: "Stellenauswahl",
    scopeAll: "Alle Stellen",
    scopeIt: "Nur IT-Rollen",
    themeToggle: "Farbschema wechseln",
    kpiHeading: "Kennzahlen",
    chartsLabel: "Diagramme",
    scopeNoteAll: (all, it) => `Alle ${all} aktuellen Werkstudenten-Anzeigen im Umkreis von 25 km um Hamburg – davon ${it} in Data-, Software- oder IT-Rollen.`,
    scopeNoteIt: (all, it) => `Nur Data-, Software- und IT-Rollen: ${it} von ${all} aktuellen Anzeigen.`,
    kpiCurrent: "Aktuelle Anzeigen",
    kpiCurrentHint: "beim letzten Abruf online",
    kpiNew: "Neu in 7 / 30 Tagen",
    kpiNewHint: "nach Erstveröffentlichung",
    kpiCompanies: "Unternehmen",
    kpiCompaniesHint: "mit aktuellen Anzeigen",
    kpiSkills: "Anteil der Anzeigen, die nennen …",
    kpiRemote: "Remote / hybrid",
    kpiRemoteHint: "Homeoffice erwähnt",
    skillsTitle: "Die 15 meistgefragten Skills",
    skillsSub: "Anteil der aktuellen Anzeigen, die den Skill in Titel oder Beschreibung nennen. Sprachen siehe unten.",
    rolesTitle: "Skills nach Rollentyp",
    rolesSub: "Anteil der Anzeigen je Rollentyp, die den Skill nennen (Basis: IT-Rollen). Der Rollentyp wird per Schlüsselwort aus dem Stellentitel bestimmt – siehe „So funktioniert's“.",
    companiesTitle: "Unternehmen mit den meisten Anzeigen",
    companiesSub: "Aktuelle Anzeigen je Unternehmen (Top 15).",
    weeklyTitle: "Neue Anzeigen pro Woche",
    weeklySubPosted: "Nach Datum der Erstveröffentlichung, letzte 26 Wochen. Sobald genug tägliche Abrufe vorliegen, zeigt die Kurve das Datum des ersten Abrufs. Die laufende Woche ist unvollständig.",
    weeklySubSeen: "Nach Datum, an dem der tägliche Abruf die Anzeige zuerst gefunden hat, letzte 26 Wochen. Die laufende Woche ist unvollständig.",
    hoursTitle: "Wochenstunden",
    hoursSub: (pct) => `Nur ${pct} der Anzeigen nennen Wochenstunden. Bei Spannen („16–20 Std.“) zählt der Höchstwert.`,
    hoursAxis: "Stunden pro Woche",
    langTitle: "Geforderte Sprachkenntnisse",
    langSub: "Höchstes genanntes Niveau je Anzeige. „Fließend“ und „verhandlungssicher“ zählen als C1.",
    coocTitle: "Welche Skills gemeinsam gefragt werden",
    coocSub: "Anzahl der Anzeigen, die beide Skills nennen – für die 10 häufigsten Skills. In Klammern: Anzeigen mit dem Skill insgesamt.",
    tableTitle: "Aktuelle Stellenanzeigen",
    download: "CSV herunterladen",
    search: "Suche",
    searchPh: "z. B. Python, Airbus, Data",
    role: "Rollentyp",
    skill: "Skill",
    workMode: "Arbeitsmodell",
    any: "Alle",
    colTitle: "Titel",
    colCompany: "Unternehmen",
    colDate: "Veröffentlicht",
    colSkills: "Skills",
    colLink: "Link",
    noResults: "Keine Anzeigen passen zu diesen Filtern.",
    noSkills: "keine erkannt",
    showMore: (n) => `${n} weitere anzeigen`,
    tableCount: (shown, total) => `${shown} von ${total} Anzeigen`,
    openAd: "Anzeige",
    openAdLabel: (title) => `Anzeige öffnen: ${title}`,
    hoursShort: (h) => `${h} Std./Woche`,
    howTitle: "So funktioniert's",
    howSub: "Eine kleine Daten-Pipeline in Python, die täglich per GitHub Actions laufen kann.",
    p1: "Jobsuche der Bundesagentur für Arbeit, 6 Suchbegriffe, Hamburg + 25 km",
    p2t: "Roh-JSON",
    p2: "Lokal zwischengespeichert, mit Zeitstempel, nicht im Repo",
    p3t: "Bereinigung",
    p3: "Duplikate, Firmennamen, Stunden, Remote, Kontaktdaten entfernt",
    p4: "Tabellen postings, skills, posting_skills, runs",
    p5t: "SQL-Abfragen",
    p5: "Eine Datei je Kennzahl im Ordner queries/",
    p6: "Statische Seite auf GitHub Pages, liest kleine JSON-Dateien",
    methodTitle: "Methodik und Grenzen",
    source: "Datenquelle",
    builtBy: "Projekt von",
    code: "Code auf GitHub",
    tableView: "Daten als Tabelle",
    postings: "Anzeigen",
    share: "Anteil",
    week: "Woche ab",
    newPostings: "neue Anzeigen",
    hours: "Stunden",
    language: "Sprache",
    level: "Niveau",
    skillA: "Skill A",
    skillB: "Skill B",
    together: "gemeinsam",
    loadError: "Die Daten konnten nicht geladen werden. Öffne die Seite über einen Webserver (z. B. „make serve“), nicht direkt als Datei.",
    chartError: "Diagramm konnte nicht geladen werden (Plotly nicht verfügbar). Die Daten stehen in der Tabelle darunter.",
    langNames: { german: "Deutsch", english: "Englisch" },
    levels: { C2: "C2 / Muttersprache", C1: "C1 / fließend", B2: "B2 / gut", B1: "B1 / Grundkenntnisse", mentioned: "erwähnt, ohne Niveau", not_mentioned: "nicht erwähnt" },
    modes: { remote: "Remote", hybrid: "Hybrid / Homeoffice", not_stated: "Keine Angabe" },
    method: [
      "<strong>Datenquelle:</strong> nur Anzeigen aus der Jobbörse der Bundesagentur für Arbeit. Viele Unternehmen veröffentlichen Werkstudentenstellen nur auf eigenen Karriereseiten oder LinkedIn – die Zahlen zeigen also einen Ausschnitt, nicht den ganzen Markt.",
      "<strong>Suche:</strong> sechs Suchbegriffe (z. B. „Werkstudent IT“, „Working Student“), Hamburg im Umkreis von 25 km. Die Volltextsuche der API ist unscharf und liefert auch Marketing-, Steuer- oder HR-Stellen. Sie bleiben als „Sonstige“ im Datensatz; der Schalter oben blendet sie aus.",
      "<strong>Duplikate:</strong> dieselbe Anzeige taucht unter mehreren Suchbegriffen auf (141 Treffer → 102 Anzeigen). Manche Unternehmen veröffentlichen eine Stelle jeden Monat neu; Anzeigen mit gleichem normalisiertem Titel und Unternehmen werden zusammengeführt.",
      "<strong>Rollentyp:</strong> per Schlüsselwort im Titel, in fester Reihenfolge Data → Software → IT. Das ist eine grobe, aber nachvollziehbare Einteilung; die Regeln stehen in <code>dictionaries/roles.yaml</code>.",
      "<strong>Skills:</strong> ein offenes Wörterbuch mit Synonymen (<code>dictionaries/skills.yaml</code>) wird auf Titel und Beschreibung angewendet. Gezählt werden Erwähnungen – nicht, ob ein Skill Pflicht oder „nice to have“ ist. Textbausteine eines Unternehmens zählen mit. Beispiele für korrigierte Fehltreffer: „Netzwerk“ meint meist berufliches Networking, „Data Science“ meist ein Studienfach.",
      "<strong>Stunden, Remote, Bezirk:</strong> aus dem Text bzw. der Postleitzahl abgeleitet und daher nur so gut wie die Angaben in der Anzeige. Bezirke sind über Postleitzahlen angenähert.",
      "<strong>Datenschutz:</strong> Namen, E-Mail-Adressen und Telefonnummern von Ansprechpersonen werden vor dem Speichern entfernt. Beschreibungstexte werden nicht veröffentlicht – hier stehen nur Kennzahlen und Links zur Originalanzeige.",
      "<strong>Zeitreihe:</strong> die Sammlung läuft täglich und wird mit jedem Tag aussagekräftiger. Anfangs basiert die Wochenkurve auf dem Veröffentlichungsdatum der API.",
    ],
  },
  en: {
    skip: "Skip to content",
    eyebrow: "Data project · Python · SQL · Visualisation",
    title: "Hamburg Working-Student Job Market",
    lede: "Which skills do Hamburg employers ask for in IT, data and software working-student jobs? Collected daily from the German Federal Employment Agency's job search API.",
    updated: "Last updated",
    controls: "View",
    scopeLabel: "Job selection",
    scopeAll: "All jobs",
    scopeIt: "IT roles only",
    themeToggle: "Toggle colour scheme",
    kpiHeading: "Key figures",
    chartsLabel: "Charts",
    scopeNoteAll: (all, it) => `All ${all} current working-student postings within 25 km of Hamburg – ${it} of them in data, software or IT roles.`,
    scopeNoteIt: (all, it) => `Data, software and IT roles only: ${it} of ${all} current postings.`,
    kpiCurrent: "Current postings",
    kpiCurrentHint: "online at the last update",
    kpiNew: "New in 7 / 30 days",
    kpiNewHint: "by first publication",
    kpiCompanies: "Companies",
    kpiCompaniesHint: "with current postings",
    kpiSkills: "Share of postings mentioning …",
    kpiRemote: "Remote / hybrid",
    kpiRemoteHint: "home office mentioned",
    skillsTitle: "Top 15 requested skills",
    skillsSub: "Share of current postings that mention the skill in the title or description. Languages are shown below.",
    rolesTitle: "Skills by role type",
    rolesSub: "Share of postings per role type that mention the skill (IT roles only). The role type comes from keywords in the job title – see “How it works”.",
    companiesTitle: "Companies with the most postings",
    companiesSub: "Current postings per company (top 15).",
    weeklyTitle: "New postings per week",
    weeklySubPosted: "By first publication date, last 26 weeks. Once enough daily runs exist, the line switches to the date the collector first saw each posting. The current week is incomplete.",
    weeklySubSeen: "By the date the daily collector first saw each posting, last 26 weeks. The current week is incomplete.",
    hoursTitle: "Weekly hours",
    hoursSub: (pct) => `Only ${pct} of postings state weekly hours. For ranges (“16–20 h”) the upper value counts.`,
    hoursAxis: "Hours per week",
    langTitle: "Required language skills",
    langSub: "Highest level mentioned per posting. “Fluent” and “business fluent” count as C1.",
    coocTitle: "Which skills are requested together",
    coocSub: "Number of postings mentioning both skills – for the 10 most common skills. In brackets: postings with the skill overall.",
    tableTitle: "Current job postings",
    download: "Download CSV",
    search: "Search",
    searchPh: "e.g. Python, Airbus, Data",
    role: "Role type",
    skill: "Skill",
    workMode: "Work mode",
    any: "All",
    colTitle: "Title",
    colCompany: "Company",
    colDate: "Published",
    colSkills: "Skills",
    colLink: "Link",
    noResults: "No postings match these filters.",
    noSkills: "none detected",
    showMore: (n) => `Show ${n} more`,
    tableCount: (shown, total) => `${shown} of ${total} postings`,
    openAd: "Posting",
    openAdLabel: (title) => `Open posting: ${title}`,
    hoursShort: (h) => `${h} h/week`,
    howTitle: "How it works",
    howSub: "A small Python data pipeline that can run daily on GitHub Actions.",
    p1: "Federal Employment Agency job search, 6 search terms, Hamburg + 25 km",
    p2t: "Raw JSON",
    p2: "Cached locally with a timestamp, never committed",
    p3t: "Cleaning",
    p3: "Duplicates, company names, hours, remote, contact data removed",
    p4: "Tables postings, skills, posting_skills, runs",
    p5t: "SQL queries",
    p5: "One file per metric in the queries/ folder",
    p6: "Static page on GitHub Pages reading small JSON files",
    methodTitle: "Methodology and limitations",
    source: "Data source",
    builtBy: "Project by",
    code: "Code on GitHub",
    tableView: "Show data as table",
    postings: "postings",
    share: "Share",
    week: "Week of",
    newPostings: "new postings",
    hours: "Hours",
    language: "Language",
    level: "Level",
    skillA: "Skill A",
    skillB: "Skill B",
    together: "together",
    loadError: "The data could not be loaded. Open the page through a web server (e.g. “make serve”), not directly as a file.",
    chartError: "Chart could not be loaded (Plotly unavailable). The data is in the table below.",
    langNames: { german: "German", english: "English" },
    levels: { C2: "C2 / native", C1: "C1 / fluent", B2: "B2 / good", B1: "B1 / basic", mentioned: "mentioned, no level", not_mentioned: "not mentioned" },
    modes: { remote: "Remote", hybrid: "Hybrid / home office", not_stated: "Not stated" },
    method: [
      "<strong>Data source:</strong> only postings on the Federal Employment Agency's job board. Many companies publish working-student jobs only on their own career pages or LinkedIn, so the numbers show a slice of the market, not all of it.",
      "<strong>Search:</strong> six search terms (e.g. “Werkstudent IT”, “Working Student”), Hamburg within 25 km. The API's full-text search is fuzzy and also returns marketing, tax or HR jobs. They stay in the data as “Other”; the switch at the top hides them.",
      "<strong>Duplicates:</strong> the same posting appears under several search terms (141 hits → 102 postings). Some companies re-publish a job every month; postings with the same normalised title and company are merged.",
      "<strong>Role type:</strong> keywords in the title, checked in a fixed order data → software → IT. A rough but transparent split; the rules live in <code>dictionaries/roles.yaml</code>.",
      "<strong>Skills:</strong> an open dictionary with synonyms (<code>dictionaries/skills.yaml</code>) is matched against title and description. It counts mentions – not whether a skill is required or “nice to have”. Company boilerplate counts too. Examples of fixed false positives: “Netzwerk” usually means professional networking, “Data Science” usually a degree subject.",
      "<strong>Hours, remote, district:</strong> derived from the text or the postcode, so only as good as the posting. Districts are approximated from postcodes.",
      "<strong>Privacy:</strong> names, email addresses and phone numbers of contact persons are removed before storage. Description texts are never published – only metrics and links to the original posting.",
      "<strong>Time series:</strong> collection runs daily and becomes more meaningful every day. At first the weekly line uses the API's publication date.",
    ],
  },
};

const SKILL_EN = {
  "Netzwerke": "Networking", "Deutsch": "German", "Englisch": "English",
  "VBA / Makros": "VBA / Macros", "KI / GenAI": "AI / GenAI", "Windows / Active Directory": "Windows / Active Directory",
};

const t = (key, ...args) => {
  const value = I18N[state.lang][key] ?? I18N.de[key] ?? key;
  return typeof value === "function" ? value(...args) : value;
};
const locale = () => (state.lang === "de" ? "de-DE" : "en-GB");
const skillLabel = (label) => (state.lang === "en" && SKILL_EN[label]) || label;
const roleLabel = (id) => state.data.meta?.roles?.[id]?.[state.lang] ?? id;
const fmtNum = (n) => Number(n).toLocaleString(locale());
const fmtPct = (n) => (state.lang === "de"
  ? `${Number(n).toLocaleString("de-DE", { maximumFractionDigits: 0 })} %`
  : `${Math.round(Number(n))}%`);
const fmtDate = (iso, opts = { day: "2-digit", month: "short", year: "numeric" }) =>
  new Intl.DateTimeFormat(locale(), opts).format(new Date(`${iso.slice(0, 10)}T12:00:00`));

/* --------------------------------------------------------------- storage */

function store(key, value) {
  try { localStorage.setItem(key, value); } catch (e) { /* ignore */ }
}
function recall(key) {
  try { return localStorage.getItem(key); } catch (e) { return null; }
}

/* ------------------------------------------------------------ DOM helpers */

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("aria-") || k.startsWith("data-")) node.setAttribute(k, v);
    else node[k] = v;
  }
  for (const child of children) if (child != null) node.append(child);
  return node;
}

/** Add (or replace) a collapsible data table under a chart – the accessible view. */
function dataTable(cardId, headers, rows, numericCols = []) {
  const card = document.getElementById(cardId);
  card.querySelector("details.data-table")?.remove();
  const thead = el("thead", {}, el("tr", {}, ...headers.map((h, i) =>
    el("th", { scope: "col", text: h, class: numericCols.includes(i) ? "num" : "" }))));
  const tbody = el("tbody", {}, ...rows.map((r) => el("tr", {}, ...r.map((c, i) =>
    el("td", { text: String(c), class: numericCols.includes(i) ? "num" : "" })))));
  card.append(el("details", { class: "data-table" },
    el("summary", { text: t("tableView") }),
    el("div", { class: "scroll" }, el("table", {}, thead, tbody))));
}

/* --------------------------------------------------------------- theming */

function tokens() {
  const css = getComputedStyle(document.documentElement);
  const v = (name) => css.getPropertyValue(name).trim();
  return {
    surface: v("--surface"), textPrimary: v("--text-primary"), textSecondary: v("--text-secondary"),
    textMuted: v("--text-muted"), grid: v("--grid"), axis: v("--axis"),
    series: [v("--series-1"), v("--series-2"), v("--series-3")], areaFill: v("--area-fill"),
    ord: [v("--ord-1"), v("--ord-2"), v("--ord-3"), v("--ord-4"), v("--neutral-1"), v("--neutral-2")],
    ordInk: [v("--ord-ink-1"), v("--ord-ink-1"), v("--ord-ink-2"), v("--ord-ink-2"), v("--ord-ink-2"), v("--ord-ink-2")],
    seq: [v("--seq-0"), v("--seq-1"), v("--seq-2"), v("--seq-3"), v("--seq-4")],
    font: v("--font"),
  };
}

const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));

/** Linear interpolation along a colour ramp; returns [r, g, b]. */
function rampColor(colors, stops, t01) {
  const t = Math.min(1, Math.max(0, t01));
  let k = 0;
  while (k < stops.length - 2 && t > stops[k + 1]) k += 1;
  const span = (t - stops[k]) / (stops[k + 1] - stops[k]);
  const a = hexToRgb(colors[k]);
  const b = hexToRgb(colors[k + 1]);
  return a.map((c, i) => Math.round(c + (b[i] - c) * span));
}

/** WCAG relative luminance of an [r, g, b] colour. */
function luminance(rgb) {
  const [r, g, b] = rgb.map((c) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function isDark() {
  const forced = document.documentElement.dataset.theme;
  if (forced) return forced === "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/* ---------------------------------------------------------------- charts */

const PLOT_CONFIG = { displayModeBar: false, responsive: true };

function baseLayout(tok, extra = {}) {
  const axis = {
    gridcolor: tok.grid, linecolor: tok.axis, zerolinecolor: tok.axis, zerolinewidth: 1,
    tickfont: { color: tok.textMuted, size: 12 }, automargin: true, fixedrange: true,
  };
  return {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: tok.font, size: 13, color: tok.textSecondary },
    margin: { l: 8, r: 16, t: 8, b: 32 },
    separators: state.lang === "de" ? ",." : ".,",
    hoverlabel: { bgcolor: tok.surface, bordercolor: tok.axis, font: { color: tok.textPrimary, family: tok.font, size: 13 } },
    showlegend: false,
    ...extra,
    xaxis: { ...axis, ...(extra.xaxis || {}) },
    yaxis: { ...axis, ...(extra.yaxis || {}) },
  };
}

function plot(id, traces, layout) {
  const node = document.getElementById(id);
  if (!window.Plotly) {
    node.replaceChildren(el("p", { class: "chart-fallback", text: t("chartError") }));
    return;
  }
  node.style.height = `${layout.height}px`;
  window.Plotly.react(node, traces, layout, PLOT_CONFIG);
}

/** Horizontal single-series bar chart with value labels at the bar tips. */
function horizontalBars(id, labels, values, texts, hovers, tok, xSuffix = "") {
  const max = Math.max(1, ...values);
  plot(id, [{
    type: "bar", orientation: "h",
    y: labels.slice().reverse(), x: values.slice().reverse(),
    text: texts.slice().reverse(), textposition: "outside", cliponaxis: false,
    textfont: { color: tok.textPrimary, size: 12 },
    hovertext: hovers.slice().reverse(), hovertemplate: "%{hovertext}<extra></extra>",
    marker: { color: tok.series[0], cornerradius: 4 },
  }], baseLayout(tok, {
    height: labels.length * 28 + 44,
    bargap: 0.32,
    margin: { l: 8, r: 48, t: 4, b: 28 },
    xaxis: { range: [0, max * 1.12], ticksuffix: xSuffix, showgrid: true, zeroline: true },
    yaxis: { showgrid: false, ticks: "", tickfont: { color: tok.textPrimary, size: 13 } },
  }));
}

function renderSkills(tok) {
  const rows = state.data.top_skills[state.scope];
  const labels = rows.map((r) => skillLabel(r.label));
  horizontalBars("chart-skills", labels, rows.map((r) => r.share_pct), rows.map((r) => fmtPct(r.share_pct)),
    rows.map((r, i) => `<b>${labels[i]}</b><br>${fmtNum(r.postings)} ${t("postings")} · ${fmtPct(r.share_pct)}`),
    tok, state.lang === "de" ? " %" : "%");
  dataTable("card-skills", [t("skill"), t("postings"), t("share")],
    rows.map((r, i) => [labels[i], r.postings, fmtPct(r.share_pct)]), [1, 2]);
}

function renderRoles(tok) {
  const rows = state.data.skills_by_role.it.filter((r) => r.role_category !== "other");
  const totals = new Map();
  for (const r of rows) totals.set(r.skill_id, (totals.get(r.skill_id) || 0) + r.postings);
  const skillIds = [...totals.keys()].sort((a, b) => totals.get(b) - totals.get(a));
  const labelOf = Object.fromEntries(rows.map((r) => [r.skill_id, skillLabel(r.label)]));
  const roles = ROLE_ORDER.filter((role) => rows.some((r) => r.role_category === role));

  const traces = roles.map((role, i) => {
    const byId = Object.fromEntries(rows.filter((r) => r.role_category === role).map((r) => [r.skill_id, r]));
    const n = rows.find((r) => r.role_category === role).role_postings;
    const ids = skillIds.slice().reverse();
    return {
      type: "bar", orientation: "h", name: `${roleLabel(role)} (n = ${n})`,
      y: ids.map((id) => labelOf[id]), x: ids.map((id) => byId[id]?.share_pct ?? 0),
      marker: { color: tok.series[i], cornerradius: 3 },
      hovertext: ids.map((id) => `<b>${labelOf[id]}</b> · ${roleLabel(role)}<br>${fmtNum(byId[id]?.postings ?? 0)} / ${n} ${t("postings")} · ${fmtPct(byId[id]?.share_pct ?? 0)}`),
      hovertemplate: "%{hovertext}<extra></extra>",
    };
  });
  // Horizontal groups draw the first trace at the bottom: reverse so "data" sits on top,
  // and reverse the legend back so it reads data → software → IT.
  traces.reverse();
  plot("chart-roles", traces, baseLayout(tok, {
    height: skillIds.length * 46 + 70,
    barmode: "group", bargap: 0.28, bargroupgap: 0.12,
    showlegend: true,
    legend: { orientation: "h", x: 0, y: 1.02, yanchor: "bottom", traceorder: "reversed", font: { color: tok.textPrimary } },
    margin: { l: 8, r: 16, t: 36, b: 28 },
    xaxis: { ticksuffix: state.lang === "de" ? " %" : "%", rangemode: "tozero" },
    yaxis: { showgrid: false, ticks: "", tickfont: { color: tok.textPrimary, size: 13 } },
  }));
  dataTable("card-roles", [t("skill"), ...roles.map(roleLabel)],
    skillIds.map((id) => [labelOf[id], ...roles.map((role) =>
      fmtPct(rows.find((r) => r.role_category === role && r.skill_id === id)?.share_pct ?? 0))]),
    roles.map((_, i) => i + 1));
}

function renderCompanies(tok) {
  const rows = state.data.top_companies[state.scope];
  const short = (s) => (s.length > 30 ? `${s.slice(0, 29)}…` : s);
  horizontalBars("chart-companies", rows.map((r) => short(r.company)), rows.map((r) => r.postings),
    rows.map((r) => fmtNum(r.postings)),
    rows.map((r) => `<b>${r.company.replace(/</g, "&lt;")}</b><br>${fmtNum(r.postings)} ${t("postings")}`), tok);
  dataTable("card-companies", [t("colCompany"), t("postings")], rows.map((r) => [r.company, r.postings]), [1]);
}

function renderWeekly(tok) {
  const meta = state.data.meta;
  const spanDays = (new Date(meta.last_run) - new Date(meta.first_run)) / 86400000;
  const useSeen = spanDays >= 28;
  const key = useSeen ? "by_first_seen" : "by_posted_date";
  const rows = state.data.weekly_postings[state.scope];
  document.getElementById("weekly-sub").textContent = t(useSeen ? "weeklySubSeen" : "weeklySubPosted");
  const max = Math.max(1, ...rows.map((r) => r[key]));
  plot("chart-weekly", [{
    type: "scatter", mode: "lines+markers",
    x: rows.map((r) => r.week_start), y: rows.map((r) => r[key]),
    line: { color: tok.series[0], width: 2, shape: "linear" },
    marker: { color: tok.series[0], size: 8, line: { color: tok.surface, width: 2 } },
    fill: "tozeroy", fillcolor: tok.areaFill,
    hovertext: rows.map((r) => `${t("week")} ${fmtDate(r.week_start)}<br><b>${fmtNum(r[key])}</b> ${t("newPostings")}`),
    hovertemplate: "%{hovertext}<extra></extra>",
  }], baseLayout(tok, {
    height: 280,
    hovermode: "x",
    margin: { l: 8, r: 16, t: 8, b: 32 },
    xaxis: { type: "date", showgrid: false, tickformat: state.lang === "de" ? "%d.%m." : "%d %b", showspikes: true, spikemode: "across", spikethickness: 1, spikecolor: tok.axis, spikedash: "solid" },
    yaxis: { rangemode: "tozero", range: [0, max * 1.15], dtick: max > 10 ? 5 : 2 },
  }));
  dataTable("card-weekly", [t("week"), t("newPostings")], rows.map((r) => [fmtDate(r.week_start), r[key]]), [1]);
}

function renderHours(tok) {
  const rows = state.data.hours_distribution[state.scope];
  const pct = state.data.kpis[state.scope].hours_stated_pct;
  document.getElementById("hours-sub").textContent = t("hoursSub", fmtPct(pct));
  const max = Math.max(1, ...rows.map((r) => r.postings));
  plot("chart-hours", [{
    type: "bar", x: rows.map((r) => r.hours), y: rows.map((r) => r.postings),
    width: 0.9, marker: { color: tok.series[0], cornerradius: 4 },
    text: rows.map((r) => fmtNum(r.postings)), textposition: "outside", cliponaxis: false,
    textfont: { color: tok.textPrimary, size: 12 },
    hovertext: rows.map((r) => `<b>${t("hoursShort", r.hours)}</b><br>${fmtNum(r.postings)} ${t("postings")}`),
    hovertemplate: "%{hovertext}<extra></extra>",
  }], baseLayout(tok, {
    height: 260,
    margin: { l: 8, r: 16, t: 20, b: 44 },
    xaxis: { range: [0, 41], dtick: 5, showgrid: false, title: { text: t("hoursAxis"), font: { size: 12, color: tok.textMuted } } },
    yaxis: { rangemode: "tozero", range: [0, max * 1.2] },
  }));
  dataTable("card-hours", [t("hours"), t("postings")], rows.map((r) => [r.hours, r.postings]), [0, 1]);
}

function renderLanguages(tok) {
  const rows = state.data.language_levels[state.scope];
  const langs = ["german", "english"];
  const total = Object.fromEntries(langs.map((l) => [l, rows.filter((r) => r.language === l)
    .reduce((s, r) => s + r.postings, 0)]));
  const get = (l, lvl) => rows.find((r) => r.language === l && r.level === lvl)?.postings ?? 0;
  const names = I18N[state.lang].langNames;
  const traces = LEVEL_ORDER.map((lvl, i) => ({
    type: "bar", orientation: "h", name: I18N[state.lang].levels[lvl],
    y: langs.map((l) => names[l]).reverse(),
    x: langs.map((l) => (100 * get(l, lvl)) / Math.max(1, total[l])).reverse(),
    text: langs.map((l) => fmtPct((100 * get(l, lvl)) / Math.max(1, total[l]))).reverse(),
    textposition: "inside", insidetextanchor: "middle",
    insidetextfont: { color: tok.ordInk[i], size: 12 },
    marker: { color: tok.ord[i], line: { color: tok.surface, width: 2 } },
    hovertext: langs.map((l) => `<b>${names[l]}: ${I18N[state.lang].levels[lvl]}</b><br>${fmtNum(get(l, lvl))} ${t("postings")}`).reverse(),
    hovertemplate: "%{hovertext}<extra></extra>",
  }));
  plot("chart-languages", traces, baseLayout(tok, {
    height: 230, barmode: "stack", bargap: 0.45,
    showlegend: true,
    legend: { orientation: "h", x: 0, y: -0.18, yanchor: "top", traceorder: "normal", font: { color: tok.textPrimary, size: 12 } },
    uniformtext: { minsize: 11, mode: "hide" },
    margin: { l: 8, r: 16, t: 4, b: 8 },
    xaxis: { range: [0, 100], ticksuffix: state.lang === "de" ? " %" : "%", showgrid: false },
    yaxis: { showgrid: false, ticks: "", tickfont: { color: tok.textPrimary, size: 13 } },
  }));
  dataTable("card-languages", [t("language"), t("level"), t("postings")],
    langs.flatMap((l) => LEVEL_ORDER.map((lvl) => [names[l], I18N[state.lang].levels[lvl], get(l, lvl)])), [2]);
}

function renderCooccurrence(tok) {
  const { labels, matrix } = state.data.skill_cooccurrence[state.scope];
  if (!labels.length) return;
  const names = labels.map(skillLabel);
  const own = matrix.map((row, i) => row[i]);
  // On narrow screens rotated skill names collide: number the rows and use numbers as columns.
  const narrow = document.getElementById("chart-cooc").clientWidth < 560;
  const yLabels = names.map((n, i) => (narrow ? `${i + 1} · ${n} (${own[i]})` : `${n} (${own[i]})`));
  const xLabels = narrow ? names.map((_, i) => String(i + 1)) : names;
  const z = matrix.map((row, i) => row.map((v, j) => (i === j ? null : v)));
  const zmax = Math.max(1, ...z.flat().filter((v) => v != null));
  const hover = matrix.map((row, i) => row.map((v, j) => (i === j
    ? `<b>${names[i]}</b><br>${fmtNum(v)} ${t("postings")}`
    : `<b>${names[i]} + ${names[j]}</b><br>${fmtNum(v)} ${t("postings")} ${t("together")}`)));
  const s = tok.seq;
  const stops = [0, 0.25, 0.5, 0.75, 1];
  // Label colour per cell: whichever of near-black / white contrasts more with the fill.
  const annotations = [];
  z.forEach((row, i) => row.forEach((v, j) => {
    if (v == null) return;
    const fill = rampColor(s, stops, v / zmax);
    annotations.push({
      x: xLabels[j], y: yLabels[i], text: String(v), showarrow: false,
      font: { size: 12, color: luminance(fill) > 0.32 ? "#0b0b0b" : "#ffffff" },
    });
  }));
  plot("chart-cooc", [{
    type: "heatmap", z, x: xLabels, y: yLabels, zmin: 0, zmax,
    colorscale: stops.map((p, k) => [p, s[k]]),
    xgap: 2, ygap: 2, showscale: false,
    hovertext: hover, hovertemplate: "%{hovertext}<extra></extra>",
  }], baseLayout(tok, {
    height: labels.length * 38 + 130,
    annotations,
    margin: { l: 8, r: 8, t: 4, b: 8 },
    xaxis: { side: "bottom", tickangle: narrow ? 0 : -35, tickmode: "array", tickvals: xLabels, showgrid: false, ticks: "", tickfont: { color: tok.textPrimary, size: 12 } },
    yaxis: { autorange: "reversed", showgrid: false, ticks: "", tickfont: { color: tok.textPrimary, size: 12 } },
  }));
  const pairs = [];
  matrix.forEach((row, i) => row.forEach((v, j) => { if (j > i && v > 0) pairs.push([names[i], names[j], v]); }));
  pairs.sort((a, b) => b[2] - a[2]);
  dataTable("card-cooc", [t("skillA"), t("skillB"), t("postings")], pairs, [2]);
}

/* ------------------------------------------------------------------- KPIs */

/** One tile comparing the three headline skills side by side. */
function skillTile(k) {
  const item = (name, pct) => el("div", { class: "kpi-split-item" },
    el("p", { class: "kpi-value", text: fmtPct(pct) }),
    el("p", { class: "kpi-split-label", text: name }));
  return el("div", { class: "kpi kpi-wide" },
    el("p", { class: "kpi-label", text: t("kpiSkills") }),
    el("div", { class: "kpi-split" },
      item("Python", k.python_pct), item("SQL", k.sql_pct), item("Power BI", k.power_bi_pct)));
}

function renderKpis() {
  const k = state.data.kpis[state.scope];
  const tile = (label, value, hint, hero = false) => el("div", { class: `kpi${hero ? " hero" : ""}` },
    el("p", { class: "kpi-label", text: label }),
    el("p", { class: "kpi-value" }, ...value),
    el("p", { class: "kpi-hint", text: hint }));
  document.getElementById("kpis").replaceChildren(
    tile(t("kpiCurrent"), [fmtNum(k.current_postings)], t("kpiCurrentHint"), true),
    tile(t("kpiNew"), [fmtNum(k.posted_last_7_days), el("small", { text: ` / ${fmtNum(k.posted_last_30_days)}` })], t("kpiNewHint")),
    tile(t("kpiCompanies"), [fmtNum(k.companies)], t("kpiCompaniesHint")),
    skillTile(k),
    tile(t("kpiRemote"), [fmtPct(k.remote_hybrid_pct)], t("kpiRemoteHint")),
  );
  const all = state.data.kpis.all.current_postings;
  const it = state.data.kpis.it.current_postings;
  document.getElementById("scope-note").textContent =
    t(state.scope === "it" ? "scopeNoteIt" : "scopeNoteAll", fmtNum(all), fmtNum(it));
}

/* ------------------------------------------------------------------ table */

function fillSelect(id, options, keep = true) {
  const select = document.getElementById(id);
  const previous = select.value;
  select.replaceChildren(el("option", { value: "", text: t("any") }),
    ...options.map(([value, label]) => el("option", { value, text: label })));
  if (keep && [...select.options].some((o) => o.value === previous)) select.value = previous;
}

function initTableFilters() {
  const rows = state.data.postings;
  const skills = [...new Set(rows.flatMap((r) => (r.skills ? r.skills.split(", ") : [])))]
    .sort((a, b) => skillLabel(a).localeCompare(skillLabel(b), locale()));
  fillSelect("f-role", ROLE_ORDER.map((r) => [r, roleLabel(r)]));
  fillSelect("f-skill", skills.map((s) => [s, skillLabel(s)]));
  fillSelect("f-mode", Object.entries(I18N[state.lang].modes));
  document.querySelector('#f-role option[value="other"]').disabled = state.scope === "it";
}

function filteredPostings() {
  const q = document.getElementById("f-search").value.trim().toLowerCase();
  const role = document.getElementById("f-role").value;
  const skill = document.getElementById("f-skill").value;
  const mode = document.getElementById("f-mode").value;
  const { sort, dir } = state.table;
  return state.data.postings
    .filter((r) => state.scope === "all" || r.role_category !== "other")
    .filter((r) => !role || r.role_category === role)
    .filter((r) => !mode || r.work_mode === mode)
    .filter((r) => !skill || (r.skills || "").split(", ").includes(skill))
    .filter((r) => !q || [r.title, r.company, r.district, r.skills, skillLabelList(r.skills)]
      .join(" ").toLowerCase().includes(q))
    .sort((a, b) => {
      const cmp = String(a[sort] ?? "").localeCompare(String(b[sort] ?? ""), locale());
      return dir === "asc" ? cmp : -cmp;
    });
}
const skillLabelList = (s) => (s ? s.split(", ").map(skillLabel).join(" ") : "");

function renderTable() {
  const rows = filteredPostings();
  const shown = rows.slice(0, state.table.limit);
  const modes = I18N[state.lang].modes;
  document.getElementById("postings-body").replaceChildren(...shown.map((r) => {
    const meta = [r.district, roleLabel(r.role_category), modes[r.work_mode]];
    if (r.hours_max) meta.push(t("hoursShort", r.hours_max));
    const skills = r.skills ? r.skills.split(", ") : [];
    return el("tr", {},
      el("td", {}, el("span", { class: "job-title", text: r.title }), el("span", { class: "job-meta", text: meta.join(" · ") })),
      el("td", { text: r.company }),
      el("td", { class: "date", text: r.posted_date ? fmtDate(r.posted_date) : "–", "data-label": t("colDate") }),
      el("td", {}, el("div", { class: "chips" }, ...(skills.length
        ? skills.map((s) => el("span", { class: "chip", text: skillLabel(s) }))
        : [el("span", { class: "chip none", text: t("noSkills") })]))),
      el("td", {}, el("a", {
        class: "ext-link", href: r.source_url, target: "_blank", rel: "noopener noreferrer",
        text: `${t("openAd")} ↗`, "aria-label": t("openAdLabel", r.title),
      })),
    );
  }));
  document.getElementById("table-empty").hidden = rows.length > 0;
  document.getElementById("table-count").textContent = t("tableCount", fmtNum(shown.length), fmtNum(rows.length));
  const more = document.getElementById("show-more");
  more.hidden = rows.length <= shown.length;
  more.textContent = t("showMore", fmtNum(Math.min(PAGE_SIZE, rows.length - shown.length)));
  document.querySelectorAll("table.postings th").forEach((th) => {
    const key = th.querySelector("button")?.dataset.sort;
    if (key) th.setAttribute("aria-sort", key === state.table.sort ? (state.table.dir === "asc" ? "ascending" : "descending") : "none");
  });
}

/* ----------------------------------------------------------------- render */

function applyStaticText() {
  document.documentElement.lang = state.lang;
  document.title = t("title");
  document.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = t(n.dataset.i18n); });
  document.querySelectorAll("[data-i18n-aria]").forEach((n) => n.setAttribute("aria-label", t(n.dataset.i18nAria)));
  document.querySelectorAll("[data-i18n-placeholder]").forEach((n) => { n.placeholder = t(n.dataset.i18nPlaceholder); });
  document.getElementById("method-list").innerHTML = I18N[state.lang].method.map((m) => `<li>${m}</li>`).join("");
  document.querySelectorAll("[data-lang]").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.lang === state.lang)));
  document.querySelectorAll("[data-scope]").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.scope === state.scope)));

  const meta = state.data.meta;
  if (meta) {
    const time = document.getElementById("last-updated");
    time.dateTime = meta.last_run;
    time.textContent = new Intl.DateTimeFormat(locale(), {
      dateStyle: "long", timeStyle: "short", timeZone: "Europe/Berlin",
    }).format(new Date(meta.last_run));
  }
  const author = document.getElementById("author-line");
  author.replaceChildren();
  if (AUTHOR.name) {
    author.append(`${t("builtBy")} `,
      AUTHOR.website ? el("a", { href: AUTHOR.website, text: AUTHOR.name }) : AUTHOR.name);
    if (AUTHOR.github) author.append(" · ", el("a", { href: AUTHOR.github, text: t("code") }));
  }
}

function renderCharts() {
  const tok = tokens();
  for (const fn of [renderSkills, renderRoles, renderCompanies, renderWeekly, renderHours, renderLanguages, renderCooccurrence]) {
    try { fn(tok); } catch (err) { console.error(fn.name, err); }
  }
}

function renderAll() {
  applyStaticText();
  if (!state.data.kpis) return;
  renderKpis();
  initTableFilters();
  renderTable();
  renderCharts();
}

/* ----------------------------------------------------------------- events */

function bindEvents() {
  document.querySelectorAll("[data-lang]").forEach((b) => b.addEventListener("click", () => {
    state.lang = b.dataset.lang; store("lang", state.lang); renderAll();
  }));
  document.querySelectorAll("[data-scope]").forEach((b) => b.addEventListener("click", () => {
    state.scope = b.dataset.scope; store("scope", state.scope);
    if (state.scope === "it" && document.getElementById("f-role").value === "other") document.getElementById("f-role").value = "";
    state.table.limit = PAGE_SIZE; renderAll();
  }));
  document.getElementById("theme-toggle").addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    document.documentElement.dataset.theme = next; store("theme", next); renderCharts();
  });
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (!document.documentElement.dataset.theme) renderCharts();
  });
  let resizeTimer;
  window.addEventListener("resize", () => {   // heatmap switches label style at 560px
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (state.data.skill_cooccurrence) renderCooccurrence(tokens()); }, 250);
  });
  for (const id of ["f-search", "f-role", "f-skill", "f-mode"]) {
    document.getElementById(id).addEventListener(id === "f-search" ? "input" : "change", () => {
      state.table.limit = PAGE_SIZE; renderTable();
    });
  }
  document.getElementById("show-more").addEventListener("click", () => {
    state.table.limit += PAGE_SIZE; renderTable();
  });
  document.querySelectorAll("th button[data-sort]").forEach((b) => b.addEventListener("click", () => {
    const key = b.dataset.sort;
    state.table.dir = state.table.sort === key && state.table.dir === "desc" ? "asc" : "desc";
    if (state.table.sort !== key) state.table.dir = key === "posted_date" ? "desc" : "asc";
    state.table.sort = key; renderTable();
  }));
}

async function loadData() {
  const entries = await Promise.all(DATA_FILES.map(async (name) => {
    const res = await fetch(`data/${name}.json`, { cache: "no-cache" });
    if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`);
    return [name, await res.json()];
  }));
  state.data = Object.fromEntries(entries);
}

async function init() {
  const lang = recall("lang");
  if (lang === "de" || lang === "en") state.lang = lang;
  const scope = recall("scope");
  if (scope === "all" || scope === "it") state.scope = scope;
  bindEvents();
  applyStaticText();
  try {
    await loadData();
  } catch (err) {
    console.error(err);
    document.getElementById("scope-note").textContent = t("loadError");
    return;
  }
  renderAll();
}

document.addEventListener("DOMContentLoaded", init);
