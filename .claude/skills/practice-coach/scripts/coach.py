#!/usr/bin/env python3
"""DJ Lab practice coach: today's drill, practice log and progress stats (Hebrew output).

  python .claude/skills/practice-coach/scripts/coach.py init [--level beginner] [--minutes 20]
  python .claude/skills/practice-coach/scripts/coach.py today [--minutes 20] [--skill bass_swap]
  python .claude/skills/practice-coach/scripts/coach.py log --drill practice-08 --minutes 20 --score 3 --note "..."
  python .claude/skills/practice-coach/scripts/coach.py stats
  python .claude/skills/practice-coach/scripts/coach.py ladder

State lives in progress/: profile.json, log.csv (date,drill_id,skill,minutes,score,notes_he), weekly/.
Score = self-rating 1-5 (1 = lost it, 3 = OK with mistakes, 5 = clean every time).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PROG = ROOT / "progress"
LOG = PROG / "log.csv"
PROFILE = PROG / "profile.json"
LOG_FIELDS = ["date", "drill_id", "skill", "minutes", "score", "notes_he"]

# The progression ladder (order matters). Each skill: Hebrew name, guide keywords, drills.
# Drill = (drill_id, files, steps_he, success_he)
LADDER = [
    ("counting", "ספירת ביטים, תיבות ופרייזים", ["phras", "count", "פרייז"], [
        ("practice-01", ["practice-01"], "נגנו את הקובץ וספרו בקול 1-2-3-4. הקישו על השולחן בכל '1' של תיבה, "
         "ותגידו 'פרייז!' כשמגיע הקראש (כל 8 תיבות) והפעמון (כל 32).", "3 פרייזים של 32 תיבות ברצף בלי לאבד את הספירה"),
    ]),
    ("cueing", "Cue ו-Hot Cues על ה-1", ["cue", "hot"], [
        ("practice-13", ["practice-13"], "Quantize ON: שימו Hot Cues A–E על התיבות 1/17/33/49/65 (יש שם צליל ברור). "
         "אחר כך Quantize OFF ונסו שוב ידנית.", "5 מתוך 5 קיוז במקום, גם בלי Quantize"),
    ]),
    ("beatmatch_sync", "ביטמאצ'ינג עם Sync + יישור פרייזים", ["sync", "beatmatch"], [
        ("practice-02", ["practice-02", "practice-03"], "Deck 1: practice-02 (120), Deck 2: practice-03 (124). "
         "Sync ON. התחילו את Deck 2 בדיוק על ה-1 של פרייז ב-Deck 1, והקשיבו שהקראשים נופלים יחד.",
         "10 כניסות ברצף שבהן הקראשים של שני הדקים נוחתים יחד"),
    ]),
    ("beatmatch_ear", "ביטמאצ'ינג באוזן", ["beatmatch", "ear", "אוזן"], [
        ("practice-03", ["practice-03", "practice-04"], "Sync OFF. Deck 1: practice-03 (124), Deck 2: practice-04 (128). "
         "כסו את המספרים במסך! כוונו את ה-Tempo fader של Deck 2 עד שהקיקים לא 'דוהרים', ותקנו עם ה-Jog.",
         "32 תיבות בלי סטייה של יותר מחצי ביט, בלי להסתכל על ה-BPM"),
        ("practice-06", ["practice-06", "practice-07"], "Sync OFF עם טמפו 'עקום': practice-06 (125.5) מול practice-07 (122.7). "
         "אותו תרגיל — אבל הפעם אין מספר עגול לנחש.", "32 תיבות יציבות פעמיים ברצף"),
    ]),
    ("eq_ear", "אוזן ל-EQ (Low/Mid/High)", ["eq"], [
        ("practice-14", ["practice-14"], "כל 8 תיבות מודגש תחום אחר. כתבו על דף Low/Mid/High לפני שהקראש מגיע.",
         "8 מתוך 10 ניחושים נכונים"),
    ]),
    ("eq_blend", "בלנד ארוך עם EQ", ["blend", "eq", "בלנד"], [
        ("transition-01", ["transition-01", "house-01", "house-02"], "האזינו לדמו transition-01, ואז בצעו אותו בעצמכם "
         "עם house-01 → house-02: כניסה על Hot Cue A, 32 תיבות חפיפה, Low של הנכנס סגור עד תיבה 17.",
         "בלנד של 32 תיבות בלי 'בוץ' בבאס ובלי קפיצת ווליום"),
    ]),
    ("bass_swap", "החלפת באס (Bass Swap)", ["bass", "באס"], [
        ("practice-08", ["practice-08", "practice-09", "transition-02"], "practice-08 (8A) מול practice-09 (9A), שניהם 124. "
         "16 תיבות חפיפה עם Low סגור בנכנס, ואז על ה-1 של פרייז: Low פתוח בנכנס וסגור ביוצא — באותו רגע.",
         "5 החלפות נקיות ברצף, בדיוק על ה-1"),
    ]),
    ("filter_echo", "מעברי Filter ו-Echo Out", ["filter", "echo", "פילטר"], [
        ("transition-03", ["transition-03", "transition-04"], "האזינו ל-transition-03 (Filter) ול-transition-04 (Echo Out). "
         "שחזרו כל אחד 3 פעמים: Filter HPF ב-8 תיבות; Echo 1/2 Beat בסוף פרייז והנכנס על ה-1.",
         "3 מעברים מכל סוג בלי 'חור' בקצב"),
    ]),
    ("harmonic", "מיקס הרמוני (Camelot)", ["harmonic", "camelot", "key", "הרמוני"], [
        ("practice-10", ["practice-10", "practice-11", "practice-12"], "practice-10 (8A) מול practice-12 (9A) — נשמע טוב. "
         "עכשיו practice-10 מול practice-11 (3A) — שומעים את הזיוף? מצאו בספרייה 3 זוגות 8A↔9A / 8A↔8B.",
         "לזהות באוזן 'תואם/מתנגש' ב-5 מתוך 5 זוגות"),
    ]),
    ("phrase_transitions", "מעברים מבוססי פרייז ו-Hot Cues", ["phrase", "drop", "breakdown", "דרופ"], [
        ("transition-10", ["transition-10", "transition-09"], "דמו transition-10 (כניסה בברייקדאון) ו-transition-09 "
         "(החלפת דרופים). שימו Hot Cues C/D ובצעו: הדרופ של הנכנס נוחת בדיוק בסוף הברייקדאון של היוצא.",
         "3 החלפות דרופ מדויקות ברצף"),
    ]),
    ("tempo_change", "מעברי טמפו (100 → 124)", ["tempo", "טמפו"], [
        ("practice-15", ["practice-15", "transition-08"], "practice-15 (100) עם אאוטרו תופים. Echo Out בסוף הפרייז והכנסה של "
         "טראק 124 על ה-1 (ראו transition-08). נסו גם 'גשר' דרך טראק 110.", "2 מעברי טמפו בלי שהרחבה 'נתקעת'"),
    ]),
    ("mini_set", "מיני-סט מוקלט (15–30 דק')", ["set", "סט"], [
        ("mini-set", ["sets/"], "בחרו סט מ-sets/ (או צרו: python tools/set_planner.py --minutes 20 --out sets/practice.md). "
         "הקליטו ב-Rekordbox (REC), ואז האזינו ורשמו 3 דברים לשיפור.", "סט רציף מוקלט בלי עצירות; 3 הערות לשיפור"),
    ]),
]
SKILLS = {s[0]: s for s in LADDER}
DRILL_SKILL = {d[0]: s[0] for s in LADDER for d in s[3]}


def read_log() -> list[dict]:
    if not LOG.exists():
        return []
    with LOG.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def ensure_state(level: str = "beginner", minutes: int = 20) -> None:
    PROG.mkdir(exist_ok=True)
    (PROG / "weekly").mkdir(exist_ok=True)
    if not PROFILE.exists():
        PROFILE.write_text(json.dumps({
            "level": level, "minutes_per_day": minutes, "equipment": "Rekordbox + controller (update me)",
            "goals_he": ["לשלוט בביטמאצ'ינג באוזן", "לבנות סט של שעה"], "lesson_day": "",
            "created": dt.date.today().isoformat(),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not LOG.exists():
        with LOG.open("w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerow(LOG_FIELDS)


def skill_state(log: list[dict]) -> dict:
    st = {k: {"scores": [], "last": None, "minutes": 0} for k in SKILLS}
    for r in log:
        k = r.get("skill") or DRILL_SKILL.get(r.get("drill_id", ""), "")
        if k not in st:
            continue
        try:
            st[k]["scores"].append(int(r["score"]))
        except (ValueError, KeyError):
            pass
        st[k]["minutes"] += int(float(r.get("minutes") or 0))
        st[k]["last"] = max(filter(None, [st[k]["last"], r.get("date")]))
    for k, v in st.items():
        last3 = v["scores"][-3:]
        v["mastered"] = len(last3) == 3 and min(last3) >= 4
        v["struggling"] = len(v["scores"]) >= 2 and max(v["scores"][-2:]) <= 2
    return st


def find_files(ids: list[str]) -> list[str]:
    out = []
    extras = {}
    ep = ROOT / "music" / "extras.plan.json"
    if ep.exists():
        data = json.loads(ep.read_text(encoding="utf-8"))
        extras = {x["id"]: x for x in data.get("practice", []) + data.get("transitions", [])}
    for i in ids:
        hits = sorted(ROOT.glob(f"music/*/{i}*.mp3")) + sorted(ROOT.glob(f"music/tracks/*/{i}-*.mp3"))
        title = extras.get(i, {}).get("title_he", "")
        if hits:
            out.append(f"`{hits[0].relative_to(ROOT)}`" + (f" — {title}" if title else ""))
        else:
            out.append(f"`{i}`" + (f" — {title}" if title else "") + (" (עוד לא רונדר)" if i.startswith(("practice", "transition")) else ""))
    return out


def guide_chapter(keywords: list[str]) -> str:
    for md in sorted((ROOT / "guide").glob("*.md")):
        head = md.read_text(encoding="utf-8")[:600].lower()
        if any(k.lower() in md.name.lower() or k.lower() in head for k in keywords):
            return str(md.relative_to(ROOT))
    return ""


def cmd_today(args) -> int:
    ensure_state()
    log = read_log()
    st = skill_state(log)
    today = dt.date.today()
    if args.skill:
        focus = args.skill
    else:
        focus = next((k for k in SKILLS if not st[k]["mastered"]), LADDER[-1][0])
        if st[focus]["struggling"]:
            idx = list(SKILLS).index(focus)
            focus = list(SKILLS)[max(0, idx - 1)]
    review = None
    for k in SKILLS:  # spaced review of a mastered skill not touched for 7+ days
        last = st[k]["last"]
        if st[k]["mastered"] and k != focus and (not last or (today - dt.date.fromisoformat(last)).days >= 7):
            review = k
            break
    skill = SKILLS[focus]
    n_done = len(st[focus]["scores"])
    drill = skill[3][min(len(skill[3]) - 1, n_done // 3)]
    m = args.minutes
    warm, main, cool = max(2, round(m * 0.15)), max(5, round(m * 0.65)), max(2, m - max(2, round(m * 0.15)) - max(5, round(m * 0.65)))
    print(f"🎯 התרגיל של היום ({today.isoformat()}) — {m} דקות")
    print(f"מיומנות: {skill[1]}  (`{focus}`, שלב {list(SKILLS).index(focus) + 1}/{len(LADDER)} בסולם)")
    ch = guide_chapter(skill[2])
    if ch:
        print(f"רקע במדריך: `{ch}`")
    print()
    if review:
        rv = SKILLS[review]
        print(f"1. חימום ({warm} דק') — חזרה על {rv[1]}: {rv[3][0][2][:120]}…")
    else:
        print(f"1. חימום ({warm} דק') — נגנו practice-01 וספרו פרייזים בקול; אוזניות בווליום נמוך-בינוני.")
    print(f"2. תרגיל מרכזי ({main} דק') — `{drill[0]}`")
    for f in find_files(drill[1]):
        print(f"   · קובץ: {f}")
    print(f"   איך: {drill[2]}")
    print(f"   ✅ הצלחה = {drill[3]}")
    print(f"3. סיום ({cool} דק') — מיקס חופשי עם 2 טראקים שאתם אוהבים, בלי לחץ.")
    print()
    print(f"אחרי האימון: coach.py log --drill {drill[0]} --minutes {m} --score <1-5> --note \"מה היה קשה?\"")
    return 0


def cmd_log(args) -> int:
    ensure_state()
    if not 1 <= args.score <= 5:
        print("score must be 1-5", file=sys.stderr)
        return 2
    skill = args.skill or DRILL_SKILL.get(args.drill, "free")
    with LOG.open("a", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerow([args.date or dt.date.today().isoformat(), args.drill, skill, args.minutes, args.score, args.note or ""])
    st = skill_state(read_log())
    s = st.get(skill)
    msg = "נרשם! 💪"
    if s and s["mastered"]:
        msg += f" שלוש פעמים ברצף 4+ — `{skill}` בשליטה. בפעם הבאה עולים שלב."
    elif s and s["struggling"]:
        msg += " נראה שזה עדיין קשה — בפעם הבאה נחזור צעד אחד אחורה ונבנה ביטחון."
    print(msg)
    return 0


def streak(dates: set[str]) -> int:
    d, n = dt.date.today(), 0
    if d.isoformat() not in dates:
        d -= dt.timedelta(days=1)
    while d.isoformat() in dates:
        n += 1
        d -= dt.timedelta(days=1)
    return n


def cmd_stats(args) -> int:
    ensure_state()
    log = read_log()
    st = skill_state(log)
    today = dt.date.today()
    week = [r for r in log if r.get("date") and (today - dt.date.fromisoformat(r["date"])).days < 7]
    total = sum(int(float(r.get("minutes") or 0)) for r in log)
    print(f"📈 התקדמות — {len(log)} אימונים, {total} דקות בסך הכל, {sum(int(float(r.get('minutes') or 0)) for r in week)} דקות ב-7 הימים האחרונים")
    print(f"🔥 רצף ימים: {streak({r['date'] for r in log if r.get('date')})}")
    print()
    for k, name, *_ in LADDER:
        v = st[k]
        sc = v["scores"][-3:]
        bar = "★" * round(sum(sc) / len(sc)) if sc else ""
        state = "✅ בשליטה" if v["mastered"] else ("⚠️ קשה" if v["struggling"] else ("…בתהליך" if sc else "—"))
        print(f"  {name:<34} {bar:<5} {state:<10} {v['minutes']:>4} דק'" + (f"  (אחרון: {v['last']})" if v["last"] else ""))
    return 0


def cmd_ladder(args) -> int:
    for i, (k, name, _, drills) in enumerate(LADDER, 1):
        print(f"{i:>2}. {name}  (`{k}`) — " + ", ".join(d[0] for d in drills))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--level", default="beginner")
    p.add_argument("--minutes", type=int, default=20)
    p = sub.add_parser("today")
    p.add_argument("--minutes", type=int, default=20)
    p.add_argument("--skill", choices=list(SKILLS))
    p = sub.add_parser("log")
    p.add_argument("--drill", required=True)
    p.add_argument("--minutes", type=int, required=True)
    p.add_argument("--score", type=int, required=True)
    p.add_argument("--note", default="")
    p.add_argument("--skill", choices=list(SKILLS) + ["free"])
    p.add_argument("--date", help="YYYY-MM-DD (default today)")
    sub.add_parser("stats")
    sub.add_parser("ladder")
    args = ap.parse_args(argv)
    if args.cmd == "init":
        ensure_state(args.level, args.minutes)
        print(f"✓ נוצרו {PROFILE.relative_to(ROOT)} ו-{LOG.relative_to(ROOT)}")
        return 0
    return {"today": cmd_today, "log": cmd_log, "stats": cmd_stats, "ladder": cmd_ladder}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
