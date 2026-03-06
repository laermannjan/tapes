# M6: Destination View

## Overview

`tab` toggles between metadata view (current) and destination view. Both views
show the same rows -- just a different lens on the data. No separate "process
mode"; the user flips back and forth freely.

## Destination view layout

| Column | Width | Content | Style |
|--------|-------|---------|-------|
| Status | 5ch | Operation: `copy`, `move`, `link`, `hdlk` | dim |
| Filepath | 52ch | Source path (unchanged) | same as metadata view |
| Dest path | ~72ch (combined metadata cols) | Computed destination | bright/error |

- Match sub-rows show the computed destination path for the proposed fields
  (preview before accepting).
- No-match sub-rows unchanged.
- Error rows: `(missing: year, episode_title)` in red where the destination
  path would be -- when the template references fields that are None.

## Config additions

```python
class LibraryConfig(BaseModel):
    movies: str = ""
    tv: str = ""
    movie_template: str = "{title} ({year})/{title} ({year}).{ext}"
    tv_template: str = "{title} ({year})/Season {season:02d}/{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
    operation: str = "copy"  # copy | move | link | hardlink
```

## Template rendering

Simple `str.format_map` with the row's metadata fields plus `ext` (from source
path extension). The destination path is relative to `library.movies` or
`library.tv` based on `media_type`.

Fields referenced in the template but missing/None from metadata are reported
as missing rather than raising an error.

## Footer keybindings (destination view)

When uncertain matches exist:
```
[A] accept all  [R] reject all  [enter] accept  [bksp] reject  [tab] metadata  [esc] quit
```

When missing-field rows exist (no uncertains):
```
[I] ignore missing  [F] fill unknown  [tab] metadata  [esc] quit
```

When all resolved:
```
[=] process 12 files  [tab] metadata  [esc] quit
```

After pressing `=` (confirmation):
```
copy 12 files to library? [=] confirm  [esc] cancel
```

## Ignore and fill-unknown

- `I` marks rows with missing mandatory fields as skipped. Operation column
  shows `skip`, destination shows `(skipped)`, row dimmed.
- `F` fills all None mandatory fields with the string `"unknown"`. The word
  "unknown" rendered in yellow within the destination path.
- Both undoable with `u`.

## Scope

- No actual file operations -- `=` confirm prints a dry-run summary and exits.
- No template config UI -- templates come from config file only.
- No custom template syntax -- plain Python `str.format_map`.
