# tapes

A one-shot CLI tool for organising movie and TV show files. Point it at a
directory of downloads, it identifies files by filename and TMDB metadata,
lets you curate the results in an interactive TUI, then copies, moves, or
links them into a clean library structure. No database, no persistent state
between runs.

**Status: pre-alpha.** The full import pipeline and TUI work end to end.

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for package management
- A [TMDB read access token](https://www.themoviedb.org/settings/api) (free)

## Setup

```sh
git clone https://github.com/laermannjan/tapes
cd tapes
uv sync
```

Set your TMDB token via environment variable or config file:

```sh
export TMDB_TOKEN=your-read-access-token
```

Or create `~/.config/tapes/config.yaml` (see `config.example.yaml` for all
options):

```yaml
metadata:
  tmdb_token: "your-read-access-token"

library:
  movies: /media/movies
  tv: /media/tv
```

## Usage

Preview what would be imported without touching any files:

```sh
tapes import /path/to/downloads --dry-run
```

Import files (default operation: copy):

```sh
tapes import /path/to/downloads
```

Override operation for a single run:

```sh
tapes import /path/to/downloads --operation move
```

## How it works

When you run `tapes import`, each file goes through a pipeline of
identification, curation, and processing. Here is what happens at each step
and the vocabulary tapes uses.

### Scan and extract

Tapes walks the input directory and creates a **file node** for every file it
finds. Each node carries a **metadata** dict -- a set of key-value pairs
called **fields** (title, year, season, episode, and so on). The initial
metadata comes from parsing the filename with
[guessit](https://github.com/guessit-io/guessit), which becomes the first
**candidate**.

A candidate is a potential source of metadata. It has a name (like "guessit"
or "TMDB #1"), its own metadata dict, and a **score** measuring how well it
matches the file.

### Search and score

If a title was extracted, tapes searches TMDB and turns each result into a
candidate. Each candidate is scored by comparing its metadata against the
file's existing metadata -- title similarity (fuzzy string matching), year
proximity, and so on. The score is a float from 0 to 1.

### Auto-accept

Tapes checks whether the top candidate should be accepted automatically. The
gate has two conditions:

1. The best score must be at least `min_score` (default 0.6).
2. The best candidate must be **prominent** -- the gap between its score and
   the runner-up must be at least `min_prominence` (default 0.15).

A single candidate has infinite prominence and always passes. Two candidates
at 0.99 and 0.98 do *not* auto-accept because the margin is too small -- you
need to decide.

When a candidate is auto-accepted, its metadata is written into the file
node's metadata. For TV episodes this triggers a second query to find the
specific episode (season, episode number, episode title).

### Staging

After metadata is populated, tapes checks whether the file has all the fields
needed to fill its destination template (movie or TV). If so, the file is
**staged** -- marked ready to commit. Staged files show a green checkmark in
the tree.

Files that are missing fields (a question mark in the destination path) cannot
be staged until you fill in the gaps.

### Curate (the TUI)

The TUI opens as an interactive file tree. From here you can:

- **Browse** the tree with `j`/`k`, collapse folders with `h`/`l`.
- **Open the metadata view** with `enter` to inspect a file's candidates,
  compare their metadata side by side, and accept or edit fields.
- **Stage and unstage** files with `space`.
- **Commit** with `tab` to preview which files will be processed, then
  confirm.

Inside the metadata view, you see two columns: the file's current metadata on
the left and the selected candidate's metadata on the right. Green values are
additions, amber values are changes. Use `tab` to cycle through candidates,
`shift+tab` to toggle focus between the metadata and candidate columns, and
`enter` to accept. Accepting writes the focused candidate's fields into the
file's metadata and returns to the tree.

If the auto-accept got it wrong or you want to override a field, press `e` to
edit inline, `backspace` to clear, or `ctrl+r` to reset from the filename.

### Commit

When you are satisfied, press `tab` to open the commit view. It shows a
summary of staged files grouped by status (ready, conflict, incomplete) and
the file operation that will run (copy, move, link, or hardlink). Press
`enter` to execute.

Copies and moves use SHA-256 verification. Moves are implemented as
copy-verify-delete for safety.

## Configuration

See `config.example.yaml` for all options with descriptions. Configuration
is loaded from (highest priority first):

1. CLI flags (`--min-score`, `--operation`, etc.)
2. Environment variables (`TAPES_METADATA__TMDB_TOKEN`, etc.)
3. Config file (`~/.config/tapes/config.yaml` or `TAPES_CONFIG`)
4. Defaults

## License

MIT
