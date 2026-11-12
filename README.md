# FootballGameFilmTools

Tools for Cedarcrest football film study and weekly opponent scouting.

## Setup

```
python -m pip install -r requirements.txt
```

ffmpeg is needed for the video tools (`winget install Gyan.FFmpeg`).

## Weekly scouting report

1. Download the opponent's games from Hudl into
   `F:\CHSFootball\Opponents\<Team>\<game folder>\`. Each game folder holds one clip per play
   (`Wide - Clip 001.mp4`, ...) and the Hudl breakdown `.xlsx`.
2. Build the report:

   ```
   python -m filmtools report "F:\CHSFootball\Opponents\<Team>"
   ```

3. Open `<Team>\_scouting\<Team> Scouting Report.html` in a browser. Clip labels such as `KEN-47`
   open that play's video. Every snap is also written to `<Team> plays.csv` for Excel.

Optional staff-written files in `<Team>\_scouting\` use simple markdown: `#` / `##` headings, `- ` bullets
(indent 2 spaces to nest) and `**bold**`. Clip labels like `FOS-12` become video links.

- `gameplan.md`: shown as the **Game plan recommendations** section. It has CHS offense, defense
  and special teams calls matched to the opponent's tendencies, using the terms in
  [docs/chs-scheme.md](docs/chs-scheme.md).
- `notes.md`: shown under Key facts.
- `film_tags.csv`: coverage/front read from film, since Hudl doesn't tag the defense. Columns:
  `game,play,front,shell,coverage,pressure,players,conf,note`. Adds a "Coverage & fronts" table.
- A roster file `roster*.txt` in the opponent folder (`# Name Pos. Gr. Ht. Wt.` lines, as copied from
  MaxPreps) adds a Roster section. Staff-confirmed roles go in `_scouting\positions.txt`, one per line
  (e.g. `9 = Will / Mike (rotates)`).

Re-run the report command after editing either file.

## Run / pass likelihood (defensive call sheet)

The report's offense section has a **Run / pass likelihood** block that every report includes.
It breaks run/pass down by down, by down & distance, by formation group, by formation × down, and in the red zone
(inside the 20 and inside the 10), plus a **play type × down** count for games whose breakdown tags play calls.
Each cell shows its count and a confidence label:
strong = 85%+ on 6+ snaps, lean = 75%+ on 4+, small = under 4 snaps.

```
python -m filmtools.tendencies "F:\CHSFootball\Opponents\<Team>"   # headline tendencies + _scouting\tendencies.csv
```

Formation groups are defined in [filmtools/tendencies.py](filmtools/tendencies.py) (`FORMATION_GROUPS`).

## Handing this off

Open the repo in Claude Code and run `/weekly-scouting-report`, or say "build this week's scouting report for
<Team>". The skill in `.claude/skills/weekly-scouting-report/` walks through the whole process:
tagging checks, report, game plan, playbook and player call-outs. Standards are in [agent.md](agent.md).

## Opponent offensive playbook (scout cards)

```
python -m filmtools.playbook "F:\CHSFootball\Opponents\<Team>"
```

The playbook is also embedded in the scouting report (section "Offensive playbook"). This command writes
the standalone `<Team>\Offensive Playbook\<Team> Offensive Playbook.html`. It starts with a **formation card** for each
set: the diagram, run/pass by down, and what they called from it. After that comes one card per play concept with
a formation diagram, each player's route or assignment, usage and success numbers, and clip links.
It also writes a `plays.csv`. Formation and route calls come from the Hudl tags, drawn on a standard alignment.
Inferred parts are flagged on each card. Put measured alignments in
`Offensive Playbook\formations.txt` (e.g. `TRIPS OPEN: X -20 0, H 8 -1, Y 13 -1, Z 20 0, QB 0 -5, RB -2 -5`).
Add `| note` at the end of a line when the alignment is drawn from the name rather than measured; the note shows on the card.

## Frame grabs for film review

```
python -m filmtools.frames grid  "<game folder>" "<out dir>" ABC 12 44   # 3x3 frames across each clip
python -m filmtools.frames sheet "<game folder>" "<out dir>" ABC 12 44   # pre/post-snap pairs
```

## How the data is read

- Breakdown row `PLAY #` N maps to `Clip N`. The tool warns if row and clip counts differ. Exports numbered
  k..N+k-1 for clips 1..N are shifted back (with a warning), and a `PLAY #` used twice is flagged.
- ODK should be from the scouted team's side: O = their offense, D = their defense, K = kicking game.
  A breakdown tagged by the *other* team (its TEAM column names the other school) is flipped
  automatically. If TEAM is empty the tool assumes the scouted side and warns you; check one clip.
  To confirm or correct a game, add a line to `<Team>\_scouting\tagging.txt` such as
  `Centralia = scouted | Sammamish in black` or `Foster = opponent`. The text before `=` matches
  part of the game folder name, and `opponent` means the breakdown's "O" rows are the other team.
  The report's "What each game's breakdown contains" table shows how each game was read.
- Who kicked is worked out from possession (including return TDs, defensive TDs and recovered
  onsides), because Hudl's kick tags don't reliably say.
- Ball-carrier, passer and target jersey numbers come from the RUSHER/PASSER/RECEIVER or
  OPP RUSHER/OPP PASSER/OPP RECEIVER columns, whichever is filled.
- YARD LN is relative to the team with the ball (−24 = its own 24).
- Play and formation names are grouped into families in [filmtools/playmap.py](filmtools/playmap.py).
  Edit the rules there when a new opponent's tagger uses different terms.

Scheme vocabulary for our own playbook is in [docs/chs-scheme.md](docs/chs-scheme.md).
