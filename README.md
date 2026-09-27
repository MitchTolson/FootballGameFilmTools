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

Re-run the report command after editing either file.

## How the data is read

- Breakdown row `PLAY #` N maps to `Clip N`. The tool warns if row and clip counts differ.
- ODK is from the scouted team's side: O = their offense, D = their defense, K = kicking game.
- YARD LN is relative to the team with the ball (−24 = its own 24).
- Play and formation names are grouped into families in [filmtools/playmap.py](filmtools/playmap.py).
  Edit the rules there when a new opponent's tagger uses different terms.

Scheme vocabulary for our own playbook is in [docs/chs-scheme.md](docs/chs-scheme.md).
