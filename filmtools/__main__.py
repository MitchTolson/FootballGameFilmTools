"""Command line entry point.

    python -m filmtools report "F:\\CHSFootball\\Opponents\\Foster"

Writes to <team folder>\\_scouting\\:
    <Team> Scouting Report.html   - open in a browser; clip labels link to the videos
    <Team> plays.csv              - every tagged snap, normalized, for Excel
Optional staff-written files in <team folder>\\_scouting\\ (simple markdown: #/## headings,
'- ' bullets, **bold**; clip labels like FOS-12 become video links):
    notes.md      - shown under Key facts
    gameplan.md   - shown as the "Game plan recommendations" section
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .loader import load_team
from .report import build_report

CSV_COLS = ["GAME_NUM", "GAME", "GAME_DATE", "PLAY #", "QTR", "SIDE", "DN", "DIST", "DD", "YARD LN", "YDS_TO_GOAL",
            "FIELD_ZONE", "HASH", "KIND", "PLAY TYPE", "RESULT", "GAIN", "SUCCESS", "EXPLOSIVE", "OFF STR",
            "FORMATION", "FORM_FAMILY", "BACKFIELD", "PLAY", "PLAY_FAMILY", "PLAY DIR", "MOTION DIR",
            "DIR_VS_STRENGTH", "DIR_VS_FIELD", "DIR_VS_MOTION", "CLIP"]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def cmd_report(args) -> None:
    team_dir = Path(args.team_dir)
    team = args.team or team_dir.name
    plays, games, warnings = load_team(team_dir)
    for w in warnings:
        print("WARNING:", w)
    out_dir = Path(args.out) if args.out else team_dir / "_scouting"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(plays, games, team, out_dir / f"{team} Scouting Report.html",
                          read_text(out_dir / "notes.md"), read_text(out_dir / "gameplan.md"))
    plays[[c for c in CSV_COLS if c in plays]].to_csv(out_dir / f"{team} plays.csv", index=False)
    print(f"{len(games)} games, {len(plays)} snaps")
    print("Report:", report)
    print("CSV:   ", out_dir / f"{team} plays.csv")


def main() -> None:
    ap = argparse.ArgumentParser(prog="filmtools")
    subs = ap.add_subparsers(dest="cmd", required=True)
    r = subs.add_parser("report", help="build the scouting report for one opponent folder")
    r.add_argument("team_dir", help=r"e.g. F:\CHSFootball\Opponents\Foster")
    r.add_argument("--team", help="team name (default: folder name)")
    r.add_argument("--out", help="output folder (default: <team_dir>\\_scouting)")
    r.set_defaults(func=cmd_report)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
