"""Run/pass likelihood tables for the defensive game plan.

Answers "what's coming?" for the scouted offense:
  - by down, and by down & distance
  - by formation group, and formation group x down
  - in the red zone (inside the 20) and inside the 10 / goal-to-go

Every cell carries its sample size and a confidence label so small samples read as a lean, not a rule:
  n < 4                 -> "small"   (don't call it a tendency)
  >= 75% one way, n>=4  -> "lean"
  >= 85% one way, n>=6  -> "strong"

Formation groups come from FORMATION_GROUPS below (first keyword match wins). Edit them when a new
tagger's vocabulary doesn't fit.

    python -m filmtools.tendencies "F:\\CHSFootball\\Opponents\\<Team>"   # print + write tendencies.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# (group, keywords - any match) checked in order against the upper-cased formation name
FORMATION_GROUPS: list[tuple[str, list[str]]] = [
    ("Wildcat", ["WILDCAT"]),
    ("Empty", ["EMPTY"]),
    ("I-formation (2 backs)", ["I PRO", "I KING", "I QUEEN", "I SLOT", "I TWIN", "I RIGHT", "I LEFT"]),
    ("Heavy / overload", ["OVERLOAD", "OVEROAD"]),
    ("Bunch / stack", ["BUNCH", "STACK"]),
    ("Pistol", ["PISTOL"]),
    ("Trips (3x1)", ["TRIPS", "TRIP ", "TREY", "TRIO", "QUADS"]),
    ("Doubles flex", ["FLEX"]),
    ("Doubles wing", ["WING"]),
    ("Unbalanced", ["UNBALANCED", "T OVER"]),
    ("Kings / Queens (tagger label)", ["KINGS", "QUEENS"]),
    ("Doubles (2x2)", ["DOUBLES", "TWINS", "REGULAR"]),
]
DOWN_NAMES = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}


def formation_group(form) -> str | None:
    if form is None or pd.isna(form):
        return None
    f = " " + str(form).upper() + " "
    for group, words in FORMATION_GROUPS:
        if any((" " + w + " ") in f or w in f for w in words):
            return group
    return str(form).title()


def confidence(n_major: int, n: int) -> str:
    share = n_major / n if n else 0
    if n < 4:
        return "small"
    if share >= 0.85 and n >= 6:
        return "strong"
    if share >= 0.75:
        return "lean"
    return "balanced"


def lean(df: pd.DataFrame) -> dict:
    """Run/pass split for a group of snaps (KIND = Run/Pass)."""
    n = int(df["KIND"].notna().sum())
    runs = int((df["KIND"] == "Run").sum())
    passes = n - runs
    major, side = (runs, "Run") if runs >= passes else (passes, "Pass")
    s = df[df["SCRIMMAGE"]]
    return {"n": n, "runs": runs, "passes": passes, "run_pct": runs / n if n else None,
            "expect": side if n else None, "expect_pct": major / n if n else None,
            "conf": confidence(major, n), "avg": s["GAIN"].mean() if len(s) else None,
            "succ": s["SUCCESS"].dropna().mean() if s["SUCCESS"].notna().any() else None}


def offense_snaps(plays: pd.DataFrame) -> pd.DataFrame:
    o = plays[(plays["SIDE"] == "offense") & plays["KIND"].notna()].copy()
    o["FGROUP"] = o["FORMATION"].map(formation_group)
    o["DOWN"] = o["DN"].map(lambda d: DOWN_NAMES.get(int(d)) if pd.notna(d) else None)
    o["RZ"] = o["YDS_TO_GOAL"] <= 20
    o["INSIDE10"] = o["YDS_TO_GOAL"] <= 10
    return o


def by_down(o: pd.DataFrame) -> list[dict]:
    return [{"key": d, **lean(o[o["DOWN"] == d])} for d in DOWN_NAMES.values() if (o["DOWN"] == d).any()]


def by_dd(o: pd.DataFrame, order: list[str]) -> list[dict]:
    return [{"key": k, **lean(o[o["DD"] == k])} for k in order if (o["DD"] == k).any()]


def by_group(o: pd.DataFrame, col: str = "FGROUP") -> list[dict]:
    rows = [{"key": k, **lean(g)} for k, g in o.groupby(col)]
    return sorted(rows, key=lambda r: -r["n"])


def group_by_down(o: pd.DataFrame) -> tuple[list[str], list[tuple[str, int, list[dict | None]]]]:
    downs = [d for d in DOWN_NAMES.values() if (o["DOWN"] == d).any()]
    out = []
    for k, g in o.groupby("FGROUP"):
        cells = [lean(g[g["DOWN"] == d]) if (g["DOWN"] == d).any() else None for d in downs]
        out.append((k, len(g), cells))
    return downs, sorted(out, key=lambda r: -r[1])


def play_type_by_down(o: pd.DataFrame) -> tuple[list[str], list[tuple[str, pd.DataFrame, list[int]]]]:
    """Play family x down, from the snaps whose play call is tagged. Rows sorted by use."""
    t = o[o["PLAY_FAMILY"].notna()]
    downs = [d for d in DOWN_NAMES.values() if (t["DOWN"] == d).any()]
    rows = [(k, g, [int((g["DOWN"] == d).sum()) for d in downs]) for k, g in t.groupby("PLAY_FAMILY")]
    return downs, sorted(rows, key=lambda r: -len(r[1]))


def red_zone(o: pd.DataFrame) -> dict:
    rz = o[o["RZ"]]
    return {"all": lean(rz), "inside10": lean(o[o["INSIDE10"]]), "by_down": by_down(rz), "by_group": by_group(rz),
            "plays": rz["PLAY_FAMILY"].value_counts(), "snaps": rz}


def headline(o: pd.DataFrame, dd_order: list[str]) -> list[str]:
    """Plain-English 'if you see X, expect Y' lines for tendencies rated lean/strong."""
    lines = []
    for r in by_down(o) + by_dd(o, dd_order):
        if r["conf"] in ("lean", "strong"):
            lines.append(f"{r['key']}: {r['expect'].lower()} {100 * r['expect_pct']:.0f}% ({r['n']} snaps, {r['conf']})")
    for r in by_group(o):
        if r["conf"] in ("lean", "strong"):
            lines.append(f"{r['key']}: {r['expect'].lower()} {100 * r['expect_pct']:.0f}% ({r['n']} snaps, {r['conf']})")
    rz = red_zone(o)["all"]
    if rz["n"]:
        lines.append(f"Red zone: {100 * rz['run_pct']:.0f}% run ({rz['n']} snaps, {rz['conf']})")
    return lines


def to_csv(o: pd.DataFrame, dd_order: list[str], path: Path) -> None:
    rows = []
    for table, items in (("down", by_down(o)), ("down_distance", by_dd(o, dd_order)), ("formation_group", by_group(o)),
                         ("red_zone_down", red_zone(o)["by_down"]), ("red_zone_formation", red_zone(o)["by_group"])):
        for r in items:
            rows.append({"table": table, "situation": r["key"], "snaps": r["n"], "runs": r["runs"], "passes": r["passes"],
                         "run_pct": None if r["run_pct"] is None else round(100 * r["run_pct"]),
                         "expect": r["expect"], "confidence": r["conf"],
                         "avg_gain": None if r["avg"] is None or pd.isna(r["avg"]) else round(r["avg"], 1)})
    downs, grid = group_by_down(o)
    for k, n, cells in grid:
        for d, c in zip(downs, cells):
            if c:
                rows.append({"table": "formation_x_down", "situation": f"{k} | {d}", "snaps": c["n"], "runs": c["runs"],
                             "passes": c["passes"], "run_pct": round(100 * c["run_pct"]), "expect": c["expect"],
                             "confidence": c["conf"], "avg_gain": None})
    pd.DataFrame(rows).to_csv(path, index=False)


if __name__ == "__main__":
    from .loader import load_team
    from .report import DD_ORDER
    team_dir = Path(sys.argv[1])
    plays, games, warnings = load_team(team_dir)
    o = offense_snaps(plays)
    for line in headline(o, DD_ORDER):
        print(line)
    out = team_dir / "_scouting" / "tendencies.csv"
    out.parent.mkdir(exist_ok=True)
    to_csv(o, DD_ORDER, out)
    print("CSV:", out)
