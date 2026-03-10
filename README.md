# tapes

Organize your media files.

Tapes renames and organizes media files into a clean directory structure. It gathers metadata for your files and lets you define a naming scheme based on it. Use it to clean up a messy collection or restructure an existing library.

It automates what it can and asks when it's not sure. Everything can be overruled, and nothing happens to your files without confirmation. Run it interactively to review and curate, or unattended to let it handle things on its own.

Works as a terminal app, a web server, or inside Docker. Configure with CLI flags, a YAML config, or environment variables.

```
messy-collection/                         Movies/
  ratatouille.mp4                           Ratatouille (2007)/
  breaking bad s01e01.mkv           ->        Ratatouille (2007).mp4
  ratatouille.en.srt                          Ratatouille (2007).en.srt
                                            TV/
                                              Breaking Bad (2008)/
                                                Season 01/
                                                  Breaking Bad - S01E01 - Pilot.mkv
```

<!-- TODO: replace with asciinema recording of a real session -->

---

## Getting started

You'll need a [TMDB read access token](https://www.themoviedb.org/settings/api) (free).

```sh
git clone https://github.com/laermannjan/tapes
cd tapes
uv sync
```

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

Set up your library:

```sh
export TMDB_TOKEN=your-token

mkdir -p ~/.config/tapes
cat > ~/.config/tapes/config.yaml << 'EOF'
library:
  movies: /media/movies
  tv: /media/tv
EOF
```

```sh
tapes import ~/media/unsorted
```

That's it. Tapes scans the folder, identifies your files, and opens the TUI. Review what it found, stage the files you're happy with, and commit.

For a one-off job with specific settings, use CLI flags directly:

```sh
tapes import ~/media/unsorted \
  --library-movies /media/movies \
  --library-tv /media/tv \
  --movie-template "{title} ({year})/{title} ({year}).{ext}" \
  --tv-template "{title} ({year})/Season {season:02d}/{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}" \
  --language de \
  --operation move \
  --min-score 0.5 \
  --dry-run
```

Templates are Python format strings - `{field}` placeholders are filled from each file's metadata, and format specs like `{season:02d}` work as expected. Available fields include `title`, `year`, `season`, `episode`, `episode_title`, `tmdb_id`, `codec`, `resolution`, and more.

All settings work as CLI flags, environment variables (`TAPES_` prefix), or in the config file. See [`config.example.yaml`](config.example.yaml) for everything, or run `tapes import --help`.

## How it works

Tapes extracts metadata from your files - title, year, season, episode, and so on - and uses it to fill a naming template you define. A template like `{title} ({year})/{title} ({year}).{ext}` turns `ratatouille.mp4` into `Ratatouille (2007)/Ratatouille (2007).mp4`.

Browse your files in the tree view. Files with enough metadata to fill their template can be **staged** for processing with `space` - individually, by directory, or across a `v` selection. When you're ready, press `tab` to open the commit view, choose your operation (copy, move, symlink, or hardlink), and confirm.

### Enriching metadata

But what if your files are badly named, or the template needs fields the filename doesn't have - like an episode title? This is where external providers come in.

Tapes queries online media databases and returns **candidates** - potential matches for your file. Open the **metadata view** for any file with `enter` to see them. Each candidate carries its own metadata and a **score** measuring how well it matches what tapes already knows about the file. Use `tab` to flip through candidates and `enter` to accept one - its metadata overwrites the file's current values.

In practice, you rarely need to do this by hand. Tapes queries all files automatically from the start and **auto-accepts** candidates it's confident about. Confidence is based on the best candidate's score and its **prominence** - how far ahead it is of the runner-up. If the best match scores 0.92 and the next best 0.4, that's prominent enough to accept. Two candidates at 0.99 and 0.98? Tapes asks you. Auto-accepted files with complete metadata are also **auto-staged**, so in many cases there's nothing to do at all.

### Manual control

Every metadata field can be edited manually with `e`. This is useful when you know something tapes doesn't - for example, setting a provider ID directly locks in the right match and triggers a fresh lookup.

You can also edit metadata in bulk. Select multiple files with `v`, press `enter` to open the metadata view for all of them, and accept a candidate or manually set a field value that applies to the whole selection. This is especially useful for TV shows: select a folder of episodes, accept the show-level match, and tapes triggers individual episode lookups for every file in the selection.

### The typical workflow

Once you get the hang of it, most of the work is just confirming what tapes already figured out. Scan through the tree, check that things look right, stage, commit. For the files tapes couldn't resolve on its own, open the metadata view, pick the right candidate, done. A common session is mostly just `enter`, `enter`, `space`, `tab`, `enter` - saying "yes, that's right" until you're done.

## Status

Pre-alpha. The import pipeline and TUI work end to end. See [docs/](docs/) for architecture and design documents.

## License

MIT
