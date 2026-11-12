"""Build an opponent's offensive playbook (scout cards) from the Hudl breakdowns.

    python -m filmtools.playbook "F:\\CHSFootball\\Opponents\\<Team>"

Writes <Team>\\Offensive Playbook\\:
    <Team> Offensive Playbook.html   - one card per play concept: formation diagram, each player's
                                       route/assignment, how often and when it was called, clip links
    plays.csv                        - every tagged offensive snap with its concept and parsed routes
Optional staff file <Team>\\Offensive Playbook\\formations.txt overrides formation alignments:
    TRIPS OPEN: X -20 0, Z 20 0, H 8 -1, Y 13 -1, QB 0 -5, RB -2 -5
(x = yards from the ball, + to the right; y = depth, negative = behind the line).

What's drawn is the tagger's formation name and route call, laid onto a standard alignment. Hudl
doesn't record exact splits, so spacing is approximate - every card links to its clips to confirm.
"""
from __future__ import annotations

import html
import math
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from .loader import load_team

# --------------------------------------------------------------------------- formations
# Receivers listed left -> right; offense moves up the page.
FORMATIONS: dict[str, dict] = {
    "DOUBLES OPEN": {"X": (-20, 0), "H": (-11, -1), "Y": (11, -1), "Z": (20, 0), "QB": (0, -5), "RB": (2.5, -5)},
    "DOUBLES STACK": {"X": (-18, 0), "H": (-17, -2.5), "Y": (17, -2.5), "Z": (18, 0), "QB": (0, -5), "RB": (2.5, -5)},
    "PISTOL DOUBLES OPEN": {"X": (-20, 0), "H": (-11, -1), "Y": (11, -1), "Z": (20, 0), "QB": (0, -4), "RB": (0, -7)},
    "PISTOL DOUBLES STACK": {"X": (-18, 0), "H": (-17, -2.5), "Y": (17, -2.5), "Z": (18, 0), "QB": (0, -4), "RB": (0, -7)},
    "TRIPS OPEN": {"X": (-20, 0), "H": (8, -1), "Y": (13, -1), "Z": (20, 0), "QB": (0, -5), "RB": (-2.5, -5)},
    "PISTOL TRIPS OPEN": {"X": (-20, 0), "H": (8, -1), "Y": (13, -1), "Z": (20, 0), "QB": (0, -4), "RB": (0, -7)},
    "EMPTY RIGHT": {"X": (-20, 0), "H": (-11, -1), "S": (7, -1), "Y": (13, -1), "Z": (20, 0), "QB": (0, -5)},
    "EMPTY LEFT": {"X": (-20, 0), "Y": (-13, -1), "S": (-7, -1), "H": (11, -1), "Z": (20, 0), "QB": (0, -5)},
    "EMPTY": {"X": (-20, 0), "H": (-11, -1), "S": (7, -1), "Y": (13, -1), "Z": (20, 0), "QB": (0, -5)},
    # Unbalanced: extra lineman/TE on the right, wing off him, direct-snap back next to the QB.
    "UNBALANCED WING RIGHT": {"X": (-18, 0), "TE": (6, 0), "W": (7.5, -1.2), "Z": (18, 0), "QB": (0, -5), "FB": (2.5, -5)},
    # Inline TE (Y) on the right; FLEX = TE detached a few yards outside the tackle; WING = wingback off the TE.
    "DOUBLES OPEN FLEX": {"X": (-20, 0), "H": (-11, -1), "Y": (8, -1), "Z": (20, 0), "QB": (0, -5), "RB": (2.5, -5)},
    "DOUBLES WING OPEN": {"X": (-20, 0), "H": (-11, -1), "Y": (6, 0), "W": (7.5, -1.2), "Z": (20, 0), "QB": (0, -5), "RB": (0, -7.5)},
    "INVERTED DOUBLES OPEN": {"X": (-13, -1), "H": (-20, 0), "Y": (13, -1), "Z": (20, 0), "QB": (0, -5), "RB": (2.5, -5)},
    "TRIP OPEN": {"X": (-20, 0), "H": (8, -1), "Y": (13, -1), "Z": (20, 0), "QB": (0, -5), "RB": (-2.5, -5)},
    "INVERTED TRIPS OPEN": {"X": (-20, 0), "H": (8, -1), "Y": (20, 0), "Z": (14, -1), "QB": (0, -5), "RB": (-2.5, -5)},
    "TREY OPEN": {"X": (-20, 0), "Y": (6, 0), "H": (12, -1), "Z": (20, 0), "QB": (0, -5), "RB": (-2.5, -5)},
    "EMPTY LEFT FLEX": {"X": (-20, 0), "Y": (-8, -1), "S": (-13, -1), "H": (11, -1), "Z": (20, 0), "QB": (0, -5)},
    "BUNCH OPEN": {"X": (-20, 0), "H": (9, -1.5), "Y": (8, 0), "Z": (10.5, -0.5), "QB": (0, -5), "RB": (-2.5, -5)},
    "DOUBLES BUNCH STACK": {"X": (-12, 0), "H": (-12, -2.5), "Y": (8, 0), "Z": (9.5, -1.5), "QB": (0, -5), "RB": (2.5, -5)},
    "PISTOL DOUBLES BUNCH STACK": {"X": (-12, 0), "H": (-12, -2.5), "Y": (8, 0), "Z": (9.5, -1.5), "QB": (0, -4), "RB": (0, -7)},
    "WILDCAT DOUBLES OPEN": {"X": (-20, 0), "QB": (-14, -1), "Y": (11, -1), "Z": (20, 0), "RB": (0, -5), "H": (2.5, -5)},
    # I formations: FB + TB stacked behind QB under center. Pro = TE right, flanker right, split end left.
    "I PRO": {"X": (-18, 0), "Y": (6, 0), "Z": (14, -1), "QB": (0, -1), "FB": (0, -4), "RB": (0, -6.5)},
    "I KING": {"X": (-18, 0), "Y": (6, 0), "Z": (18, 0), "H": (12, -1), "QB": (0, -1), "FB": (0, -4), "RB": (0, -6.5)},
    "I QUEEN": {"X": (-18, 0), "H": (-12, -1), "Y": (6, 0), "QB": (0, -1), "FB": (0, -4), "RB": (0, -6.5)},
    # Not confirmed on film: drawn as 2x1 with a second back.
    "QUEENS": {"X": (-20, 0), "H": (-11, -1), "Z": (20, 0), "QB": (0, -5), "FB": (-2.5, -5), "RB": (2.5, -5)},
}
# Formation names whose alignment is a guess from how the set is used (not a standard Hudl name).
UNCONFIRMED = {"I KING": "King / Queen are this tagger's labels; drawn as I with twins to the TE (King) or away (Queen). Check a clip.",
               "I QUEEN": "King / Queen are this tagger's labels; drawn as I with twins to the TE (King) or away (Queen). Check a clip.",
               "QUEENS": "Alignment not confirmed on film; drawn as a two-back 2x1 set. Check a clip before practice."}
OL = [(-4, 0), (-2, 0), (0, 0), (2, 0), (4, 0)]
OL_UNBAL = [(-2, 0), (0, 0), (2, 0), (4, 0), (6, 0)]   # unbalanced: line shifted right; TE drawn separately

ROUTE_WORDS = {"HITCH", "HITCHES", "OUT", "OUTS", "SEAM", "SEAMS", "GO", "GOS", "9", "9S", "DIG", "DIGS", "POST",
               "CORNER", "CURL", "DRAG", "SLANT", "SLANTS", "FLAT", "BUBBLE", "WHEEL", "SWING", "MESH", "DEEP OUT",
               "DEEP OUTS", "QUICK OUT"}
NORMAL = {"HITCHES": "HITCH", "OUTS": "OUT", "SEAMS": "SEAM", "GOS": "GO", "9": "GO", "9S": "GO", "DIGS": "DIG",
          "SLANTS": "SLANT", "DEEP OUTS": "DEEP OUT"}


def formation_key(form) -> str | None:
    if form is None or (isinstance(form, float) and math.isnan(form)) or pd.isna(form):
        return None
    f = re.sub(r"\s+", " ", str(form).upper().replace("DOULBES", "DOUBLES")).strip()
    return f


def read_overrides(book_dir: Path) -> None:
    p = book_dir / "formations.txt"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        name, spec = line.split(":", 1)
        spec, _, note = spec.partition("|")   # "| note" = drawn from the name, not measured on film
        pos = {}
        for part in spec.split(","):
            m = re.match(r"\s*([A-Z]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*$", part.upper())
            if m:
                pos[m.group(1)] = (float(m.group(2)), float(m.group(3)))
        if pos:
            FORMATIONS[name.strip().upper()] = pos
            if note.strip():
                UNCONFIRMED[name.strip().upper()] = note.strip()
            else:
                UNCONFIRMED.pop(name.strip().upper(), None)


# --------------------------------------------------------------------------- play parsing
MOTION_RE = re.compile(r"\b(YOYO MOTION|BACK MOTION|HB MOTION|WING MOTION|MOTION)\b")


def split_motion(play: str) -> tuple[str, str | None]:
    m = MOTION_RE.search(play)
    if not m:
        return play.strip(), None
    rest = (play[:m.start()] + play[m.end():]).strip()
    return re.sub(r"\s+", " ", rest), m.group(1).title()


RUN_CONCEPTS = [("TRIPLE OPTION", "Triple option"), ("ZONE READ", "Zone read"), ("ZON READ", "Zone read"),
                ("INSIDE ZONE", "Inside zone"), ("QB DRAW", "QB draw"), ("QB SWEEP", "QB sweep"), ("QB LEAD", "QB lead"),
                ("DIRECT SNAP LEAD", "Direct-snap lead"), ("DIRECT SNAP", "FB direct snap"), ("HB SWEEP", "HB sweep"),
                ("HB LEAD", "HB lead"), ("TOSS", "HB toss"), ("WING AROUND", "Wing around"), ("WING UNDER", "Wing under"),
                ("#3 FLAT", "#3 flat (jet)")]


def classify(play: str, kind: str | None) -> tuple[str, str, str | None]:
    """-> (concept name, run|pass|screen, motion)"""
    base, motion = split_motion(play)
    for key, name in RUN_CONCEPTS:
        if key in base:
            return name, "run", motion
    if "SWING" in base and len(base.split()) <= 3:
        return "HB swing" + (" screen" if "SCREEN" in base else ""), "screen", motion
    if "SCREEN" in base or base.startswith("KEY"):
        return base.title().replace("Wr", "WR").replace("Hb", "HB"), "screen", motion
    if base in ("RPO", "SPRINT OUT"):
        return base.title() if base != "RPO" else "RPO", "pass", motion
    return base.title().replace("Hb", "HB").replace("P/A", "P/A"), "pass" if kind != "Run" else "run", motion


def parse_routes(base: str, receivers: list[str], backs: list[str]) -> tuple[dict[str, str], bool]:
    """Map the tagger's route call to receivers (left -> right). Returns (assignments, exact?)."""
    s = base.upper().replace("&", " ").replace(" AND ", " ").replace("'", "")
    s = re.sub(r"\b9S\b", "GO", s)
    s = s.replace("DEEP OUTS", "DEEPOUTS").replace("DEEP OUT ", "DEEPOUT ").replace("GO S", "GOS")
    s = s.replace("SPRINT OUT", " ")                  # QB action, not a route
    out: dict[str, str] = {}
    # backfield routes
    for m in re.finditer(r"\bHB (FLAT|SWING|WHEEL|DIG)\b", s):
        if backs:
            out[backs[-1]] = m.group(1)
    s = re.sub(r"\bHB (FLAT|SWING|WHEEL|DIG)\b", " ", s)
    s = re.sub(r"\b(P/A|\d{2,})\b", " ", s)      # play-action tag / numeric route codes we don't decode
    tokens = [t for t in s.split() if t]
    norm = {"HITCHES": "HITCH", "OUTS": "OUT", "SEAMS": "SEAM", "GOS": "GO", "9": "GO", "DIGS": "DIG", "SLANTS": "SLANT",
            "DEEPOUT": "DEEP OUT", "DEEPOUTS": "DEEP OUT", "CURLS": "CURL", "POSTS": "POST", "FLATS": "FLAT"}
    routes = [norm.get(t, t) for t in tokens if norm.get(t, t) in
              {"HITCH", "OUT", "SEAM", "GO", "DIG", "POST", "CORNER", "CURL", "DRAG", "SLANT", "FLAT", "BUBBLE",
               "WHEEL", "DEEP OUT", "MESH"}]
    if not routes:
        return out, False
    n = len(receivers)
    if tokens and tokens[0] == "ALL":
        return {**{r: routes[0] for r in receivers}, **out}, True
    if routes == ["MESH"]:
        inside = receivers[1:-1] or receivers
        for r in receivers:
            out[r] = "DRAG" if r in inside[:2] else "GO"
        return out, False
    plural = [t for t in tokens if t.endswith("S") and norm.get(t, t) != t]
    if len(routes) == 2 and len(plural) == 2:          # "DEEP OUTS SEAMS": outside get 1st, inside get 2nd
        for i, r in enumerate(receivers):
            outside = i == 0 or i == n - 1
            out[r] = routes[0] if outside else routes[1]
        return out, True
    if len(routes) == 2 and len(plural) == 1:          # "HITCHES OUTS"/"OUT SEAM HITCHES" style
        pl = norm.get(plural[0], plural[0])
        other = [r for r in routes if r != pl]
        for i, r in enumerate(receivers):
            out[r] = pl
        if other:
            out[receivers[0]] = other[0]
        return out, False
    exact = len(routes) == n
    for i, r in enumerate(receivers):
        if i < len(routes):
            out[r] = routes[i]
    return out, exact


# --------------------------------------------------------------------------- drawing
SCALE, W, H = 13.0, 640, 330   # px per yard; svg size
OX, OY = W / 2, 215           # ball position


def P(x, y):
    return OX + x * SCALE, OY - y * SCALE


def route_path(route: str, x: float, y: float) -> list[tuple[float, float]]:
    side = -1 if x < 0 else 1          # toward own sideline
    inn = -side
    pts = {"HITCH": [(0, 5), (inn * 0.6, 4)], "OUT": [(0, 8), (side * 5, 8)], "DEEP OUT": [(0, 13), (side * 6, 12)],
           "SEAM": [(inn * 1, 4), (inn * 1, 18)], "GO": [(0, 19)], "DIG": [(0, 11), (inn * 9, 11)],
           "POST": [(0, 10), (inn * 6, 18)], "CORNER": [(0, 9), (side * 6, 15)], "CURL": [(0, 10), (inn * 1.2, 8.5)],
           "DRAG": [(inn * 2, 2), (inn * 13, 2.5)], "SLANT": [(0, 2), (inn * 6, 7)], "FLAT": [(side * 1.5, 2), (side * 7, 3)],
           "BUBBLE": [(side * 2, -1.5), (side * 6, 0)], "WHEEL": [(side * 4, 1), (side * 6, 4), (side * 6, 16)],
           "SWING": [(side * 4, -1), (side * 9, 1)]}.get(route)
    if pts is None:
        return []
    return [(x, y)] + [(max(-23.5, min(23.5, x + dx)), y + dy) for dx, dy in pts]   # stay on the field


def run_path(concept: str, positions: dict, play_dir: str | None) -> list[tuple[list, str]]:
    d = 1 if play_dir == "R" else -1
    qb = positions.get("QB", (0, -5))
    back = next((positions[k] for k in ("RB", "FB") if k in positions), (2.5, -5))
    c = concept.lower()
    paths = []
    if "sweep" in c or "toss" in c or "around" in c:
        carrier = qb if c.startswith("qb") else back
        paths.append(([carrier, (carrier[0] + d * 5, carrier[1] - 0.5), (d * 12, 1), (d * 14, 8)], "carry"))
        if "toss" in c:
            paths.append(([qb, (carrier[0], carrier[1])], "pitch"))
    elif "lead" in c:
        carrier = qb if c.startswith("qb") else back
        lead = positions.get("FB") if carrier != positions.get("FB") else positions.get("W")
        hole = d * 3
        paths.append(([carrier, (hole * 0.6, -2), (hole, 1), (hole, 7)], "carry"))
        if lead:
            paths.append(([lead, (hole * 0.8, -0.5), (hole, 3)], "lead"))
    elif "zone read" in c or "inside zone" in c or "option" in c:
        paths.append(([back, (-d * 0.5 + 0.5 * d, -3), (d * 1.5, 1), (d * 2, 7)], "carry"))
        if "read" in c or "option" in c:
            paths.append(([qb, (-d * 4, -4.5), (-d * 8, 2)], "keep"))
        if "option" in c:
            paths.append(([(-d * 6, -1), (-d * 10, -1.5)], "pitch"))
    elif "draw" in c:
        paths.append(([qb, (qb[0], qb[1] - 1.5), (0.5, 1), (0.5, 7)], "carry"))
    elif "direct snap" in c or "wing under" in c:
        carrier = positions.get("FB", back) if "fb" in c or "direct" in c else positions.get("W", back)
        paths.append(([carrier, (carrier[0] + d * 0.5, -2), (d * 2.5, 1), (d * 2.5, 6)], "carry"))
    elif "flat" in c:
        paths.append(([positions.get("H", (8, -1)), (2, -3), (-10, -2)], "motion"))
    return paths


def svg_card(positions: dict, routes: dict, concept: str, kind: str, motion: str | None, play_dir: str | None,
             unbalanced: bool, compact: bool = False) -> str:
    top = OY - 4 * SCALE if compact else 0          # formation-only cards: trim the empty field above the LOS
    out = [f'<svg viewBox="0 {top:.0f} {W} {H - top:.0f}" class="diagram" role="img" aria-label="{html.escape(concept)} diagram">',
           f'<rect x="0" y="0" width="{W}" height="{H}" class="turf"/>']
    for yd in range(-6, 22, 5):
        y = OY - yd * SCALE
        out.append(f'<line x1="0" x2="{W}" y1="{y:.0f}" y2="{y:.0f}" class="yardline"/>')
    out.append(f'<line x1="0" x2="{W}" y1="{OY:.0f}" y2="{OY:.0f}" class="los"/>')
    for (x, y) in (OL_UNBAL if unbalanced else OL):
        cx, cy = P(x, y)
        out.append(f'<rect x="{cx - 7:.1f}" y="{cy - 7:.1f}" width="14" height="14" class="ol"/>')
    # routes
    for name, route in routes.items():
        if name not in positions:
            continue
        pts = route_path(route, *positions[name])
        if pts:
            d = " ".join(f"{'M' if i == 0 else 'L'}{P(*p)[0]:.1f},{P(*p)[1]:.1f}" for i, p in enumerate(pts))
            out.append(f'<path d="{d}" class="route" marker-end="url(#arrow)"/>')
            lx, ly = P(*pts[-1])
            out.append(f'<text x="{lx:.0f}" y="{ly - 6:.0f}" class="rlabel">{html.escape(route.lower())}</text>')
    if kind == "run":
        for pts, style in run_path(concept, positions, play_dir):
            d = " ".join(f"{'M' if i == 0 else 'L'}{P(*p)[0]:.1f},{P(*p)[1]:.1f}" for i, p in enumerate(pts))
            out.append(f'<path d="{d}" class="run {style}" marker-end="url(#arrow)"/>')
    if motion:
        mover = next((k for k in ("H", "Y", "W", "RB") if k in positions), None)
        if mover:
            x, y = positions[mover]
            tx = -x * 0.6 if "Yoyo" not in motion else x * 0.3
            a, b = P(x, y), P(tx, y - 0.5)
            out.append(f'<path d="M{a[0]:.1f},{a[1]:.1f} L{b[0]:.1f},{b[1]:.1f}" class="motion" marker-end="url(#arrow)"/>')
    for name, (x, y) in positions.items():
        cx, cy = P(x, y)
        cls = "qb" if name == "QB" else "skill"
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="11" class="{cls}"/>')
        out.append(f'<text x="{cx:.1f}" y="{cy + 4:.1f}" class="plabel">{html.escape(name)}</text>')
    out.append('<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" '
               'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="arrowhead"/></marker></defs></svg>')
    return "".join(out)


# --------------------------------------------------------------------------- page
CSS = """
:root{color-scheme:light;--bg:#fcfcfb;--surface:#fff;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8984;--line:#e4e3de;
--accent:#2a78d6;--turf:#eef5ee;--yard:#d5e3d5;--route:#c2410c;--run:#1d4ed8;--ol:#9ca3af;--warn:#fff7e6;--warnline:#eda100}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#141413;--surface:#1a1a19;--ink:#fff;
--ink2:#c3c2b7;--muted:#8f8e86;--line:#2e2e2b;--accent:#3987e5;--turf:#17231a;--yard:#2a3a2c;--route:#fb923c;--run:#60a5fa;--ol:#6b7280;
--warn:#2a2414;--warnline:#c98500}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#141413;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#8f8e86;--line:#2e2e2b;
--accent:#3987e5;--turf:#17231a;--yard:#2a3a2c;--route:#fb923c;--run:#60a5fa;--ol:#6b7280;--warn:#2a2414;--warnline:#c98500}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 64px}h1{margin:0 0 4px;font-size:26px}h2{font-size:20px;margin:32px 0 8px;border-bottom:2px solid var(--ink);padding-bottom:4px}
.note{color:var(--ink2);font-size:13px}.callout{background:var(--warn);border-left:4px solid var(--warnline);padding:10px 12px;border-radius:4px;margin:12px 0}
nav{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}nav a{padding:4px 10px;border:1px solid var(--line);border-radius:999px;color:var(--ink);text-decoration:none;font-size:13px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(520px,1fr));gap:16px}
@media (max-width:600px){.cards{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px;break-inside:avoid}
.card h3{margin:0 0 2px;font-size:17px}.meta{color:var(--ink2);font-size:12.5px;margin-bottom:6px}
.badge{display:inline-block;font-size:11px;padding:1px 7px;border-radius:999px;border:1px solid var(--line);margin-right:4px;color:var(--ink2)}
.diagram{width:100%;height:auto;border-radius:6px;display:block}.turf{fill:var(--turf)}.yardline{stroke:var(--yard);stroke-width:1}
.los{stroke:var(--ink2);stroke-width:1.5;stroke-dasharray:4 4}.ol{fill:var(--surface);stroke:var(--ol);stroke-width:2}
.skill{fill:var(--surface);stroke:var(--ink);stroke-width:2}.qb{fill:var(--ink);stroke:var(--ink)}
.plabel{font-size:10px;font-weight:700;text-anchor:middle;fill:var(--ink)}.qb+.plabel{fill:var(--surface)}
.route{fill:none;stroke:var(--route);stroke-width:2.5}.run{fill:none;stroke:var(--run);stroke-width:2.5}.run.keep,.run.pitch{stroke-dasharray:6 4}
.run.lead{stroke-width:2;stroke-dasharray:2 3}.motion{fill:none;stroke:var(--muted);stroke-width:2;stroke-dasharray:3 4}
.arrowhead{fill:var(--ink2)}.rlabel{font-size:10px;fill:var(--route);text-anchor:middle}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin-top:6px}td,th{padding:3px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--ink2);font-weight:600}a.clip{color:var(--accent);text-decoration:none;white-space:nowrap}a.clip:hover{text-decoration:underline}
.legend span{display:inline-block;margin-right:14px;font-size:12px;color:var(--ink2)}.legend i{display:inline-block;width:22px;height:0;border-top:3px solid;vertical-align:middle;margin-right:5px}
@media print{nav{display:none}.cards{grid-template-columns:1fr 1fr}.card{page-break-inside:avoid}}
"""


def esc(x) -> str:
    return html.escape("" if x is None or (not isinstance(x, str) and pd.isna(x)) else str(x))


def render(team_dir: Path, plays: pd.DataFrame, games, out_dir: Path) -> dict:
    """Build the playbook pieces; clip links are relative to out_dir (so the report can embed them).

    Returns {"intro", "legend", "formations", "n_formations", "sections": {ctype: (title, n, html)}, "csv_rows"}.
    """
    from . import tendencies as T
    read_overrides(team_dir / "Offensive Playbook")
    book = out_dir
    labels = {i: re.sub(r"[^A-Za-z]", "", g.opponent)[:3].upper() for i, g in enumerate(games, 1)}
    o = plays[(plays["SIDE"] == "offense") & plays["KIND"].notna()].copy()
    o["LABEL"] = [f"{labels[g]}-{int(n)}" for g, n in zip(o["GAME_NUM"], o["PLAY #"])]
    o["FKEY"] = o["OFF FORM"].map(formation_key)
    o["DOWN"] = o["DN"].map(lambda d: T.DOWN_NAMES.get(int(d)) if pd.notna(d) else None)
    t = o[o["PLAY"].notna()].copy()
    cls = [classify(p, k) for p, k in zip(t["PLAY"], t["KIND"])]
    t["CONCEPT"] = [c[0] for c in cls]
    t["CTYPE"] = [c[1] for c in cls]
    t["MOTION"] = [c[2] for c in cls]

    def clip_link(r):
        if r["CLIP"] is None or pd.isna(r["CLIP"]):
            return esc(r["LABEL"])
        rel = os.path.relpath(r["CLIP"], book).replace(os.sep, "/")
        return f'<a class="clip" href="{quote(rel)}">{esc(r["LABEL"])}</a>'

    # ---- formation cards: alignment diagram + what they do from it
    fcards = []
    for fkey, g in o.groupby("FKEY"):
        g = g.sort_values(["GAME_NUM", "PLAY #"])
        positions = FORMATIONS.get(fkey)
        svg = svg_card(positions or FORMATIONS["DOUBLES OPEN"], {}, fkey, "pass", None, None, "UNBALANCED" in fkey, compact=True)
        L = T.lean(g)
        downs = []
        for d in T.DOWN_NAMES.values():
            x = g[g["DOWN"] == d]
            if len(x):
                r = int((x["KIND"] == "Run").sum())
                downs.append(f"<td>{esc(d)}: <b>{r}R / {len(x) - r}P</b></td>")
        top = t[t["FKEY"] == fkey]["CONCEPT"].value_counts().head(5)
        n_rz = int((g["YDS_TO_GOAL"] <= 20).sum())
        flags = []
        if positions is None:
            flags.append(f"No template for '{fkey}' - drawn as Doubles Open. Add it to formations.txt.")
        if fkey in UNCONFIRMED:
            flags.append(UNCONFIRMED[fkey])
        exp = f"{L['expect'].upper()} {100 * L['expect_pct']:.0f}% ({L['conf']})" if L["n"] else ""
        fcards.append((len(g), f'<div class="card"><h3>{esc(fkey.title())}</h3>'
                       f'<div class="meta"><span class="badge">{len(g)} snaps</span>{L["runs"]} run / {L["passes"]} pass'
                       f' · expect <b>{esc(exp)}</b>{f" · {n_rz} red-zone snaps" if n_rz else ""}</div>{svg}'
                       f'<table><tr>{"".join(downs)}</tr></table>'
                       f'<p class="note">Called from it: {esc(", ".join(f"{k} {v}" for k, v in top.items()) or "-")}</p>'
                       + "".join(f'<p class="callout note">{esc(f)}</p>' for f in flags)
                       + f'<p>Clips: {" ".join(clip_link(r) for _, r in g.iterrows())}</p></div>'))
    fcards.sort(key=lambda x: -x[0])

    # one card per (concept, formation)
    cards_by_type = {"run": [], "pass": [], "screen": []}
    csv_rows = []
    for concept, g in t.groupby("CONCEPT"):
        g = g.sort_values(["GAME_NUM", "PLAY #"])
        fcounts = g["FKEY"].value_counts()
        fkey = fcounts.index[0] if len(fcounts) else None
        also = ", ".join(f"{k.title()} {v}" for k, v in fcounts.items()) if len(fcounts) > 1 else ""
        ctype = g["CTYPE"].mode().iloc[0]
        positions = FORMATIONS.get(fkey) if isinstance(fkey, str) else None
        unbalanced = isinstance(fkey, str) and "UNBALANCED" in fkey
        if positions is None:
            positions = FORMATIONS["DOUBLES OPEN"]
        receivers = sorted([k for k in positions if k not in ("QB", "RB", "FB", "TE")], key=lambda k: positions[k][0])
        backs = [k for k in ("RB", "FB") if k in positions]
        base, _ = split_motion(g["PLAY"].iloc[0])
        routes, exact = parse_routes(base, receivers, backs) if ctype != "run" else ({}, True)
        motion = g["MOTION"].dropna().mode().iloc[0] if g["MOTION"].notna().any() else None
        play_dir = g["PLAY DIR"].dropna().mode().iloc[0] if g["PLAY DIR"].notna().any() else None
        scr = g[g["SCRIMMAGE"]]
        n = len(g)
        avg = scr["GAIN"].mean()
        succ = scr["SUCCESS"].dropna()
        dd = ", ".join(f"{v}×{c}" for v, c in g["DD"].dropna().value_counts().head(3).items())
        dirs = g["PLAY DIR"].dropna().value_counts()
        dir_txt = ", ".join(f"{'right' if k == 'R' else 'left'} {v}" for k, v in dirs.items())
        assign = []
        for k in sorted(positions, key=lambda k: (positions[k][1] < -2, positions[k][0])):
            if k in routes:
                assign.append(f"<tr><td><b>{esc(k)}</b></td><td>{esc(routes[k].title())}</td></tr>")
            elif ctype == "run":
                role = {"QB": "Ball handler / read" if "read" in concept.lower() or "option" in concept.lower() else "Ball handler",
                        "RB": "Ball carrier" if not concept.lower().startswith(("qb", "fb", "wing")) else "Fake / block",
                        "FB": "Ball carrier (direct snap)" if "direct" in concept.lower() else "Lead block",
                        "W": "Ball carrier" if "wing" in concept.lower() else "Block / lead"}.get(k, "Block (stalk)")
                assign.append(f"<tr><td><b>{esc(k)}</b></td><td>{esc(role)}</td></tr>")
            elif k == "QB":
                assign.append(f"<tr><td><b>QB</b></td><td>{'Play-action, ' if 'P/A' in base else ''}throw</td></tr>")
            elif k in backs:
                assign.append(f"<tr><td><b>{esc(k)}</b></td><td>Protect (not tagged)</td></tr>")
            else:
                assign.append(f"<tr><td><b>{esc(k)}</b></td><td class='note'>Not in tag - check clip</td></tr>")
        flags = []
        if fkey in UNCONFIRMED:
            flags.append(UNCONFIRMED[fkey])
        if fkey not in FORMATIONS:
            flags.append(f"Formation '{fkey}' has no template; drawn as Doubles Open.")
        if ctype != "run" and not exact:
            flags.append("The tag doesn't list a route for every receiver; assignments inferred left to right.")
        svg = svg_card(positions, routes, concept, ctype, motion, play_dir, unbalanced)
        badges = f'<span class="badge">{esc(ctype)}</span>' + (f'<span class="badge">{esc(motion)}</span>' if motion else "")
        card = (f'<div class="card"><h3>{esc(concept)} <span class="note">· {esc((fkey or "formation not tagged").title())}</span></h3>'
                f'<div class="meta">{badges} Called {n}× · avg {"-" if pd.isna(avg) else f"{avg:.1f}"} yds'
                f'{"" if not len(succ) else f" · {100 * succ.mean():.0f}% success"}{" · " + dd if dd else ""}'
                f'{" · went " + dir_txt if dir_txt else ""}</div>{svg}'
                f'<table><tr><th>Player</th><th>Assignment</th></tr>{"".join(assign)}</table>'
                + "".join(f'<p class="callout note">{esc(f)}</p>' for f in flags)
                + (f'<p class="note">Formations: {esc(also)} (drawn from the most-used one)</p>' if also else "")
                + f'<p class="note">Tagged as: {esc(", ".join(sorted(g["PLAY"].unique())))}</p>'
                f'<p>Clips: {" ".join(clip_link(r) for _, r in g.iterrows())}</p></div>')
        cards_by_type[ctype].append((n, card))
        for _, r in g.iterrows():
            csv_rows.append({"clip": r["LABEL"], "game": r["GAME"], "qtr": r["QTR"], "down": r["DN"], "dist": r["DIST"],
                             "formation": r["OFF FORM"], "play_tag": r["PLAY"], "concept": concept, "type": ctype,
                             "motion": r["MOTION"], "dir": r["PLAY DIR"], "result": r["RESULT"], "gain": r["GAIN"],
                             **{f"route_{k}": v for k, v in routes.items()}})

    per_game = ", ".join(f"{labels[i]} {int(((o['GAME_NUM'] == i) & o['PLAY'].notna()).sum())}/{int((o['GAME_NUM'] == i).sum())}"
                         for i in range(1, len(games) + 1))
    sections = {}
    for ctype, title in (("run", "Run game"), ("pass", "Pass game"), ("screen", "Screens & quick game")):
        cards = [c for _, c in sorted(cards_by_type[ctype], key=lambda x: -x[0])]
        if cards:
            sections[ctype] = (title, len(cards), '<div class="cards">' + "".join(cards) + "</div>")
    intro = ("<div class=\"callout\"><b>How to read these cards.</b> Formation and route calls are the Hudl tagger's. "
             "Players are placed on the standard alignment for that formation name; splits and depths are approximate, "
             "not measured from film. Hudl doesn't record which receiver ran which route, so routes are assigned "
             "outside-in, left to right, from the tag. Each card flags anything inferred. "
             "<b>Watch the clip before putting a card in front of the scout team.</b></div>"
             f'<p class="note">Play calls tagged: {esc(per_game)} (tagged / snaps). Offense moves up the page. '
             "Untagged snaps aren't in the play cards.</p>")
    legend = ('<div class="legend"><span><i style="border-color:var(--route)"></i>route</span>'
              '<span><i style="border-color:var(--run)"></i>ball carrier</span>'
              '<span><i style="border-color:var(--run);border-top-style:dashed"></i>QB keep / pitch</span>'
              '<span><i style="border-color:var(--muted);border-top-style:dotted"></i>motion</span></div>')
    return {"intro": intro, "legend": legend, "n_formations": len(fcards),
            "formations": '<div class="cards">' + "".join(c for _, c in fcards) + "</div>",
            "sections": sections, "csv_rows": csv_rows}


# Card/diagram styles only - safe to embed in the scouting report, which supplies the base tokens.
CARD_CSS = (CSS[CSS.index(".cards{"):].replace("@media print{nav{display:none}", "@media print{")
            .replace("table{border-collapse", ".pb table{border-collapse").replace("td,th{padding", ".pb td,.pb th{padding")
            .replace("\nth{color", "\n.pb th{color").replace(".run{", ".pb .run{").replace(".run.", ".pb .run."))
CARD_CSS += ".pb .callout{background:var(--warn);border-left:4px solid var(--warnline);padding:8px 10px;border-radius:4px;margin:8px 0}"
PB_TOKENS = (":root{--turf:#eef5ee;--yard:#d5e3d5;--route:#c2410c;--run:#1d4ed8;--ol:#9ca3af;--warn:#fff7e6;--warnline:#eda100}"
             "@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"]){--turf:#17231a;--yard:#2a3a2c;--route:#fb923c;"
             "--run:#60a5fa;--ol:#6b7280;--warn:#2a2414;--warnline:#c98500}}"
             ":root[data-theme=\"dark\"]{--turf:#17231a;--yard:#2a3a2c;--route:#fb923c;--run:#60a5fa;--ol:#6b7280;"
             "--warn:#2a2414;--warnline:#c98500}")


def build(team_dir: Path) -> Path:
    """Standalone playbook page in <team>\\Offensive Playbook\\."""
    team = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", team_dir.name)   # "ChiefSealth" -> "Chief Sealth"
    book = team_dir / "Offensive Playbook"
    book.mkdir(exist_ok=True)
    plays, games, warnings = load_team(team_dir)
    pb = render(team_dir, plays, games, book)
    secs = "".join(f'<h2 id="{k}">{t} <span class="note">({n} cards)</span></h2>{h}' for k, (t, n, h) in pb["sections"].items())
    body = (f"<main><h1>{esc(team)} offensive playbook</h1>{pb['intro']}{pb['legend']}"
            '<nav><a href="#formations">Formations</a><a href="#run">Run game</a><a href="#pass">Pass game</a>'
            '<a href="#screen">Screens</a></nav>'
            f'<h2 id="formations">Formations <span class="note">({pb["n_formations"]})</span></h2>{pb["formations"]}{secs}</main>')
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(team)} Offensive Playbook</title><style>{CSS}</style></head><body>{body}</body></html>')
    out = book / f"{team_dir.name} Offensive Playbook.html"
    out.write_text(page, encoding="utf-8")
    pd.DataFrame(pb["csv_rows"]).to_csv(book / "plays.csv", index=False)
    for w in warnings:
        print("WARNING:", w)
    return out


if __name__ == "__main__":
    print(build(Path(sys.argv[1])))
