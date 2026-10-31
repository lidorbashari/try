/* Mashup Lab v5 · מעברי מילים (wordplay / lyric-transition engine)
   Plain browser JS, no dependencies. Works in Node too (module.exports) for tests.
   Never contains lyrics: it works from TITLES only (normalised tokens), plus key/BPM/energy/sections.

   window.Wordplay = {
     index(DATA)                      → index object (tokens, concepts, idf), cached per DATA array
     autoLinks(DATA, opts)            → [{ai, bi, type, word, score, hype, conf, mix, cueA, cueB, why_he}]
     mixCheck(a, b)                   → {compatible, rel, tempoDiffPct, tempoMode, keyOk, tempoOk, eA, eB, dE, energyOk, technique, technique_he, rates}
     resolve(DATA, LINKS)             → curated links (links.json) resolved to indices, with mix + cue objects
     merge(curated, auto, opts)       → one ranked list, curated first, no duplicate pairs
     cuePlan(a, b, mix, opts)         → {cueA, cueB} objects: {sec, bar, t, mmss, he}
     previewPlan(link, DATA)          → how the app should demo it on 30 s previews: {T, style, xfMs, rates}
     TYPE_HE, TECH_HE, SEC_HE         → Hebrew labels
   }
*/
(function (root) {
  "use strict";

  /* ---------------- SPEC §7: energy + sections (same numbers as app.html) ---------------- */
  var E_BASE = { techno: 8, edm: 8, dnb: 9, techhouse: 8, house: 7, afrohouse: 6, ukg: 7, amapiano: 6, afro: 6, dancehall: 7, regg: 7, latin: 7, hiphop: 6, rnb: 4, pop: 6, ilpop: 5, mizr: 6 };
  var CLUB_G = { house: 1, techhouse: 1, afrohouse: 1, techno: 1, edm: 1, ukg: 1, dnb: 1 };
  var FAMILY = { mizr: "il", ilpop: "il", regg: "latin", latin: "latin", hiphop: "urban", rnb: "urban", pop: "urban", dancehall: "urban", afro: "africa", amapiano: "africa", afrohouse: "club", house: "club", techhouse: "club", techno: "club", edm: "club", ukg: "club", dnb: "club" };

  function energyOf(t) {
    var raw = t && t.e != null && t.e !== "" ? Number(t.e) : NaN;
    if (isFinite(raw) && raw > 0) return { e: Math.max(1, Math.min(10, Math.round(raw))), est: false };
    var e = E_BASE[t.g] != null ? E_BASE[t.g] : 6;
    var bpm = t.g === "dnb" ? t.bpm * 2 : t.bpm;
    if (bpm >= 128) e += 1; else if (bpm <= 95) e -= 1;
    return { e: Math.max(1, Math.min(10, e)), est: true };
  }
  function formOf(g) {
    if (CLUB_G[g]) return { type: "club", sec: { intro: [1, 32], groove: [33, 64], breakdown: [65, 80], drop: [81, 112], outro: [113, 144] } };
    if (g === "amapiano") return { type: "amapiano", sec: { intro: [1, 16], hook: [17, 48], logdrum: [49, 80] } };
    return { type: "song", sec: { intro: [1, 8], verse1: [9, 24], chorus1: [25, 32], verse2: [33, 48], chorus2: [49, 56], bridge: [57, 64], chorus3: [65, 80] } };
  }
  /* playing tempo: dnb rows are listed at half time (< 110) and play at 2× */
  function effBpm(t) { return t.g === "dnb" && t.bpm < 110 ? t.bpm * 2 : t.bpm; }
  function barSec(t, bpm) { return 240 / (bpm || effBpm(t)); }

  /* ---------------- key + tempo (ported from template4 / app.html) ---------------- */
  function camRel(a, b) {
    if (!a || !b) return null;
    var na = parseInt(a, 10), la = a.slice(-1), nb = parseInt(b, 10), lb = b.slice(-1);
    if (a === b) return "same";
    if (la === lb && (Math.abs(na - nb) === 1 || Math.abs(na - nb) === 11)) return "adj";
    if (na === nb && la !== lb) return "rel";
    return null;
  }
  function tempo(a, b) {
    var opts = [
      { d: Math.abs(a - b) / Math.min(a, b), mode: "1:1" },
      { d: Math.abs(a - 2 * b) / Math.min(a, 2 * b), mode: "vhalf" },
      { d: Math.abs(2 * a - b) / Math.min(2 * a, b), mode: "vdouble" }
    ];
    opts.sort(function (x, y) { return x.d - y.d; });
    return opts[0];
  }
  function targets(v, b, t) {
    if (t.mode === "vhalf") return { meet: b.bpm, vT: b.bpm * 2, bT: b.bpm };
    if (t.mode === "vdouble") return { meet: b.bpm, vT: b.bpm / 2, bT: b.bpm };
    var m = Math.round((v.bpm + b.bpm) / 2);
    return { meet: m, vT: m, bT: m };
  }
  var r1 = function (x) { return Math.round(x * 10) / 10; };

  var TECH_HE = {
    double: "דאבל דרופ", blend: "בלנד", callresp: "שאלה־תשובה בין הדקים", echo: "אקו על המילה",
    cut: "קאט על ה־1", spinback: "ספינבק", acapella: "אקפלה לדרופ", filter: "פילטר וקאט"
  };
  var TYPE_HE = { chain: "שרשרת", answer: "שאלה ותשובה", lang: "חוצה שפות", same: "אותה מילה", count: "ספירה וזמן", theme: "המשך הסיפור" };
  var SEC_HE = { intro: "אינטרו", verse1: "בית ראשון", chorus1: "פזמון ראשון", verse2: "בית שני", chorus2: "פזמון שני", bridge: "ברידג׳", chorus3: "פזמון אחרון", groove: "גרוב מרכזי", breakdown: "ברייקדאון", drop: "דרופ", outro: "אאוטרו", hook: "ההוק", logdrum: "דרופ לוג־דראם" };

  /* mixCheck(a, b): is A → B mixable, and with which technique */
  /* key fit BY EAR: Pearson correlation of the measured pitch-class profiles of the two previews (analysis.json:
     hc = harmony, vc = singing), B moved by s ∈ {0, ±1} semitones. Catalog keys are often wrong; the ear is not
     fooled by a label. Returns null when either preview has no measured profile (then the Camelot keys decide). */
  function prof12(sv) { if (!sv || String(sv).length !== 12) return null; var v = [], m = 0, i, n = 0; for (i = 0; i < 12; i++) { v.push(parseInt(String(sv).charAt(i), 16) || 0); m += v[i]; } m /= 12;
    for (i = 0; i < 12; i++) { v[i] -= m; n += v[i] * v[i]; } n = Math.sqrt(n); if (!(n > 1e-6)) return null; for (i = 0; i < 12; i++) v[i] /= n; return v; }
  function rot(a, b, s) { var c = 0; for (var i = 0; i < 12; i++) c += a[i] * b[((i + s) % 12 + 12) % 12]; return c; }
  function anOf(t) { var m = root.__analysis && root.__analysis.map, v = m && t && m[String(t.t) + " | " + String(t.a)]; return v && !v.err ? v : null; }
  function earKey(a, b) {
    var A = anOf(a), B = anOf(b); if (!A || !B) return null;
    var hA = prof12(A.hc), hB = prof12(B.hc), vA = prof12(A.vc), vB = prof12(B.vc); if (!hA || !hB) return null;
    var best = null;
    [0, 1, -1].forEach(function (s) {
      var f = .5 * rot(hA, hB, -s), w = .5;
      if (vA) { f += .25 * rot(vA, hB, -s); w += .25; }
      if (vB) { f += .25 * rot(hA, vB, -s); w += .25; }
      f /= w; var sc = f - .06 * Math.abs(s);
      if (!best || sc > best.sc) best = { semis: s, fit: Math.round(f * 100) / 100, sc: sc };
    });
    best.rel = best.fit >= .45 ? "ear" : best.fit >= .3 ? "ear-ok" : null;
    return best;
  }
  function mixCheck(a, b) {
    var rel = camRel(a.k, b.k), t = tempo(a.bpm, b.bpm), d = t.d, ear = earKey(a, b);
    if (ear) rel = ear.rel;                       /* the ear decides when both previews were measured */
    else if (a.kc === 1 || b.kc === 1) rel = null; /* key not confirmed by a second source: don't overlap */
    var keyOk = !!rel, tempoOk = d <= 0.06 + 1e-9, compatible = keyOk && tempoOk;
    var eA = energyOf(a), eB = energyOf(b), dE = eB.e - eA.e;
    var bClub = !!CLUB_G[b.g] || b.g === "amapiano";
    var tech;
    if (compatible) tech = bClub ? "double" : "blend";
    else if (keyOk && d <= 0.10) tech = "cut";
    else if (tempoOk) tech = "echo";
    else if (d <= 0.15) tech = "echo";
    else tech = (formOf(a.g).type === "song") ? "spinback" : "echo";
    var tg = targets(a, b, t);
    return {
      compatible: compatible, rel: rel, keyOk: keyOk, tempoOk: tempoOk,
      tempoDiffPct: r1(d * 100), tempoMode: t.mode, ear: ear ? ear.fit : null, semis: ear ? ear.semis : 0,
      eA: eA.e, eB: eB.e, est: eA.est || eB.est, dE: dE, energyOk: dE >= -1,
      technique: tech, technique_he: TECH_HE[tech],
      rates: compatible ? { A: tg.vT / a.bpm, B: tg.bT / b.bpm } : { A: 1, B: 1 },
      meet: compatible ? tg.meet : null
    };
  }

  /* ---------------- section-based cue plan (SPEC §7 typical bars) ---------------- */
  function mmss(s) { s = Math.max(0, Math.round(s)); return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2); }
  function cuePlan(a, b, mix, opts) {
    mix = mix || mixCheck(a, b); opts = opts || {};
    var fa = formOf(a.g), fb = formOf(b.g), tech = opts.technique || mix.technique;
    var bpmA = mix.compatible ? mix.rates.A * a.bpm : a.bpm, bpmB = mix.compatible ? mix.rates.B * b.bpm : b.bpm;
    if (a.g === "dnb" && a.bpm < 110) bpmA *= 2;
    if (b.g === "dnb" && b.bpm < 110) bpmB *= 2;
    var bA = 240 / bpmA, bB = 240 / bpmB;
    /* where A's hook word lands (end of that bar = the cut point) */
    var secA = opts.secA || (fa.type === "song" ? "chorus2" : fa.type === "club" ? "breakdown" : "hook");
    if (!fa.sec[secA]) secA = fa.type === "song" ? "chorus2" : fa.type === "club" ? "breakdown" : "hook";
    var barA = fa.sec[secA][1];
    /* where B comes in (downbeat of that bar) */
    var secB = opts.secB || (fb.type === "club" ? (tech === "blend" ? "groove" : "drop") : fb.type === "amapiano" ? "logdrum" : "chorus1");
    if (!fb.sec[secB]) secB = fb.type === "club" ? "drop" : fb.type === "amapiano" ? "logdrum" : "chorus1";
    var barB = fb.sec[secB][0];
    var tA = barA * bA, tB = (barB - 1) * bB;
    var wordA = SEC_HE[secA], wordB = SEC_HE[secB];
    var he = {
      double: ["הפזמון האחרון של A רוכב מעל הדרופ של B", "B מסונכרן; הדרופ שלו (תיבה " + barB + ", " + mmss(tB) + ") נוחת עם ההוק של A. להחליף בס על ה־1 (LOW של A למטה), 16 תיבות, ואז אקו ל־A"],
      blend: ["ב־4 התיבות האחרונות של ה" + wordA + " (תיבה " + barA + ", " + mmss(tA) + ") להוריד LOW ל־A", "B נכנס מה" + wordB + " (תיבה " + barB + ", " + mmss(tB) + ") בסנכרון; הבס מתחלף על ה־1 שאחרי המילה"],
      callresp: ["לופ של 4 פעמות על ההוק של A (" + wordA + ", תיבה " + barA + ")", "B עונה מה" + wordB + " (" + mmss(tB) + "); לחתוך את A אחרי כל משפט, 8–16 תיבות"],
      echo: ["על המילה האחרונה של ה" + wordA + " (סוף תיבה " + barA + ", " + mmss(tA) + "): אקו ½ פעמה, ומיד לסגור את A", "B על ה־1 הבא, ישר ל" + wordB + " (תיבה " + barB + ", " + mmss(tB) + "), מתחת לזנב האקו"],
      cut: ["לסגור את A בדיוק בסוף המילה, סוף ה" + wordA + " (תיבה " + barA + ", " + mmss(tA) + ")", "B יבש על ה־1, מה" + wordB + " (תיבה " + barB + ", " + mmss(tB) + ")"],
      spinback: ["מיד אחרי המילה (סוף ה" + wordA + ", " + mmss(tA) + "): ספינבק על פעמה 3–4", "B יבש על ה־1, ישר ל" + wordB + " (" + mmss(tB) + ")"],
      acapella: ["סטמס: להשאיר רק את השירה של A ל־1–2 תיבות, ההוק בסוף ה" + wordA + " (" + mmss(tA) + ")", "הבילד של B מתחת; ה" + wordB + " של B (" + mmss(tB) + ") על ה־1 אחרי המילה"],
      filter: ["HPF על A לאורך התיבה האחרונה של ה" + wordA + " (" + mmss(tA) + "), קאט על המילה", "B מלא על ה־1, מה" + wordB + " (" + mmss(tB) + ")"]
    }[tech] || ["", ""];
    return {
      cueA: { sec: secA, bar: barA, t: Math.round(tA), mmss: mmss(tA), he: he[0] },
      cueB: { sec: secB, bar: barB, t: Math.round(tB), mmss: mmss(tB), he: he[1] },
      note_he: "הערכה לפי מבנה טיפוסי של הסגנון: לבדוק באוזן"
    };
  }

  /* ---------------- title normalisation ---------------- */
  var VERSION_RX = /(\b(remix|extended|edit|version|mix|feat\.?|ft\.?|vip|radio|rework|bootleg|remaster(ed)?|live|acoustic|english|instrumental)\b|רמיקס|גרסה)/i;
  var FINALS = { "ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ" };
  function unifyFinals(w) { return w.replace(/[ךםןףץ]/g, function (c) { return FINALS[c]; }); }
  var STOP = {};
  ("the a an i you me my your of to in on and it is we be for with so da dat at im its it's u ur y'all ya are am was were that this these those our us he she his her they them as by or not no").split(" ").forEach(function (w) { STOP[w] = 1; });
  ("el la los las de del en con un una y que me te mi tu pa lo le se al por mas").split(" ").forEach(function (w) { STOP[w] = 1; });
  ("את של זה הזה זאת לא כל אני אתה הוא היא אנחנו עם על מה רק עוד גם כי אם לי לך לנו שלי שלך שלנו אז יש אין כמה כבר הנה אל").split(" ").forEach(function (w) { STOP[unifyFinals(w)] = 1; });
  /* words that look like content but are naming noise in this pool */
  var NOISE = {};
  ("again extended remix mix edit version feat ft vol pt part ii iii bzrp sessions music dj original radio").split(" ").forEach(function (w) { NOISE[w] = 1; });
  var NEG = {};
  ("dont don't never no not nothing sin without לא אל אין בלי").split(" ").forEach(function (w) { NEG[unifyFinals(w.replace(/'/g, ""))] = 1; });
  var QWORDS = {};
  ("what where who why how when whats wheres que donde quien como cuando מה מי איפה למה מדוע איך האם ממה מתי לאן").split(" ").forEach(function (w) { QWORDS[unifyFinals(w)] = 1; });
  var SHORT_OK = { "do": 1, "go": 1, "up": 1, "on": 1, "pr": 1, "mr": 1 };
  /* two-letter Latin words that matter */
  var WEAK = {};
  ("love baby girl girls boy boys bad time one up go get got like good new day man night feel do on make want need come back let don life heart way take give dance down hey low all only just big little lil real na la oh yeah").split(" ").forEach(function (w) { WEAK[w] = 1; });

  /* Hebrew lemma table (natural spelling; normalised at init) */
  var LEMMA_SRC = {
    "לילה": "לילות הלילה בלילות לילה ללילה",
    "שמחה": "שמחות השמחה שמח תשמח שמחה שמחים בשמחות",
    "מאושר": "מאושרים מאושרת מאושר",
    "משוגע": "משוגעים משוגעת משוגע להשתגע השתגע",
    "אהבה": "אהבנו אהבתי אוהב אוהבת מאוהב אהבה האהבה לאהבה מאוהבת",
    "לב": "הלב לב לבי",
    "חיים": "החיים חיים חיי החיים",
    "עולם": "העולם עולם",
    "בית": "הבית הביתה בית",
    "בנות": "הבנות בנות",
    "רקוד": "רוקדים לרקוד ריקוד רוקדת רוקד",
    "שבור": "תשבור שבורים שובר שבור",
    "מילה": "מילים מילה",
    "הולך": "הולך הולכת הולכים ללכת",
    "בוא": "תבואי תבוא כשתבוא שתבואי בואי",
    "פגש": "ניפגש נפגש",
    "נצחון": "מנצח מנצחת",
    "עיניים": "העיניים עיניים",
    "זמן": "הזמן זמן",
    "יום": "ימים יום ביום",
    "גשם": "הגשם גשם",
    "סופה": "הסופה סופה",
    "חבר": "חברות חברים חבר",
    "הגיד": "תגידי יגידו שתגידי להגיד",
    "דבר": "מדברים דבר לדבר",
    "הרגש": "מרגישה מרגיש",
    "נצח": "נצח לנצח",
    "כעס": "תכעס כועס כעס",
    "פחד": "מפחדת מפחד פחד",
    "חסר": "חסרה חסר",
    "מצא": "מצאת תמצאי מצאתי",
    "עצור": "נעצור עצור",
    "רחוב": "רחובות רחוב",
    "שעה": "השעות שעות שעה"
  };
  var LEMMA = {};
  Object.keys(LEMMA_SRC).forEach(function (k) { LEMMA_SRC[k].split(" ").forEach(function (w) { LEMMA[unifyFinals(w)] = unifyFinals(k); }); });

  /* cross-language concept dictionary: id → words (EN / ES / HE / FR / transliterated); normalised at init */
  var CONCEPT_SRC = {
    night: "night nights tonight noche nuit לילה",
    heart: "heart hearts heartbreak corazon לב",
    dance: "dance dancing dancin danz danza baila bailando רקוד",
    party: "party club discoteca disco rave raving fiesta מסיבה מסיבות מסיבת",
    paradise: "paradise heaven עדן",
    without: "without בלעדייך",
    together: "contigo conmigo לצידך side",
    home: "home casa בית",
    girls: "girls ladies chicas banyana בנות",
    rain: "rain lluvia diluvio גשם",
    storm: "storm tormenta סופה",
    summer: "summer summertime sun sunrise verano שמש",
    sea: "ocean sea mar playa beach tidal marea ים חוף",
    fire: "fire flame flames burn burning burnin inferno fuego fireworks אש",
    crazy: "crazy loco stupid psycho משוגע טירוף",
    happy: "happy joy fun feliz felices שמחה מאושר",
    time: "time timeless tiempo זמן",
    days: "days dias יום",
    today: "today hoy היום",
    forever: "forever foreva נצח",
    lights: "lights light luz strobelights apagon אור",
    dark: "dark oscuro חושך",
    miss: "miss missed extranandote חסר געגועים",
    call: "call calls telephone hotline llamo llamado 911 nokia ממתינה הלו",
    hello: "hello hola jambo הלו",
    tell: "tell say talk dile הגיד דבר",
    words: "word words kalima מילה",
    know: "know knows conoce תדעי",
    feel: "feel feeling feels הרגש",
    close: "close closer cerca קרוב",
    far: "far lejos רחוק מתרחק",
    alone: "alone lonely לבד",
    single: "single soltera soltero רווקים",
    wedding: "marry boda חתונה",
    money: "money dolla bank commas dinero כסף",
    jewels: "diamonds diamond gold 24k solitaires zahav יהלום זהב",
    magic: "magic abracadabra houdini miracle מכשפה פלא",
    angel: "angel angels מלאך",
    strangers: "strangers stranger זרים",
    friends: "friends copines amigos חבר",
    mother: "mama mami maman mom אמא מאמי",
    father: "daddy papi papasito dad אבא",
    dream: "dream dreamin dreams sueno חלום",
    wake: "wake snooze sleep",
    eyes: "eyes ojos עיניים",
    head: "head mind cabeza ראש",
    move: "move moving זז",
    up: "jump jumper bounce תרימו",
    high: "high higher highest",
    breath: "breathe breath",
    lose: "lose losing lost",
    find: "found find מצא",
    stop: "stop עצור brakes",
    leave: "leave gone vas despedida הולך נעלמת",
    come: "come coming ven בוא",
    wait: "wait waiting",
    give: "gimme give dame תן תני",
    kiss: "kiss kisses beso חיבוק",
    tears: "tears cry llorar דמעות",
    breakit: "break broken rompe שבור",
    truth: "truth honest verdad אמת",
    lie: "lie lies liar mentira שקר",
    dare: "dare חובה",
    fear: "scared afraid fear miedo פחד",
    temper: "calm mad angry כעס",
    drink: "vodka gin drank yak liquor sippin bebo mule וודקה גין שיכורים",
    ride: "tesla altima nissan scooter roadtrip drive סקוטר כביש",
    dress: "dress falda ropa closet שמלה גינסים",
    wolf: "wolf lobo זאבה",
    tarantula: "tarantula טרנטולה",
    butterfly: "butterfly butterflies papillon mariposa",
    dog: "perro dog greyhound",
    cat: "gatito kitty kittys",
    lion: "lion lions lioness",
    bandaid: "curita bandaid פלסטרים",
    queen: "queen reina מלכה diva",
    win: "champion win winner נצחון",
    world: "world mundo עולם",
    life: "life vida vie חיים",
    streets: "streets street calle רחוב",
    good: "good bien letova טוב",
    all: "all todo hakol הכל",
    sweet: "sugar sweet candy caramelo מתוק",
    memories: "memories remember nostalgia",
    moon: "moon moonlight luna ירח",
    stars: "stars starry stargazing",
    eyesface: "face פני",
    weekend: "friday saturday weekend sabado viernes שבת",
    latenight: "2am midnight שעה",
    emergency: "911 sos emergencia ayudame",
    ibiza: "ibiza",
    telaviv: "אביב"
  };
  var CONCEPT = {};   // normalised word → [concept ids]
  var LANG_HINT = {}; // normalised Spanish words, for language detection
  ("noche una amor corazon baila bailando sola soltera calle playa mar luna fuego gata perro cielo vida gente contigo conmigo sin todo dile mas pues juez senor dura rompe despacito gasolina imposible bandido nueva era pareja ano felices cumpleanos castigo amargura latina foreva porto bonito efecto perreo voy llevarte ella levanto llamado emergencia despedida somos relacion vas curita matadora borro perdedor contrato prestamo mojando asientos propuesta indecente solo bebo ayudame huellas sexo ropa fiel chantaje enamore felicito bicicleta gusta punteria contra pared verdolaga morenita extranandote sigo amarillo azul morado desesperados diluvio dejame entrar falda tranza sabe chorrito animas juro mor tormenta danza preguntó pregunto otra mudanza turista apagon mira hawai corazon dembow").split(" ").forEach(function (w) { LANG_HINT[w] = "es"; });
  ("maman copines pookie djadja desarmer nuit vie").split(" ").forEach(function (w) { LANG_HINT[w] = "fr"; });

  function normToken(w) {
    w = w.toLowerCase();
    if (/[א-ת]/.test(w)) w = unifyFinals(w);
    return w;
  }
  function normText(s) {
    s = String(s || "").toLowerCase();
    s = s.replace(/\b((?:[a-z]\.){2,}[a-z]?)(?=\s|$)/gi, function (m) { return m.replace(/\./g, ""); }); /* D.A.N.C.E → dance */
    s = s.normalize ? s.normalize("NFD").replace(/[̀-ͯ]/g, "") : s;
    s = s.replace(/[֑-ׇ]/g, "");                           /* niqqud */
    s = s.replace(/(^|\s)ת['׳’`]/g, "$1");                           /* ת'לב → לב (= את הלב) */
    s = s.replace(/['׳’`"״]/g, "");                                   /* don't → dont, ג'ינסים → גינסים */
    s = s.replace(/[^a-z0-9א-ת]+/g, " ").trim();
    return s;
  }
  function splitTitle(t) {
    var subs = [];
    var main = String(t || "").replace(/[\(\[]([^\)\]]*)[\)\]]/g, function (m, inner) {
      if (!VERSION_RX.test(inner)) subs.push(inner);
      return " ";
    }).replace(/\s+-\s+(.*?(remix|edit|version|mix|רמיקס|גרסה).*)$/i, "").replace(/\b(pt|part|vol)\.?\s*\d+\b/ig, " ").trim();
    if (!main && subs.length) main = subs.shift();
    return { main: main, subs: subs };
  }

  var CONCEPT_READY = false;
  function initConcepts(vocab) {
    if (CONCEPT_READY) return;
    Object.keys(CONCEPT_SRC).forEach(function (id) {
      CONCEPT_SRC[id].split(" ").forEach(function (w) {
        var n = normToken(normText(w).replace(/\s+/g, ""));
        if (/[א-ת]/.test(n)) { if (LEMMA[n]) n = LEMMA[n]; vocab[n] = 1; }
        (CONCEPT[n] = CONCEPT[n] || []).indexOf(id) < 0 && CONCEPT[n].push(id);
      });
    });
    Object.keys(LEMMA).forEach(function (w) { vocab[w] = 1; vocab[LEMMA[w]] = 1; });
    CONCEPT_READY = true;
  }
  var HE_P2 = ["וה", "וב", "ול", "ומ", "וש", "שה", "שב", "של", "כש", "מה", "לה", "בה", "שמ", "וכ"];
  var HE_P1 = "והבלמשכ";
  function heBase(w, vocab) {
    if (LEMMA[w]) return LEMMA[w];
    if (w.length >= 4) for (var i = 0; i < HE_P2.length; i++) {
      if (w.indexOf(HE_P2[i]) === 0) { var r2 = w.slice(2); if (LEMMA[r2]) return LEMMA[r2]; if (vocab[r2] > 1 || CONCEPT[r2]) return r2; }
    }
    if (w.length >= 3 && HE_P1.indexOf(w[0]) >= 0) { var r1x = w.slice(1); if (LEMMA[r1x]) return LEMMA[r1x]; if (vocab[r1x] > 1 || CONCEPT[r1x]) return r1x; }
    return w;
  }
  function langOf(tok) { return /[א-ת]/.test(tok) ? "he" : (LANG_HINT[tok] || "en"); }

  /* ---------------- index ---------------- */
  var CACHE = typeof WeakMap === "function" ? new WeakMap() : null;
  function index(DATA) {
    if (CACHE && CACHE.has(DATA)) return CACHE.get(DATA);
    var vocab = {};
    initConcepts(vocab);
    /* pass 1: raw Hebrew vocabulary counts (so prefix stripping only maps onto words that exist) */
    DATA.forEach(function (t) {
      normText(t.t).split(" ").forEach(function (w) { if (/[א-ת]/.test(w)) { w = unifyFinals(w); vocab[w] = (vocab[w] || 0) + 1; } });
    });
    var tracks = DATA.map(function (t, i) {
      var sp = splitTitle(t.t);
      var rawMain = normText(sp.main).split(" ").filter(Boolean);
      var mainToks = rawMain.map(function (w) { w = normToken(w); return /[א-ת]/.test(w) ? heBase(w, vocab) : w; });
      var subToks = [];
      sp.subs.forEach(function (s) { normText(s).split(" ").filter(Boolean).forEach(function (w) { w = normToken(w); subToks.push(/[א-ת]/.test(w) ? heBase(w, vocab) : w); }); });
      var surf = {};
      (String(sp.main) + " " + sp.subs.join(" ")).replace(/\b((?:[A-Za-z]\.){2,}[A-Za-z]?)(?=\s|$)/g, function (m) { return m.replace(/\./g, ""); })
        .split(/[^A-Za-z\u00C0-\u024F\u05d0-\u05ea0-9'׳’$]+/).forEach(function (o) {
          if (!o) return;
          normText(o).split(" ").filter(Boolean).forEach(function (w) { w = normToken(w); w = /[\u05d0-\u05ea]/.test(w) ? heBase(w, vocab) : w; if (!surf[w]) surf[w] = o.replace(/[$]+$/, ""); });
        });
      var isContent = function (w) {
        if (!w || STOP[w] || NOISE[w] || NEG[w] || QWORDS[w]) return false;
        if (/^\d$/.test(w)) return false;
        if (/^[a-z]+$/.test(w) && w.length < 3 && !SHORT_OK[w]) return false;
        if (/[א-ת]/.test(w) && w.length < 2) return false;
        return true;
      };
      var content = mainToks.filter(isContent);
      var subContent = subToks.filter(isContent);
      var concepts = {};
      content.concat(subContent).forEach(function (w) { (CONCEPT[w] || []).forEach(function (c) { concepts[c] = concepts[c] || w; }); });
      /* known two-word phrases */
      var joined = " " + mainToks.join(" ") + " ";
      if (/ גנ עדנ /.test(joined)) concepts.paradise = "גן עדן";
      if (/ תל אביב /.test(joined)) concepts.telaviv = "תל אביב";
      if (/ (שעה|שעות) קטנות /.test(joined)) concepts.latenight = "השעות הקטנות";
      if (/ ocean drive /.test(joined)) concepts.ride = "ocean drive";
      var nums = [];
      mainToks.forEach(function (w) { var m = w.match(/^(\d+)/); if (m) nums.push(+m[1]); });
      var langs = {};
      content.forEach(function (w) { langs[langOf(w)] = 1; });
      var lang = langs.he ? "he" : langs.es ? "es" : langs.fr ? "fr" : "en";
      if (langs.he && (langs.en || langs.fr)) lang = "mix";
      return {
        i: i, raw: t.t, main: sp.main, toks: mainToks, content: content, sub: subContent,
        first: content[0] || null, last: content[content.length - 1] || null,
        concepts: concepts, nums: nums, lang: lang, surf: surf,
        qw: mainToks.slice(0, 3).some(function (w) { return QWORDS[w] === 1; }),
        q: /\?/.test(t.t) || QWORDS[mainToks[0]] === 1 || QWORDS[mainToks[1]] === 1 && STOP[mainToks[0]] === 1,
        neg: mainToks.some(function (w) { return NEG[w]; }),
        artist: String(t.a || "").split(",")[0].trim().toLowerCase()
      };
    });
    /* document frequency per token and per concept */
    var df = {}, cdf = {};
    tracks.forEach(function (x) {
      var seen = {};
      x.content.concat(x.sub).forEach(function (w) { if (!seen[w]) { seen[w] = 1; df[w] = (df[w] || 0) + 1; } });
      Object.keys(x.concepts).forEach(function (c) { cdf[c] = (cdf[c] || 0) + 1; });
    });
    var N = DATA.length;
    var idf = function (w) { return Math.log(N / Math.max(1, df[w] || 1)); };
    var cidf = function (c) { return Math.log(N / Math.max(1, cdf[c] || 1)); };
    var byTok = {}, byConcept = {}, byFirst = {};
    tracks.forEach(function (x) {
      var seen = {};
      x.content.concat(x.sub).forEach(function (w) { if (!seen[w]) { seen[w] = 1; (byTok[w] = byTok[w] || []).push(x.i); } });
      Object.keys(x.concepts).forEach(function (c) { (byConcept[c] = byConcept[c] || []).push(x.i); });
      if (x.first) (byFirst[x.first] = byFirst[x.first] || []).push(x.i);
    });
    var ix = { N: N, tracks: tracks, df: df, cdf: cdf, idf: idf, cidf: cidf, byTok: byTok, byConcept: byConcept, byFirst: byFirst, maxIdf: Math.log(N) };
    if (CACHE) CACHE.set(DATA, ix);
    return ix;
  }

  /* ---------------- candidate generation ---------------- */
  function sameSong(A, B, xa, xb) {
    if (xa.artist && xa.artist === xb.artist) return true;   /* same first artist: a medley, not wordplay */
    var ta = xa.toks.join(" "), tb = xb.toks.join(" ");
    if (ta === tb && String(A.a).toLowerCase().split(",").some(function (s) { return String(B.a).toLowerCase().indexOf(s.trim()) >= 0; })) return true;
    return false;
  }
  function S(x, w) { return (x.surf && x.surf[w]) || w; }
  var OPP = [["without", "together"], ["alone", "together"]];
  var GENERIC_C = {};
  ("life time world good all days today come give leave tell know feel up high move lose find stop home kiss girls together heart").split(" ").forEach(function (c) { GENERIC_C[c] = 1; });
  function startsWith(arr, pre) { if (pre.length >= arr.length) return false; for (var i = 0; i < pre.length; i++) if (arr[i] !== pre[i]) return false; return true; }

  function candidates(DATA, ix) {
    var out = {}, tr = ix.tracks;
    function add(ai, bi, c) {
      if (ai === bi) return;
      var A = DATA[ai], B = DATA[bi];
      if (sameSong(A, B, tr[ai], tr[bi])) return;
      var key = ai + ">" + bi, prev = out[key];
      if (!prev || c.str > prev.str || (c.str === prev.str && c.w > prev.w)) out[key] = c;
    }
    tr.forEach(function (xa) {
      /* 1) title chain: A's last content word opens B */
      if (xa.last && ix.byFirst[xa.last]) ix.byFirst[xa.last].forEach(function (bi) {
        var xb = tr[bi]; if (xb.toks.join(" ") === xa.toks.join(" ")) return;
        var w = ix.idf(xa.last) / ix.maxIdf, weak = WEAK[xa.last] || (ix.df[xa.last] || 0) > 14;
        if (weak && xa.content.length + xb.content.length > 3) return;      /* "love … love …" is noise */
        if (weak && xa.content.length > 1 && xb.content.length > 1) return;
        add(xa.i, bi, { type: "chain", word: S(xa, xa.last), str: weak ? 2 : 3, w: w, why: "chain" });
      });
      /* 1b) phrase chain: A's whole title (≥ 2 words) opens B's title ("take it" → "take it off") */
      if (xa.toks.length >= 2) tr.forEach(function (xb) {
        if (startsWith(xb.toks, xa.toks)) add(xa.i, xb.i, { type: "chain", word: xa.toks.map(function (w) { return S(xa, w); }).join(" "), str: 3, w: 1, why: "phrase" });
      });
    });
    /* 2) shared rare word (same) */
    Object.keys(ix.byTok).forEach(function (w) {
      var list = ix.byTok[w]; if (list.length < 2 || list.length > 12) return;
      var wt = ix.idf(w) / ix.maxIdf; if (WEAK[w] || wt < 0.42) return;
      for (var p = 0; p < list.length; p++) for (var q = 0; q < list.length; q++) if (p !== q) {
        var xa = tr[list[p]], xb = tr[list[q]];
        var inMain = xa.content.indexOf(w) >= 0 && xb.content.indexOf(w) >= 0;
        var str = inMain ? 2 : 1;
        if (xa.content.length === 1 && xb.content.length === 1 && inMain) str = 3;   /* one-word titles that are the same word: Paradise → Paradise */
        var type = "same";
        if (xa.q && !xb.q) { type = "answer"; str = Math.max(str, xa.qw ? 3 : 2); }
        else if (xa.neg !== xb.neg && inMain) { type = "answer"; }
        add(xa.i, xb.i, { type: type, word: S(xa, w), str: str, w: wt, why: "token" });
      }
    });
    /* 3) shared concept in different words / languages (lang, theme, answer, count) */
    Object.keys(ix.byConcept).forEach(function (c) {
      var list = ix.byConcept[c]; if (list.length < 2 || list.length > 40) return;
      var cw = ix.cidf(c) / ix.maxIdf;
      for (var p = 0; p < list.length; p++) for (var q = 0; q < list.length; q++) if (p !== q) {
        var xa = tr[list[p]], xb = tr[list[q]];
        var wa = xa.concepts[c], wb = xb.concepts[c];
        if (wa === wb && !(xa.q && !xb.q)) continue;                    /* identical word: handled by "same" */
        var shared = Object.keys(xa.concepts).filter(function (k) { return xb.concepts[k]; });
        var la = langOf(String(wa).split(" ")[0]), lb = langOf(String(wb).split(" ")[0]);
        var type, str;
        if (xa.q && !xb.q) { type = "answer"; str = xa.qw ? 3 : 2; }
        else if (la !== lb) { type = "lang"; str = shared.length >= 2 ? 3 : 2; }
        else { type = "theme"; str = shared.length >= 2 ? 2 : 1; }
        if (xa.neg !== xb.neg && type !== "answer") { type = "answer"; str = Math.max(str, 2); }
        if (c === "weekend" || c === "latenight" || c === "call" || c === "emergency") { if (type === "theme") { type = "count"; str = 2; } }
        if (shared.length === 1 && WEAK[wa] && WEAK[wb] && type !== "lang") continue;
        if (GENERIC_C[c] && shared.length === 1 && xa.content.length > 1 && xb.content.length > 1) str = Math.max(1, str - 1);
        add(xa.i, xb.i, { type: type, word: wa === wb ? S(xa, wa) : S(xa, wa) + " → " + S(xb, wb), str: str, w: cw, why: "concept:" + shared.join("+") });
      }
    });
    /* 3b) opposites: "without" → "with you", "truth" → "lie", "far" → "close" … (an answer move) */
    OPP.forEach(function (pr) {
      [[pr[0], pr[1]], [pr[1], pr[0]]].forEach(function (d) {
        (ix.byConcept[d[0]] || []).forEach(function (ai) {
          (ix.byConcept[d[1]] || []).forEach(function (bi) {
            var xa = tr[ai], xb = tr[bi];
            var str = 2;
            add(ai, bi, { type: "answer", word: S(xa, xa.concepts[d[0]]) + " → " + S(xb, xb.concepts[d[1]]), str: str, w: Math.min(ix.cidf(d[0]), ix.cidf(d[1])) / ix.maxIdf, why: "opposite:" + d[0] + "/" + d[1] });
          });
        });
      });
    });
    /* 4) day / time order: Friday → Saturday, small hours → sunrise */
    var dayIdx = function (x) { var s = " " + x.toks.join(" ") + " "; return / friday | viernes /.test(s) ? 5 : / saturday | sabado | שבת /.test(s) ? 6 : / weekend /.test(s) ? 6.5 : null; };
    var timeIdx = function (x) { var s = " " + x.toks.join(" ") + " "; return / (night|nights|tonight|לילה) /.test(s) ? 1 : (x.concepts.latenight ? 2 : / (sunrise|morning|בוקר) /.test(s) ? 3 : null); };
    var days = [], times = [];
    tr.forEach(function (x) { var d = dayIdx(x); if (d != null) days.push([x.i, d]); var t = timeIdx(x); if (t != null) times.push([x.i, t]); });
    days.forEach(function (a) { days.forEach(function (b) { if (b[1] > a[1] && b[1] - a[1] <= 1.5) add(a[0], b[0], { type: "count", word: "יום אחרי יום", str: 2, w: 0.7, why: "day" }); }); });
    times.forEach(function (a) { times.forEach(function (b) { if (b[1] === a[1] + 1) add(a[0], b[0], { type: "count", word: "השעון ממשיך", str: 2, w: 0.6, why: "time" }); }); });
    return out;
  }

  /* ---------------- scoring ---------------- */
  function hypeOf(type, str, A, B, mix) {
    var rec = (A.hot ? 1 : 0) + (B.hot ? 1 : 0);
    var ease = mix.compatible ? 2 : 1;
    var en = mix.dE <= -2 ? -1 : 0;
    var era = (A.y && B.y) ? Math.abs(A.y - B.y) : 0;
    var surprise = (FAMILY[A.g] !== FAMILY[B.g] || era >= 10) ? 1 : 0;
    return Math.max(1, Math.min(9, Math.round(str + rec + ease + en + surprise)));
  }
  function confOf(c, xa, xb) {
    if (c.type === "chain" && c.why === "phrase") return "high";
    if (c.str >= 3 && c.w >= 0.55) return "high";
    if (c.str >= 2 && c.w >= 0.45) return "mid";
    return "low";
  }
  function whyHe(c, A, B) {
    var w = c.word;
    switch (c.type) {
      case "chain": return "השם של A נגמר ב־\"" + w + "\" ושל B מתחיל בזה: המשפט ממשיך מתקליט לתקליט.";
      case "answer": return "A שואל או קורא, ו־B עונה לו על אותה מילה (" + w + ").";
      case "lang": return "אותה מילה בשתי שפות (" + w + "): הקהל שומע תרגום חי בין שני השירים.";
      case "same": return "שני השירים בנויים על אותה מילה (" + w + "), כך שה־hook עובר ישר מאחד לשני.";
      case "count": return "הזמן או הספירה ממשיכים מהשם של A לשם של B (" + w + ").";
      default: return "אותו דימוי בשתי מילים שונות (" + w + "): הסיפור ממשיך.";
    }
  }

  /* autoLinks(DATA, opts) → ranked links
     opts: { limit=150, minScore=0, minConf="mid", types:[…], compatibleOnly=false, genres:[…] (either side), perTrack=3 } */
  function autoLinks(DATA, opts) {
    opts = opts || {};
    var ix = index(DATA), cand = candidates(DATA, ix), list = [];
    var CONF = { low: 0, mid: 1, high: 2 }, minConf = CONF[opts.minConf || "mid"];
    Object.keys(cand).forEach(function (key) {
      var c = cand[key], ab = key.split(">"), ai = +ab[0], bi = +ab[1], A = DATA[ai], B = DATA[bi];
      var xa = ix.tracks[ai], xb = ix.tracks[bi];
      var conf = confOf(c, xa, xb); if (CONF[conf] < minConf) return;
      if (opts.types && opts.types.indexOf(c.type) < 0) return;
      if (opts.genres && opts.genres.length && opts.genres.indexOf(A.g) < 0 && opts.genres.indexOf(B.g) < 0) return;
      var mix = mixCheck(A, B);
      if (opts.compatibleOnly && !mix.compatible) return;
      var hype = hypeOf(c.type, c.str, A, B, mix);
      var score = hype * 10 + Math.round(c.w * 6) + (mix.compatible ? 4 : 0) + (B.hot ? 2 : 0) + (CLUB_G[B.g] && mix.dE >= 0 ? 1 : 0) - (mix.dE <= -2 ? 6 : 0) - (conf === "low" ? 8 : 0);
      score = Math.max(0, Math.min(100, score));
      if (score < (opts.minScore || 0)) return;
      var cues = cuePlan(A, B, mix);
      list.push({ ai: ai, bi: bi, type: c.type, type_he: TYPE_HE[c.type], word: c.word, score: score, hype: hype, conf: conf, mix: mix, cueA: cues.cueA, cueB: cues.cueB, note_he: cues.note_he, why_he: whyHe(c, A, B), src: "auto", basis: c.why });
    });
    /* keep the better direction of each unordered pair */
    var best = {};
    list.forEach(function (l) { var k = Math.min(l.ai, l.bi) + "~" + Math.max(l.ai, l.bi); if (!best[k] || l.score > best[k].score) best[k] = l; });
    list = Object.keys(best).map(function (k) { return best[k]; });
    list.sort(function (x, y) { return y.score - x.score || y.hype - x.hype || (x.ai - y.ai); });
    /* diversity: one track should not own the board */
    var per = opts.perTrack == null ? 2 : opts.perTrack, used = {}, out = [];
    for (var n = 0; n < list.length; n++) {
      var l = list[n]; if ((used[l.ai] || 0) >= per || (used[l.bi] || 0) >= per) continue;
      used[l.ai] = (used[l.ai] || 0) + 1; used[l.bi] = (used[l.bi] || 0) + 1; out.push(l);
      if (out.length >= (opts.limit || 150)) break;
    }
    return out;
  }

  /* ---------------- curated links (links.json) ---------------- */
  function keyOf(t) { return (String(t.t) + " | " + String(t.a)).toLowerCase().replace(/\s+/g, " ").trim(); }
  function findTrack(DATA, s, memo) {
    var k = String(s).toLowerCase().replace(/\s+/g, " ").trim();
    if (memo[k] != null) return memo[k];
    var hit = -1, parts = k.split(" | "), title = parts[0], artist = (parts[1] || "").split(",")[0].trim();
    for (var i = 0; i < DATA.length && hit < 0; i++) if (keyOf(DATA[i]) === k) hit = i;
    for (var j = 0; j < DATA.length && hit < 0; j++) {
      var t = DATA[j];
      if (String(t.t).toLowerCase() === title && String(t.a).toLowerCase().indexOf(artist) >= 0) hit = j;
    }
    memo[k] = hit; return hit;
  }
  function resolve(DATA, LINKS) {
    var memo = {}, out = [];
    (LINKS || []).forEach(function (L) {
      var ai = findTrack(DATA, L.a, memo), bi = findTrack(DATA, L.b, memo);
      if (ai < 0 || bi < 0) return;
      var A = DATA[ai], B = DATA[bi], mix = mixCheck(A, B);
      var tech = L.technique || mix.technique;
      /* a long overlap (blend / double drop / call-and-response / acapella) needs keys that really fit: when they
         don't (by ear, or by the corrected keys), never overlap: cut or echo on the word, with a fresh cue plan */
      var overlap = { blend: 1, double: 1, callresp: 1, acapella: 1 }, forced = false;
      if (overlap[tech] && !mix.compatible) { tech = mix.technique; if (overlap[tech]) tech = "echo"; forced = true; }
      var cues = cuePlan(A, B, mix, { secA: L.secA, secB: L.secB, technique: tech });
      if (L.cueA) cues.cueA.he = L.cueA;
      if (L.cueB && !forced) cues.cueB.he = L.cueB;
      out.push({
        ai: ai, bi: bi, type: L.type, type_he: TYPE_HE[L.type] || L.type, word: L.word, conf: L.conf || "high",
        hype: L.hype || hypeOf(L.type, L.conf === "mid" ? 2 : L.conf === "low" ? 1 : 3, A, B, mix),
        score: Math.min(100, (L.hype || 7) * 10 + 8 + (mix.compatible ? 2 : 0)),
        mix: Object.assign({}, mix, { technique: tech, technique_he: TECH_HE[tech] || tech }),
        cueA: cues.cueA, cueB: cues.cueB, note_he: cues.note_he, why_he: L.why_he || "", src: "curated"
      });
    });
    out.sort(function (x, y) { return y.hype - x.hype || y.score - x.score; });
    return out;
  }
  function merge(curated, auto, opts) {
    opts = opts || {};
    var seen = {}, out = [];
    (curated || []).concat(auto || []).forEach(function (l) {
      var k = Math.min(l.ai, l.bi) + "~" + Math.max(l.ai, l.bi);
      if (seen[k]) return; seen[k] = 1; out.push(l);
    });
    return opts.limit ? out.slice(0, opts.limit) : out;
  }

  /* ---------------- demo on 30 s previews ---------------- */
  /* previewPlan(link, DATA): play A alone for T seconds (a whole number of bars at A's playing tempo,
     8 bars when that fits in ~16 s, else 4), then bring B in with the technique's move. */
  function previewPlan(link, DATA) {
    var A = DATA[link.ai], B = DATA[link.bi], mix = link.mix || mixCheck(A, B);
    var rateA = mix.compatible ? mix.rates.A : 1;
    var bar = 240 / (effBpm(A) * rateA);
    var bars = bar * 8 <= 16.5 ? 8 : 4, T = Math.round(bar * bars * 100) / 100;
    var tech = mix.technique, style = (tech === "double" || tech === "blend" || tech === "callresp") ? "blend" : (tech === "echo" || tech === "acapella" || tech === "filter") ? "echo" : tech === "spinback" ? "spinback" : "cut";
    var beat = bar / 4;
    return {
      T: T, bars: bars, bar: Math.round(bar * 1000) / 1000, beat: Math.round(beat * 1000) / 1000, style: style,
      xfMs: style === "blend" ? Math.round(bar * 2 * 1000) : style === "echo" ? Math.round(beat * 1000) : 90,
      rates: mix.compatible ? mix.rates : { A: 1, B: 1 }, sync: !!mix.compatible
    };
  }

  var api = {
    index: index, autoLinks: autoLinks, mixCheck: mixCheck, resolve: resolve, merge: merge, cuePlan: cuePlan, previewPlan: previewPlan,
    energyOf: energyOf, formOf: formOf, camRel: camRel, tempo: tempo, earKey: earKey,
    TYPE_HE: TYPE_HE, TECH_HE: TECH_HE, SEC_HE: SEC_HE,
    _norm: { normText: normText, splitTitle: splitTitle }
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.Wordplay = api;
})(typeof window !== "undefined" ? window : (typeof globalThis !== "undefined" ? globalThis : this));
