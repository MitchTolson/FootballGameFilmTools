"""Build a self-contained HTML scouting report from the normalized play table."""
from __future__ import annotations

import html
import os
import re
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from .loader import GameInfo

DD_ORDER = ["1st & 10+", "1st & <10",
            "2nd & long (7+)", "2nd & medium (3-6)", "2nd & short (1-2)",
            "3rd & long (7+)", "3rd & medium (3-6)", "3rd & short (1-2)",
            "4th & long (7+)", "4th & medium (3-6)", "4th & short (1-2)"]
ZONE_ORDER = ["Backed up (inside own 20)", "Own territory (own 20-49)", "Opp territory (21-50)",
              "Red zone (6-20)", "Goal line (5-)"]


# ---------------------------------------------------------------- helpers
def esc(x) -> str:
    return html.escape("" if x is None or (pd.api.types.is_scalar(x) and pd.isna(x)) else str(x))


def pct(n, d) -> str:
    return "–" if not d else f"{100 * n / d:.0f}%"


def num(x, digits=1) -> str:
    return "–" if x is None or pd.isna(x) else f"{x:.{digits}f}"


class Ctx:
    """Things every section needs: output dir (for relative clip links) and game labels."""

    def __init__(self, out_dir: Path, games: list[GameInfo]):
        self.out_dir = out_dir
        self.labels = {i: g.opponent[:3].upper() for i, g in enumerate(games, 1)}

    def clip(self, row) -> str:
        label = f"{self.labels.get(row['GAME_NUM'], '?')}-{int(row['PLAY #'])}"
        path = row.get("CLIP")
        if path is None or pd.isna(path):
            return esc(label)
        rel = os.path.relpath(path, self.out_dir).replace(os.sep, "/")
        return f'<a class="clip" href="{quote(rel)}" title="Open clip">{esc(label)}</a>'

    def index(self, plays: pd.DataFrame) -> None:
        """Map 'FOS-12' style labels to rows so text can link clips."""
        self.by_label = {f"{self.labels.get(r['GAME_NUM'], '?')}-{int(r['PLAY #'])}": r for _, r in plays.iterrows()}

    def link_labels(self, text: str) -> str:
        """Turn clip labels in already-escaped text into links."""
        def sub_(m):
            r = getattr(self, "by_label", {}).get(m.group(0))
            return self.clip(r) if r is not None else m.group(0)
        return re.sub(r"\b[A-Z]{3}-\d+\b", sub_, text)

    def clips(self, df: pd.DataFrame, limit=12) -> str:
        links = [self.clip(r) for _, r in df.head(limit).iterrows()]
        more = len(df) - limit
        return " ".join(links) + (f' <span class="muted">+{more}</span>' if more > 0 else "")


def bar(value: float, max_value: float, text: str) -> str:
    w = 0 if not max_value else max(2, 100 * value / max_value)
    return (f'<div class="barcell" title="{esc(text)}"><div class="track"><div class="bar" style="width:{w:.1f}%">'
            f'</div></div><span>{esc(text)}</span></div>')


def table(headers: list[str], rows: list[list[str]], numeric_cols=()) -> str:
    th = "".join(f'<th class="{"num" if i in numeric_cols else ""}">{esc(h)}</th>' for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(f'<td class="{"num" if i in numeric_cols else ""}">{c}</td>' for i, c in enumerate(r)) + "</tr>"
        for r in rows)
    return f'<div class="tablewrap"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def tiles(items: list[tuple[str, str, str]]) -> str:
    return '<div class="tiles">' + "".join(
        f'<div class="tile"><div class="tlabel">{esc(l)}</div><div class="tvalue">{esc(v)}</div>'
        f'<div class="tsub">{esc(s)}</div></div>' for l, v, s in items) + "</div>"


def section(title: str, audience: str, body: str, sid: str) -> str:
    aud = f'<span class="aud">For: {esc(audience)}</span>' if audience else ""
    return f'<section id="{sid}"><h2>{esc(title)}{aud}</h2>{body}</section>'


def sub(title: str, body: str, note: str = "") -> str:
    n = f'<p class="note">{esc(note)}</p>' if note else ""
    return f'<div class="sub"><h3>{esc(title)}</h3>{n}{body}</div>'


def group_stats(df: pd.DataFrame, by: str, order=None, min_n=1) -> list[dict]:
    out = []
    for key, g in df.groupby(by, dropna=True):
        if len(g) < min_n:
            continue
        s = g[g["SCRIMMAGE"]]
        runs = g[g["KIND"] == "Run"]
        succ = s["SUCCESS"].dropna()
        out.append(dict(
            key=key, n=len(g), g=g,
            run_pct=len(runs) / max(1, g["KIND"].notna().sum()),
            avg=s["GAIN"].mean() if len(s) else None,
            run_avg=s[s["KIND"] == "Run"]["GAIN"].mean(),
            pass_avg=s[s["KIND"] == "Pass"]["GAIN"].mean(),
            succ=succ.mean() if len(succ) else None,
            expl=int(s["EXPLOSIVE"].sum()),
            td=int(g["IS_TD"].sum()),
        ))
    if order:
        rank = {k: i for i, k in enumerate(order)}
        out.sort(key=lambda r: rank.get(r["key"], 999))
    else:
        out.sort(key=lambda r: -r["n"])
    return out


def top_calls(g: pd.DataFrame, col="PLAY_FAMILY", k=3) -> str:
    vc = g[col].dropna().value_counts()
    if vc.empty:
        return '<span class="muted">not tagged</span>'
    tot = vc.sum()
    return ", ".join(f"{esc(name)} {100 * c / tot:.0f}%" for name, c in vc.head(k).items())


def share(series: pd.Series, value) -> tuple[int, int]:
    s = series.dropna()
    return int((s == value).sum()), len(s)


# ---------------------------------------------------------------- offense
def offense_section(o: pd.DataFrame, ctx: Ctx, team: str) -> str:
    s = o[o["SCRIMMAGE"]]
    runs, passes = s[s["KIND"] == "Run"], s[s["KIND"] == "Pass"]
    called = o[o["KIND"].notna()]
    run_n = int((called["KIND"] == "Run").sum())
    succ = s["SUCCESS"].dropna()
    parts = [tiles([
        ("Offensive snaps", str(len(called)), f"{o['GAME_NUM'].nunique()} games"),
        ("Run rate", pct(run_n, len(called)), f"{run_n} run / {len(called) - run_n} pass"),
        ("Yards per run", num(runs["GAIN"].mean()), f"{len(runs)} measured runs"),
        ("Yards per pass play", num(passes["GAIN"].mean()), "incl. scrambles/sacks"),
        ("Success rate", pct(succ.sum(), len(succ)), "40% / 60% / 100% of distance"),
        ("Explosive plays", str(int(s["EXPLOSIVE"].sum())), "run 10+ / pass 15+"),
    ])]

    # Play families
    fam = group_stats(o, "PLAY_FAMILY")
    mx = max((r["n"] for r in fam), default=1)
    rows = []
    for r in fam:
        g = r["g"]
        ts, tn = share(g["DIR_VS_STRENGTH"], "To strength")
        fs, fn = share(g["DIR_VS_FIELD"], "To field")
        rows.append([esc(r["key"]), bar(r["n"], mx, f"{r['n']} ({pct(r['n'], len(called))})"),
                     num(r["avg"]), pct(r["succ"] * 100 if r["succ"] is not None else 0, 100) if r["succ"] is not None else "–",
                     str(r["expl"]), str(r["td"]), f"{pct(ts, tn)} <span class='muted'>({tn})</span>",
                     f"{pct(fs, fn)} <span class='muted'>({fn})</span>", ctx.clips(g, 8)])
    parts.append(sub("Play calls", table(
        ["Play family", "Calls", "Avg gain", "Success", "Expl.", "TD", "To strength", "To field", "Clips"],
        rows, numeric_cols=(2, 3, 4, 5, 6, 7)),
        "Play names are Hudl's tags grouped into families. 'To strength' = run/throw toward the formation's strength; "
        "'To field' = toward the wide side of the field (hash plays only). (n) = plays with that info tagged."))

    # Raw play names (detail)
    raw = group_stats(o, "PLAY", min_n=2)
    parts.append(sub("Play calls - as tagged (2+ calls)", table(
        ["Play (Hudl tag)", "Calls", "Avg gain", "Success", "Clips"],
        [[esc(r["key"]), str(r["n"]), num(r["avg"]),
          pct(r["succ"] * 100, 100) if r["succ"] is not None else "–", ctx.clips(r["g"], 8)] for r in raw],
        numeric_cols=(1, 2, 3))))

    # Down & distance
    dd = group_stats(o, "DD", order=DD_ORDER)
    parts.append(sub("Down & distance", table(
        ["Situation", "Snaps", "Run %", "Top calls", "Avg gain", "Success"],
        [[esc(r["key"]), str(r["n"]), bar(r["run_pct"], 1, f"{r['run_pct'] * 100:.0f}% run"), top_calls(r["g"]),
          num(r["avg"]), pct(r["succ"] * 100, 100) if r["succ"] is not None else "–"] for r in dd],
        numeric_cols=(1, 4, 5))))

    # Formations
    fm = group_stats(o, "FORM_FAMILY")
    mx = max((r["n"] for r in fm), default=1)
    parts.append(sub("Formations", table(
        ["Formation", "Snaps", "Run %", "Top calls", "Avg gain", "Success"],
        [[esc(r["key"]), bar(r["n"], mx, str(r["n"])), f"{r['run_pct'] * 100:.0f}%", top_calls(r["g"]),
          num(r["avg"]), pct(r["succ"] * 100, 100) if r["succ"] is not None else "–"] for r in fm],
        numeric_cols=(2, 4, 5)),
        "Left/Right/Open dropped so mirrored sets group together. Pistol is kept separate from the gun sets."))

    # Formation x play family
    ct = pd.crosstab(o["FORM_FAMILY"], o["PLAY_FAMILY"])
    if not ct.empty:
        ct = ct.loc[ct.sum(axis=1).sort_values(ascending=False).index, ct.sum().sort_values(ascending=False).index]
        mxv = ct.values.max()
        rows = []
        for form, r in ct.iterrows():
            cells = []
            for v in r.values:
                a = 0 if not v else 0.12 + 0.75 * v / mxv
                cells.append(f'<span class="heat" style="--a:{a:.2f}">{v if v else ""}</span>')
            rows.append([esc(form)] + cells)
        parts.append(sub("Formation → play call", table(["Formation"] + [esc(c) for c in ct.columns], rows,
                                                         numeric_cols=tuple(range(1, len(ct.columns) + 1))),
                         "Count of each call from each formation. Darker = more often."))

    # Motion
    m = o[o["KIND"].notna()]
    mot = m[m["HAS_MOTION"]]
    rows = []
    for r in group_stats(mot, "PLAY_FAMILY"):
        w, n = share(r["g"]["DIR_VS_MOTION"], "With motion")
        rows.append([esc(r["key"]), str(r["n"]), f"{pct(w, n)} <span class='muted'>({n})</span>", num(r["avg"]),
                     ctx.clips(r["g"], 8)])
    w_all, n_all = share(mot["DIR_VS_MOTION"], "With motion")
    parts.append(sub("Motion", tiles([
        ("Snaps with motion", pct(len(mot), len(m)), f"{len(mot)} of {len(m)}"),
        ("Play goes with the motion", pct(w_all, n_all), f"{n_all} motion snaps with a direction"),
    ]) + table(["Play family (motion snaps)", "Snaps", "Goes with motion", "Avg gain", "Clips"], rows,
               numeric_cols=(1, 2, 3))))

    # Field zone
    fz = group_stats(o, "FIELD_ZONE", order=ZONE_ORDER)
    parts.append(sub("Field position", table(
        ["Field zone", "Snaps", "Run %", "Top calls", "Avg gain", "TD"],
        [[esc(r["key"]), str(r["n"]), f"{r['run_pct'] * 100:.0f}%", top_calls(r["g"]), num(r["avg"]), str(r["td"])]
         for r in fz], numeric_cols=(1, 2, 4, 5))))

    # By game
    parts.append(sub("By game", by_game(o, ctx)))

    # Big plays and turnovers
    big = o[o["EXPLOSIVE"] | o["IS_TURNOVER"]].sort_values(["GAME_NUM", "PLAY #"])
    parts.append(sub("Explosive plays & turnovers", play_list(big, ctx)))
    return section(f"{team} offense", "Defense - DL, LB, DB", "".join(parts), "offense")


def by_game(df: pd.DataFrame, ctx: Ctx) -> str:
    rows = []
    for gnum, g in df.groupby("GAME_NUM"):
        s = g[g["SCRIMMAGE"]]
        called = g[g["KIND"].notna()]
        rows.append([esc(g["GAME"].iloc[0]), esc(g["GAME_DATE"].iloc[0].strftime("%b %d") if pd.notna(g["GAME_DATE"].iloc[0]) else ""),
                     str(len(called)), pct((called["KIND"] == "Run").sum(), len(called)),
                     num(s[s["KIND"] == "Run"]["GAIN"].mean()), num(s[s["KIND"] == "Pass"]["GAIN"].mean()),
                     str(int(s["EXPLOSIVE"].sum())), top_calls(g)])
    return table(["Game", "Date", "Snaps", "Run %", "Yds/run", "Yds/pass", "Expl.", "Top calls"], rows,
                 numeric_cols=(2, 3, 4, 5, 6))


def play_list(df: pd.DataFrame, ctx: Ctx) -> str:
    if df.empty:
        return '<p class="muted">None.</p>'
    rows = []
    for _, r in df.iterrows():
        dd = f"{int(r['DN'])} & {int(r['DIST'])}" if pd.notna(r["DN"]) and pd.notna(r["DIST"]) else ""
        yl = r["YARD LN"]
        spot = "" if pd.isna(yl) else (f"own {int(-yl)}" if yl < 0 else f"opp {int(yl)}")
        rows.append([ctx.clip(r), f"Q{int(r['QTR'])}" if pd.notna(r["QTR"]) else "", esc(dd), esc(spot),
                     esc(r["FORMATION"]), esc(r["PLAY"]), esc(r["PLAY DIR"]), esc(r["RESULT"]),
                     num(r["GAIN"], 0)])
    headers = ["Clip", "Qtr", "D&D", "Spot", "Formation", "Play", "Dir", "Result", "Gain"]
    keep = [i for i in range(len(headers)) if any(r[i] for r in rows)]   # drop never-tagged columns
    return table([headers[i] for i in keep], [[r[i] for i in keep] for r in rows],
                 numeric_cols=tuple(n for n, i in enumerate(keep) if headers[i] == "Gain"))


# ---------------------------------------------------------------- defense
def defense_section(d: pd.DataFrame, ctx: Ctx, team: str) -> str:
    s = d[d["SCRIMMAGE"]]
    runs, passes = s[s["KIND"] == "Run"], s[s["KIND"] == "Pass"]
    succ = s["SUCCESS"].dropna()
    sacks = int(d["RESULT"].str.contains("Sack").sum())
    takeaways = int(d["IS_TURNOVER"].sum())
    parts = ['<p class="callout">The Hudl breakdowns tag the <b>opponent\'s offense</b> on these snaps; '
             f'{esc(team)}\'s fronts, blitzes and coverages are not tagged. The tables show what offenses ran '
             f'against {esc(team)} and what worked. Use the clip links to see the defensive looks.</p>',
             tiles([
                 ("Snaps defended", str(int(d["KIND"].notna().sum())), f"{d['GAME_NUM'].nunique()} games"),
                 ("Yards per run allowed", num(runs["GAIN"].mean()), f"{len(runs)} runs"),
                 ("Yards per pass allowed", num(passes["GAIN"].mean()), f"{len(passes)} pass plays"),
                 ("Offense success rate", pct(succ.sum(), len(succ)), "lower is better for them"),
                 ("Explosives allowed", str(int(s["EXPLOSIVE"].sum())), "run 10+ / pass 15+"),
                 ("Sacks / INT + fumbles", f"{sacks} / {takeaways}", "fumbles may not all be recovered"),
             ])]

    fm = group_stats(d, "FORM_FAMILY")
    mx = max((r["n"] for r in fm), default=1)
    parts.append(sub("Against opponent formations", table(
        ["Opponent formation", "Snaps", "Run %", "Yds/run", "Yds/pass", "Success", "Expl.", "Clips"],
        [[esc(r["key"]), bar(r["n"], mx, str(r["n"])), f"{r['run_pct'] * 100:.0f}%", num(r["run_avg"]),
          num(r["pass_avg"]), pct(r["succ"] * 100, 100) if r["succ"] is not None else "–", str(r["expl"]),
          ctx.clips(r["g"], 8)] for r in fm],
        numeric_cols=(2, 3, 4, 5, 6)),
        "Formation names are Hudl's tags for the opponent's offense (e.g. Kings/Queens = that tagger's labels)."))

    rows = []
    for kind in ("Run", "Pass"):
        k = s[s["KIND"] == kind]
        for lab, col, val in (("To strength", "DIR_VS_STRENGTH", "To strength"),
                              ("Away from strength", "DIR_VS_STRENGTH", "Away from strength"),
                              ("To field", "DIR_VS_FIELD", "To field"),
                              ("To boundary", "DIR_VS_FIELD", "To boundary")):
            g = k[k[col] == val]
            sc = g["SUCCESS"].dropna()
            rows.append([esc(kind), esc(lab), str(len(g)), num(g["GAIN"].mean()), pct(sc.sum(), len(sc)),
                         str(int(g["EXPLOSIVE"].sum()))])
    parts.append(sub("Where offenses attacked", table(
        ["Type", "Direction", "Plays", "Avg gain", "Success", "Expl."], rows, numeric_cols=(2, 3, 4, 5))))

    dd = group_stats(d, "DD", order=DD_ORDER)
    parts.append(sub("Down & distance faced", table(
        ["Situation", "Snaps", "Opp. run %", "Yds/run", "Yds/pass", "Success"],
        [[esc(r["key"]), str(r["n"]), f"{r['run_pct'] * 100:.0f}%", num(r["run_avg"]), num(r["pass_avg"]),
          pct(r["succ"] * 100, 100) if r["succ"] is not None else "–"] for r in dd],
        numeric_cols=(1, 2, 3, 4, 5))))

    rows = []
    for gnum, g in d.groupby("GAME_NUM"):
        k = g[g["SCRIMMAGE"]]
        sc = k["SUCCESS"].dropna()
        rows.append([esc(g["GAME"].iloc[0]), str(int(g["KIND"].notna().sum())),
                     num(k[k["KIND"] == "Run"]["GAIN"].mean()), num(k[k["KIND"] == "Pass"]["GAIN"].mean()),
                     pct(sc.sum(), len(sc)), str(int(k["EXPLOSIVE"].sum())), str(int(g["IS_TURNOVER"].sum()))])
    parts.append(sub("By game", table(["Opponent", "Snaps", "Yds/run", "Yds/pass", "Success", "Expl.", "INT + fumbles"],
                                      rows, numeric_cols=(1, 2, 3, 4, 5, 6))))

    big = d[d["EXPLOSIVE"] | d["IS_TURNOVER"] | d["RESULT"].str.contains("Sack")].sort_values(["GAME_NUM", "PLAY #"])
    parts.append(sub("Explosives allowed, sacks & takeaways", play_list(big, ctx)))
    return section(f"{team} defense", "Offense - OL, QB, RB, Y, WR", "".join(parts), "defense")


# ---------------------------------------------------------------- special teams
def special_section(k: pd.DataFrame, ctx: Ctx, team: str) -> str:
    k = k[~k["IS_TIMEOUT"]].copy()
    k["KICKER"] = k["KICKING_TEAM"].map({"scouted": f"{team} kicking", "opponent": "Opponent kicking"})
    parts = [f'<p class="note">Kicking team is worked out from possession (Hudl\'s KO / Onside / Fake Punt tags '
             f'don\'t say who kicked). Kick and return yards are not tagged - use the clips.</p>']
    for who in (f"{team} kicking", "Opponent kicking"):
        g = k[k["KICKER"] == who]
        if g.empty:
            continue
        ct = pd.crosstab([g["UNIT"], g["RESULT"]], g["GAME"])
        ct["Total"] = ct.sum(axis=1)
        rows = []
        for (unit, res), r in ct.iterrows():
            clips = g[(g["UNIT"] == unit) & (g["RESULT"] == res)].sort_values(["GAME_NUM", "PLAY #"])
            rows.append([esc(unit), esc(res)] + [str(v) if v else "" for v in r.values] + [ctx.clips(clips, 10)])
        title = who if who != "Opponent kicking" else f"Opponent kicking ({team} receiving / defending PATs)"
        parts.append(sub(title, table(["Unit", "Result"] + [esc(c) for c in ct.columns] + ["Clips"], rows,
                                      numeric_cols=tuple(range(2, len(ct.columns) + 2)))))
    notable = k[k["UNIT"].isin(["Onside kick", "Fake punt", "2-pt try", "Field goal"]) |
                k["RESULT"].str.contains("Fumble|Recovered|Penalty|No Good", na=False)]
    rows = [[ctx.clip(r), f"Q{int(r['QTR'])}" if pd.notna(r["QTR"]) else "", esc(r["KICKER"]), esc(r["UNIT"]),
             esc(r["RESULT"])] for _, r in notable.sort_values(["GAME_NUM", "PLAY #"]).iterrows()]
    parts.append(sub("Onside, fakes, 2-pt, FG & other notable snaps",
                     table(["Clip", "Qtr", "Kicking", "Unit", "Result"], rows)))
    return section(f"{team} special teams", "Special teams", "".join(parts), "special")


# ---------------------------------------------------------------- key facts
def key_facts(p: pd.DataFrame, team: str) -> list[str]:
    facts = []
    o = p[p["SIDE"] == "offense"]
    called = o[o["KIND"].notna()]
    if len(called):
        facts.append(f"{team} ran on {pct((called['KIND'] == 'Run').sum(), len(called))} of {len(called)} offensive snaps.")
        vc = o["PLAY_FAMILY"].value_counts()
        top = ", ".join(f"{n} ({c})" for n, c in vc.head(3).items())
        facts.append(f"Most-called play families: {top}.")
    for r in group_stats(o, "FORM_FAMILY", min_n=8):
        if r["run_pct"] >= 0.85 or r["run_pct"] <= 0.25:
            facts.append(f"From {r['key']} ({r['n']} snaps) they ran {r['run_pct'] * 100:.0f}% of the time; "
                         f"top calls: {top_calls(r['g'])}.")
    for r in group_stats(o, "DD", order=DD_ORDER, min_n=6):
        if r["run_pct"] >= 0.85 or r["run_pct"] <= 0.25:
            facts.append(f"On {r['key']} ({r['n']} snaps) they ran {r['run_pct'] * 100:.0f}%.")
    mot = o[o["HAS_MOTION"] & o["KIND"].notna()]
    w, n = share(mot["DIR_VS_MOTION"], "With motion")
    if n >= 8:
        facts.append(f"With motion, the play went the same direction as the motion {pct(w, n)} of the time ({n} snaps).")
    k = p[(p["SIDE"] == "special") & (p["KICKING_TEAM"] == "scouted")]
    onside = int((k["UNIT"] == "Onside kick").sum())
    fakes = int((k["UNIT"] == "Fake punt").sum())
    if onside or fakes:
        facts.append(f"Kicking game: {team} tried {onside} onside kick(s) and {fakes} fake punt(s) "
                     f"in {p['GAME_NUM'].nunique()} games.")
    fourth = o[(o["DN"] == 4) & o["KIND"].notna()]
    if len(fourth) >= 3:
        facts.append(f"{team} went for it on 4th down {len(fourth)} times in {p['GAME_NUM'].nunique()} games.")
    return facts  # already HTML (names are escaped where they're built)


# ---------------------------------------------------------------- staff-written markdown
def md_to_html(text: str, ctx: Ctx, base_level: int = 3) -> str:
    """Small markdown subset: #/##/### headings, '- ' bullets (2-space nesting), **bold**, paragraphs.
    Clip labels like FOS-12 become video links."""
    def inline(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        return ctx.link_labels(s)

    out, depth, para = [], 0, []

    def flush_para():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()

    def set_depth(n):
        nonlocal depth
        while depth < n:
            out.append("<ul>")
            depth += 1
        while depth > n:
            out.append("</ul>")
            depth -= 1

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.lstrip()
        if not stripped:
            flush_para()
            set_depth(0)
            continue
        if stripped.startswith("#"):
            flush_para()
            set_depth(0)
            hashes = len(stripped) - len(stripped.lstrip("#"))
            level = min(6, base_level + hashes - 1)
            out.append(f"<h{level}>{inline(stripped[hashes:].strip())}</h{level}>")
        elif stripped.startswith(("- ", "* ")):
            flush_para()
            set_depth((len(line) - len(stripped)) // 2 + 1)
            out.append(f"<li>{inline(stripped[2:])}</li>")
        else:
            set_depth(0)
            para.append(stripped)
    flush_para()
    set_depth(0)
    return "".join(out)


# ---------------------------------------------------------------- page
CSS = """
:root{color-scheme:light;--bg:#fcfcfb;--surface:#ffffff;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8984;--line:#e4e3de;
--accent:#2a78d6;--accent-soft:#2a78d61f;--callout:#fff7e6;--callout-line:#eda100}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#141413;--surface:#1a1a19;
--ink:#ffffff;--ink2:#c3c2b7;--muted:#8f8e86;--line:#2e2e2b;--accent:#3987e5;--accent-soft:#3987e533;--callout:#2a2414;--callout-line:#c98500}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#141413;--surface:#1a1a19;--ink:#ffffff;--ink2:#c3c2b7;--muted:#8f8e86;
--line:#2e2e2b;--accent:#3987e5;--accent-soft:#3987e533;--callout:#2a2414;--callout-line:#c98500}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 64px}
header h1{margin:0 0 4px;font-size:26px}header p{margin:0;color:var(--ink2)}
nav{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}nav a{padding:6px 12px;border:1px solid var(--line);border-radius:999px;color:var(--ink);text-decoration:none}
section{margin-top:32px}h2{font-size:21px;border-bottom:2px solid var(--ink);padding-bottom:6px;display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap}
.aud{font-size:13px;font-weight:500;color:var(--ink2)}h3{font-size:16px;margin:24px 0 6px}
.note{color:var(--ink2);margin:0 0 8px;font-size:13px}.muted{color:var(--muted)}
.callout{background:var(--callout);border-left:4px solid var(--callout-line);padding:10px 12px;border-radius:4px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.tlabel{color:var(--ink2);font-size:12px}.tvalue{font-size:24px;font-weight:600;margin:2px 0}.tsub{color:var(--muted);font-size:12px}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--ink2);font-weight:600;background:var(--bg);position:sticky;top:0}tr:last-child td{border-bottom:none}
.num{text-align:right;white-space:nowrap}
.barcell{display:flex;align-items:center;gap:8px;min-width:170px}.track{flex:0 0 100px;height:12px}
.bar{height:100%;background:var(--accent);border-radius:0 4px 4px 0}
.barcell span{white-space:nowrap;font-variant-numeric:tabular-nums}
.heat{display:inline-block;min-width:28px;padding:2px 6px;border-radius:4px;background:rgb(from var(--accent) r g b / var(--a));text-align:center}
a.clip{color:var(--accent);text-decoration:none;white-space:nowrap;font-variant-numeric:tabular-nums}a.clip:hover{text-decoration:underline}
ul.facts li{margin:4px 0}
.gameplan h3{font-size:18px;margin:24px 0 4px;padding:6px 10px;background:var(--accent-soft);border-radius:6px}
.gameplan h4{font-size:15px;margin:16px 0 4px}.gameplan li{margin:4px 0}.gameplan ul ul{margin-top:2px}details{margin-top:8px}summary{cursor:pointer;font-weight:600}
@media print{nav{display:none}section{break-inside:auto}.tablewrap{overflow:visible}a.clip{color:inherit}}
"""


def build_report(p: pd.DataFrame, games: list[GameInfo], team: str, out_path: Path,
                 notes_md: str = "", gameplan_md: str = "") -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ctx = Ctx(out_path.parent, games)
    ctx.index(p)
    notes_html = f"<h3>Coach notes</h3>{md_to_html(notes_md, ctx, 4)}" if notes_md.strip() else ""
    gameplan = (f'<section id="gameplan" class="gameplan"><h2>Game plan recommendations</h2>'
                f'{md_to_html(gameplan_md, ctx, 3)}</section>') if gameplan_md.strip() else ""
    game_line = " · ".join(
        f"{g.opponent} ({g.date.strftime('%b %d') if g.date is not None else '?'})" for g in games)
    labels = ", ".join(f"{ctx.labels[i]} = {g.opponent}" for i, g in enumerate(games, 1))
    facts = "".join(f"<li>{f}</li>" for f in key_facts(p, team))
    appendix = "".join(
        f"<details><summary>{esc(g.opponent)} - all plays</summary>"
        f"{play_list(p[p['GAME_NUM'] == i].sort_values('PLAY #'), ctx)}</details>"
        for i, g in enumerate(games, 1))
    body = f"""
<main>
<header><h1>{esc(team)} scouting report</h1>
<p>Games scouted: {esc(game_line)}. Built from Hudl breakdowns ({len(p)} tagged snaps).</p>
<p class="muted">Clip labels: {esc(labels)} - click a label to open that play's video.</p></header>
<nav><a href="#keys">Key facts</a>{'<a href="#gameplan">Game plan</a>' if gameplan else ''}<a href="#offense">{esc(team)} offense</a><a href="#defense">{esc(team)} defense</a>
<a href="#special">Special teams</a><a href="#appendix">All plays</a></nav>
<section id="keys"><h2>Key facts</h2><ul class="facts">{facts}</ul>{notes_html}
<p class="note">Success = gain of 40% of the distance on 1st down, 60% on 2nd, 100% on 3rd/4th. Penalty and timeout rows
are counted as calls but left out of yardage and success.</p></section>
{gameplan}
{offense_section(p[p['SIDE'] == 'offense'], ctx, team)}
{defense_section(p[p['SIDE'] == 'defense'], ctx, team)}
{special_section(p[p['SIDE'] == 'special'], ctx, team)}
<section id="appendix"><h2>All plays</h2>{appendix}</section>
</main>"""
    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>{esc(team)} Scouting Report</title><style>{CSS}</style></head><body>{body}</body></html>')
    out_path.write_text(doc, encoding="utf-8")
    return out_path
