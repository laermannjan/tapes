# Interactive UI Redesign -- Design Draft

**Date:** 2026-03-05
**Status:** Brainstorming
**Supersedes:** Issue 007 (adopt prompt_toolkit) -- extends scope significantly

---

## Core Vision

Replace the current file-by-file sequential prompt with a **vertical accordion
review UI** built on textual. All import groups are visible at once in a
scrollable list. The focused group expands to show full details (candidates,
companions, actions). Other groups show a one-line summary with status. Import
executes only when the user explicitly submits from the summary section.

Inspired by:
- **Claude Code** multi-question flow: independent navigation, summary at end
- **ccstatusline** editing patterns: in-place cycling, fuzzy search, mode
  stacking, color hierarchy, custom keybinds per item type

**Library choice: textual.** By the Rich author (already a dependency), provides
Collapsible, OptionList, SelectionList, Input, DataTable, ModalScreen, and
built-in fuzzy matching. Rich renderables work natively inside textual widgets.

---

## 1. Grouping Model

### 1.1 Group Types

After discovery + identification, files are organized into groups. A group is
the unit of user review.

| Type | Contents | When created |
|------|----------|--------------|
| **Movie** | 1 video + companions (subs, artwork, NFO) | Single video in a directory, or identified as movie by guessit |
| **Multi-part movie** | N videos (parts) + companions | Multiple videos identified as same movie split across files (e.g., "Movie.CD1.mkv", "Movie.CD2.mkv") |
| **Season** | N episodes + their companions | Multiple videos in same dir sharing a show name + season number |
| **Show** | Container for season groups | 2+ season groups with matching show name / TMDB ID |

Show groups are display-only containers in the summary; they do not get their
own accordion section. Each season within a show is its own section.

**Multi-part movies** are a single movie split across multiple video files
(CD1/CD2, Part1/Part2, Disc1/Disc2). All parts share the same TMDB movie ID.
They are grouped together because they are one logical unit. When the user
accepts a candidate, all parts are matched to that same movie. The expanded
view shows each file with the shared match on the same row.

**TV episode matching**: when the user accepts a show-level candidate for a
season group, each episode is looked up against that specific show and season
on TMDB (get episode details by show ID + season + episode number). The lookup
is constrained to the selected show -- it does not search broadly. Each episode
gets its own confidence score. The season-level confidence displayed in the
collapsed view is the average of all episode confidences. If an episode cannot
be found on TMDB or has very low confidence, it is highlighted as unmatched
(red/warning). The expanded view shows each video file with its episode match
on the same row, and companion files grouped visually with their video
(separated by empty lines between video+companion units).

**Episode correction**: the user can see per-episode match quality in the
expanded season view. To fix a mismatched or misclassified episode, the user
splits it out (via `p`) into its own group, then reviews that group
independently. This reuses the split mechanism and avoids nesting a
per-episode review flow inside the season view.

### 1.2 Group Identity

Each group has:
- **id**: stable, used for widget IDs and internal references
- **label**: human-readable, shown in accordion header. Auto-generated:
  - Movie: `"Dune (2021)"` or `"Unknown: movie.mkv"` if unidentified
  - Season: `"Breaking Bad S01"` or `"Unknown: TV.S01/"`
  - Show (summary only): `"Breaking Bad -- 5 seasons"`
- **status**: `pending | accepted | skipped | auto-accepted`
- **match**: the selected SearchResult (or None)
- **files**: list of (path, included: bool) tuples
- **companions**: list of (CompanionFile, included: bool) tuples

Labels regenerate after split/merge/match-change.

### 1.3 Building Groups from Discovery

Current flow: `scan_media_files` -> `group_media_files` (by parent dir) ->
per-file identification. The new flow separates local metadata extraction
from remote identification and adds smart grouping between them.

#### Pipeline

```
1. Scan         find video files under import root
2. Extract      extract metadata from local sources (no network)
3. Group        cluster videos into groups using extracted metadata + locality
4. Companions   find companion files for each group (no network)
5. Identify     TMDB lookup per group (network)
6. Present      launch ReviewApp with groups
```

#### Step 1: Scan

`scan_media_files(root)` -- unchanged. Finds all files with video extensions,
excludes sample patterns.

#### Step 2: Extract local metadata

For each video file, extract metadata from multiple local sources. These
sources may conflict, so they are resolved by a configurable priority order.

| Source | What it provides | Notes |
|--------|-----------------|-------|
| **Filename** | title, year, season, episode, part/cd, codec, source | via guessit (`parse_filename`) |
| **Parent directory name** | title, year, season | parsed same way as filename |
| **Sidecar files** (.nfo, .xml) | title, year, TMDB/IMDB ID | existing NFO scanner |
| **Embedded tags** (MKV, MP4) | title, year, description | via MediaInfo or ffprobe |

**Priority resolution**: when sources disagree, a configurable priority list
determines which value wins. Default priority (highest first):

```toml
[import]
metadata_priority = ["sidecar", "embedded", "filename", "directory"]
```

For example, if the filename says "Dune 2021" but an NFO sidecar contains
`tmdb:438631`, the sidecar wins. If no sidecar exists, filename is used.

The output of this step is a `LocalMetadata` per video file containing the
resolved title, year, media type (movie/tv), season, episode, part number,
and any external IDs found.

#### Step 3: Group

New `build_import_groups(videos, metadata)` function. Grouping uses only
local metadata and directory locality -- no network calls.

**Locality constraint**: a video can only be grouped with other videos in
the **same directory or a child directory** of its containing directory.
Never with files in a parent or sibling directory. This prevents unrelated
files in distant parts of the tree from being merged.

**Grouping rules** (applied in order):

1. Videos in the same directory (or parent-child) with the same show name
   + same season number + different episode numbers -> **Season group**
2. Season groups sharing a show name -> nested under a **Show** (display-only)
3. Videos in the same directory (or parent-child) with the same title +
   different CD/part/disc numbers (guessit `part` field) -> **Multi-part
   movie group** (one movie, multiple files)
4. Movie sequels (e.g., Kill Bill Vol. 1 and Vol. 2) are separate movie
   groups -- they have different titles after guessit parsing
5. Everything else -> **Movie group** (one per video)

#### Step 4: Companion detection

For each group, find companion files automatically:

- A companion must have an **allowed extension** (subtitle, artwork, NFO,
  etc. -- already defined in `CompanionFile` classification)
- A companion is auto-associated with a video if it **shares the video's
  name stem** (e.g., `Movie.en.srt` is a companion of `Movie.mkv`)
- Companions can be in the **same directory or child directories** of the
  video, with a **maximum depth of 3** (configurable, sane default)
- Companions not matching any video's stem remain unassigned -- they show
  up in the file editor but are not auto-included in any group

The user can always override companion assignment in the interactive flow
via the file editor modal (`e` key).

#### Step 5: Identify (TMDB lookup)

Run identification pipeline per group (network calls):
- **Movie group**: one TMDB search using resolved title + year
- **Multi-part movie group**: one TMDB search (all parts share one ID)
- **Season group**: one TMDB search for the show, then per-episode lookups
  constrained to the matched show ID + season number
- If a sidecar/embedded source already provided a TMDB/IMDB ID, use
  `get_by_id` directly instead of searching

#### Step 6: Present

Launch ReviewApp with groups.

### 1.4 Group Manipulation

Users can restructure groups during review:

**Edit files** (`e` key):
- Opens a file browser modal showing ALL files under the import root
- Each file shows its path relative to the import root
- Files in the current group are highlighted prominently (bold/cyan)
- Files in another group show that group's label dimmed next to them
- Files not in any group are shown plain
- The list is fuzzy-searchable (type to filter by filename/path)
- **Tab** toggles a file into/out of the current group
- Adding a file that belongs to another group removes it from that group
  (each file can only be in one group or none)
- Useful for: reassigning a misclassified companion to the right video,
  adding a forgotten file, removing a file that does not belong

**Copy match** (`c` key):
- Copies the current group's match to a selected file within the group
- Use case: a companion file (e.g., subtitle) was correctly grouped but the
  user wants to explicitly confirm which video it belongs to
- Opens a picker showing files in the current group; selecting one associates
  the current match with that file

**Split group** (`p` key):
- Opens a SelectionList modal showing all files in the group
- User marks files to break out with **Tab**
- Creates a new group from marked files, removes them from current
- Both groups get new labels based on remaining contents
- New accordion section appears below current

**Merge groups** (`j` key):
- Opens a fuzzy-find picker (Input + filtered OptionList) of all other groups
- User marks groups for merge with **Tab**
- Files combined, companions combined
- Merged sections removed
- Current group label regenerates

**Toggling convention**: throughout all modals and selection lists, **Tab**
marks/unmarks items. This is consistent everywhere and avoids conflict with
fuzzy-search typing (which uses normal character keys including space).

---

## 2. Screen Layout -- Vertical Accordion

The key insight: instead of a horizontal tab bar, use a **vertical accordion**.
The focused group is expanded; all others show a collapsed one-line summary.
This lets the user see the status of every group at a glance while working on
one.

```
+------------------------------------------------------------------+
| tapes import /downloads                                  ctrl+q  |
+------------------------------------------------------------------+
|                                                                    |
|  [ok]  Dune (2021)  ->  Dune: Part One  tmdb:438631  94%         | <- collapsed, accepted
|  [ok]  Arrival (2016)  ->  Arrival  tmdb:329865  91%             | <- collapsed, accepted
|                                                                    |
|  [??]  Breaking Bad S01  ->  (pending)                    [FOCUS] | <- expanded header
|  +--------------------------------------------------------------+ |
|  |  Candidates                                                   | |
|  |  > Breaking Bad (2008)  tmdb:1396  87%               green    | |
|  |    Break (2009)          tmdb:4821  31%               red     | |
|  |                                                                | |
|  |  Files                                                         | |
|  |  video     S01E01.Breaking.Bad.mkv    S01E01 Pilot  92% green | |
|  |  subtitle  S01E01.en.srt                                      | |
|  |                                                                | |
|  |  video     S01E02.Breaking.Bad.mkv    S01E02 Cat's  91% green | |
|  |  subtitle  S01E02.en.srt                                      | |
|  |                                                                | |
|  |  Dest: TV/Breaking Bad (2008)/Season 01/                      | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  [??]  Unknown: rip/  ->  (pending)                               | <- collapsed, pending
|  [--]  bonus.mkv  ->  (skipped)                                   | <- collapsed, skipped
|                                                                    |
|  === Summary ===                                                   |
|  Accepted: 2 (+ 0 auto)    Pending: 2    Skipped: 1              |
|  [Proceed]  [Proceed + auto-accept]  [Cancel]                    |
|                                                                    |
+------------------------------------------------------------------+
| ^up/^down groups  up/down items  enter accept  s search          |
| m manual  x skip  e files  p split  j merge  c copy  q quit     |
+------------------------------------------------------------------+
```

In the default expanded view, files are listed plainly without checkbox
markers. They are shown because they are included. To add, remove, or
reassign files, the user presses **e** to open the file editor modal.

### 2.1 Accordion Behavior

- **Ctrl+Up / Ctrl+Down**: move focus to previous/next group. The newly
  focused group expands; the previously focused group collapses to its
  one-line summary.
- **Up / Down**: navigate within the expanded group (candidates, files).
- Only one group is expanded at a time.
- The summary section at the bottom is always visible (not collapsible).

### 2.2 Collapsed Group Format

Each collapsed group is a single line showing:

```
[status]  label  ->  match_title  tmdb:ID  confidence%
```

Status indicators:
- `[ok]` green: accepted (user confirmed)
- `[**]` blue: auto-accepted (above threshold, no user action)
- `[??]` yellow: pending (needs review)
- `[--]` dim: skipped
- `[..]` dim pulse: loading (identification in progress)

### 2.3 Expanded Group Sections

When a group is focused/expanded, it shows:

1. **Candidate section**: OptionList of TMDB candidates, colored by confidence
2. **File list**: each video file shown with its match on the same row. For TV
   seasons, each episode shows the TMDB episode match inline. Companion files
   are listed directly below their associated video, forming visually separated
   units (empty line between each video+companions block). For movies, all
   files match the single selected candidate. Press `e` to open the full file
   editor modal.
3. **Destination preview**: Static showing where files will be placed
4. **Search/manual form**: Hidden by default, shown on `s` or `m`

**Movie group** expanded:
```
  Candidates
  > Dune: Part One (2021)      tmdb:438631  94%           green
    Dune (1984)                 tmdb:841     62%           yellow

  Files
  video     Dune.2021.2160p.BluRay.x265.DTS-HD.mkv       -> Dune: Part One
  subtitle  Dune.2021.en.srt
  subtitle  Dune.2021.de.srt
  artwork   poster.jpg

  Dest: Movies/Dune Part One (2021)/Dune Part One (2021).mkv
```

All files in a movie group inherit the selected candidate. The video row shows
the match name; companion rows are indented/grouped below without repeating it.

**TV season group** expanded (after show-level match accepted, per-episode
lookups done):
```
  Candidates
  > Breaking Bad (2008)        tmdb:1396                  green

  Files                                            avg confidence: 89%

  video     S01E01.Pilot.720p.mkv                 S01E01 Pilot  92%  green
  subtitle  S01E01.en.srt

  video     S01E02.Cats.in.the.Bag.720p.mkv       S01E02 Cat's in the Bag  91%  green
  subtitle  S01E02.en.srt

  video     S01E03.And.the.Bags.720p.mkv          S01E03 ...and the Bag's  84%  green

  artwork   poster.jpg                             (season-level)

  Dest: TV/Breaking Bad (2008)/Season 01/
```

Each video file is paired with its episode match on the same row. Companions
for that episode appear directly below, forming a visual unit. Empty lines
separate each episode block. Companions not tied to a specific episode (like
`poster.jpg`) appear at the end as season-level. If an episode has no TMDB
match or very low confidence, the match column shows `(no match)` in red.

**Multi-part movie group** expanded:
```
  Candidates
  > The Lord of the Rings: The Fellowship (2001)  tmdb:120  93%  green

  Files

  video     LOTR.Fellowship.CD1.mkv                -> The Fellowship  93%
  video     LOTR.Fellowship.CD2.mkv                -> The Fellowship  93%
  subtitle  LOTR.Fellowship.en.srt
  artwork   poster.jpg

  Dest: Movies/The Lord of the Rings The Fellowship (2001)/
```

All parts share the same TMDB match. Each video row shows the match; companions
are grouped below.

### 2.4 Textual Widget Mapping

| UI Region | Textual Widget | Notes |
|-----------|---------------|-------|
| Accordion container | `VerticalScroll` + custom `GroupWidget` | Custom collapsible behavior |
| Collapsed group | `Static` (one line) | Styled by status |
| Expanded candidate list | `OptionList` | Rich Text items, color by confidence |
| Expanded file list | `Static` list | File + match on same row, grouped by video+companions |
| Destination preview | `Static` | Updates reactively when match changes |
| Inline search form | `Vertical(Select, Input, Input, Button)` | Hidden by default |
| Summary section | `Static` + `Horizontal(Button, Button, Button)` | Always visible at bottom |
| File editor modal | `ModalScreen` + `Input` + list | Fuzzy search, Tab to toggle |
| Split modal | `ModalScreen` + list | Tab to mark, enter to split |
| Merge picker | `ModalScreen` + `Input` + list | Fuzzy search, Tab to mark |
| Footer | `Footer` | Auto-populated from BINDINGS |

### 2.5 Color Scheme

| Meaning | Color | Where |
|---------|-------|-------|
| High confidence (>= 0.75) | green | Match candidate text |
| Medium confidence (0.5-0.75) | yellow | Match candidate text |
| Low confidence (< 0.5) | red | Match candidate text |
| Selected/highlighted item | cyan reverse | OptionList/SelectionList cursor |
| Accepted group (user) | green | Collapsed line, status badge |
| Auto-accepted group | blue | Collapsed line, status badge |
| Pending group | yellow | Collapsed line, status badge |
| Skipped group | dim | Collapsed line, status badge |
| Destination preview | dim | Static text |

---

## 3. Interaction Flows

### 3.1 Group Navigation

| Key | Action |
|-----|--------|
| Ctrl+Down | Focus next group (expand it, collapse current) |
| Ctrl+Up | Focus previous group (expand it, collapse current) |

When a group is accepted or skipped, focus auto-advances to the next pending
group. If no pending groups remain, focus moves to the summary section.

### 3.2 Within-Group Review

| Key | Action | Context |
|-----|--------|---------|
| up/down | Navigate candidates | Candidate list focused |
| enter | Accept highlighted candidate | Candidate list focused |
| s | Show/focus inline search form | Any focus in group |
| m | Show/focus inline manual form | Any focus in group |
| x | Skip this group | Any focus in group |
| e | Open file editor modal | Any focus in group |
| c | Copy match to file | Any focus in group |
| p | Open split modal | Any focus in group |
| j | Open merge modal | Any focus in group |
| escape | Cancel form / return to candidates | Form focused |

When the user presses **enter** on a candidate:
1. Group status -> `accepted`
2. Group match -> selected candidate
3. All files in the group are matched to this candidate:
   - **Movie groups**: all files immediately inherit the selected movie match
   - **Multi-part movie groups**: all parts share the same TMDB movie ID
   - **TV season groups**: per-episode lookups fire (background), constrained
     to the selected show ID + season number. Each episode gets its own
     confidence. Episodes with no TMDB match or very low confidence are
     highlighted in red as unmatched.
4. Destination preview updates
5. Group collapses to one-line with green `[ok]` badge
6. Focus auto-advances to next pending group

When the user presses **x**:
1. Group status -> `skipped`
2. Group collapses to one-line with dim `[--]` badge
3. Focus auto-advances to next pending group

### 3.3 File Editor Modal (`e` key)

Pressing **e** opens a modal showing ALL files under the import root --
not just the current group's files. This is the central tool for
adding, removing, and reassigning files between groups.

```
  +-- Edit Files: Breaking Bad S01 -----------------------------------+
  |                                                                    |
  |  Search: [srt                                                    ] |
  |                                                                    |
  |  S01E01.en.srt                                      Breaking Bad S01  <- in current group (bold cyan)
  |  S01E02.en.srt                                      Breaking Bad S01  <- in current group (bold cyan)
  |  Arrival.2016.en.srt                                Arrival (2016)    <- in another group (dim)
  |  Dune.2021.en.srt                                   Dune (2021)       <- in another group (dim)
  |  Dune.2021.de.srt                                   Dune (2021)       <- in another group (dim)
  |  S02E01.en.srt                                      Breaking Bad S02  <- in another group (dim)
  |  S02E02.en.srt                                      Breaking Bad S02  <- in another group (dim)
  |                                                                    |
  |  7 files matching "srt"  (tab toggle, enter confirm, esc cancel)   |
  +--------------------------------------------------------------------+
```

- Files are shown with paths relative to import root
- Fuzzy search: type to filter (accumulates in search input)
- **Tab**: toggle file into/out of current group
  - If file is in current group (cyan): removes it (goes plain)
  - If file is in another group (dim label): moves it to current group
    (becomes cyan), removed from old group
  - If file is unassigned (plain): adds it to current group (becomes cyan)
- **Enter**: confirm and close modal
- **Escape**: cancel changes, close modal
- Files in the current group are **bold cyan** for prominent visibility
- Files in other groups show that group's label **dimmed** next to them
- Unassigned files (not in any group) show no label

### 3.4 Inline Search

Pressing **s** reveals the search form (hidden Vertical container) and focuses
the title Input.

```
  Search TMDB
  Type:  [movie v]     <- Select widget
  Title: [Dune       ] <- Input, pre-filled from filename
  Year:  [2021       ] <- Input, pre-filled from filename
  [Search]  [Cancel]
```

- Tab moves between fields within the form
- Enter on Search button or submitting last field triggers TMDB lookup
- Results replace the OptionList candidates
- Escape or Cancel hides the form, restores previous candidates
- If search returns nothing, OptionList shows "No results found"

### 3.5 Inline Manual Entry

Pressing **m** reveals a similar form:

```
  Manual Metadata
  Type:     [movie v]
  Title:    [         ]
  Year:     [         ]
  Show:     [         ]    <- visible only if type=tv
  Season:   [         ]    <- visible only if type=tv
  Episode:  [         ]    <- visible only if type=tv
  [Apply]  [Cancel]
```

- Apply creates a synthetic SearchResult (tmdb_id=0, confidence=1.0)
- Group auto-accepts with this result
- Group collapses, focus advances

### 3.6 Copy Match (`c` key)

Pressing **c** opens a picker showing files in the current group. The user
selects a target file, and the current group's match is associated with it.

Use case: a subtitle file was grouped correctly but needs to be explicitly
linked to a specific video (e.g., in a multi-part movie where each subtitle
could belong to either part).

```
  +-- Copy match to file -------------------------+
  |                                                |
  |  Match: Breaking Bad (2008) tmdb:1396          |
  |                                                |
  |  > S01E01.Pilot.720p.mkv                       |
  |    S01E02.Cats.in.the.Bag.720p.mkv             |
  |    S01E01.en.srt                                |
  |    S01E02.en.srt                                |
  |    poster.jpg                                   |
  |                                                |
  |  (up/down select, enter confirm, esc cancel)   |
  +------------------------------------------------+
```

### 3.7 Split Group (Modal)

Pressing **p** pushes a ModalScreen:

```
  +-- Split: Breaking Bad S01 --------------------------------+
  |                                                            |
  |  Mark files to move to a new group:                        |
  |                                                            |
  |    S01E01.Pilot.720p.mkv                                   |
  |    S01E02.Cats.in.the.Bag.720p.mkv                         |
  |  * S01E03.And.the.Bags.in.the.River.720p.mkv        marked |
  |    S01E01.en.srt                                            |
  |    S01E02.en.srt                                            |
  |    poster.jpg                                               |
  |                                                            |
  |  1 file marked  (tab mark, enter split, esc cancel)        |
  +------------------------------------------------------------+
```

- **Tab** marks/unmarks files for splitting
- Companion files associated with marked videos are auto-marked
- **Enter** creates new group from marked files, removes them from current
- Both groups get regenerated labels
- Modal dismisses, focus stays on current (now smaller) group

### 3.8 Merge Groups (Modal)

Pressing **j** pushes a ModalScreen with fuzzy search:

```
  +-- Merge into: Breaking Bad S01 ---------------------------+
  |                                                            |
  |  Search: [break                                          ] |
  |                                                            |
  |  * Breaking Bad S02 -- 2 episodes                   marked |
  |    Arrival (2016) -- 1 video                                |
  |    Dune (2021) -- 1 video                                   |
  |                                                            |
  |  1 group marked  (tab mark, enter merge, esc cancel)       |
  +------------------------------------------------------------+
```

- Type to fuzzy-filter groups by name
- **Tab** marks/unmarks groups for merge
- **Enter** merges marked groups into current group
- Merged sections removed from accordion
- Current group label regenerates

### 3.8 Summary Section

Always visible at the bottom of the accordion (scrolls into view). Not
collapsible. Shows:

```
  === Summary ===
  Accepted: 2    Auto-accepted: 3    Pending: 1    Skipped: 1

  [Proceed]  [Proceed + include auto-accepted]  [Cancel]
```

- **Proceed**: imports only groups with status `accepted` (user-confirmed)
- **Proceed + include auto-accepted**: also imports `auto-accepted` groups
- **Cancel**: aborts, returns empty ImportPlan
- Counts update in real-time as the user accepts/skips groups

The auto-accept toggle exists because the user may want to review auto-accepted
matches before committing, or may trust the pipeline and include them.

---

## 4. Data Flow

```
CLI (tapes import /path --interactive)
  |
  v
1. scan_media_files(/path)       -- existing, find video files
  |
  v
2. extract_local_metadata()      -- NEW: filename + parent dir + NFO + tags
  |                                 priority-resolved, no network
  v
3. build_import_groups()         -- NEW: smart grouping by metadata + locality
  |
  v
4. find_companions()             -- NEW: name-stem matching, same/child dirs
  |                                 max depth 3, allowed extensions only
  v
5. identify per group            -- existing pipeline + batched TV lookups
  |                                 uses sidecar IDs directly if available
  v
6. auto-accept groups >= threshold
  |
  v
7. launch ReviewApp(groups)      -- NEW: textual app
  |
  v
user reviews (accept/skip/search/split/merge)
  |
  v
user submits from summary
  |
  v
ReviewApp returns ImportPlan     -- list of (group, match, files)
  |
  v
ImportService.execute(plan)      -- refactored: takes plan, not path
  |
  v
file ops + DB writes             -- existing
```

### 4.1 Key Dataclasses

```python
from enum import Enum

class GroupStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    AUTO_ACCEPTED = "auto_accepted"
    SKIPPED = "skipped"

@dataclass
class LocalMetadata:
    """Resolved metadata from local sources (no network)."""
    title: str | None
    year: int | None
    media_type: str | None               # "movie" or "tv"
    season: int | None
    episode: int | None
    part: int | None                     # CD1/CD2/Part1/Part2
    external_ids: dict[str, str]         # {"tmdb": "438631", "imdb": "tt1234"}
    sources: dict[str, dict]             # raw per-source data for debugging

@dataclass
class ImportGroup:
    id: str
    label: str
    status: GroupStatus
    media_type: str                      # "movie" or "tv"
    match: SearchResult | None
    candidates: list[SearchResult]
    files: list[tuple[Path, bool]]       # (path, included)
    companions: list[tuple[CompanionFile, bool]]
    local_metadata: LocalMetadata        # resolved from extraction step

@dataclass
class ImportPlanItem:
    video: Path
    match: SearchResult
    companions: list[CompanionFile]      # only included ones

@dataclass
class ImportPlan:
    items: list[ImportPlanItem]
    dry_run: bool = False
```

The ReviewApp receives `list[ImportGroup]` and returns `ImportPlan`.
ImportService.execute() takes an ImportPlan.

---

## 5. Non-Interactive and Edge Cases

### --interactive flag
The textual UI only launches when `--interactive` is passed. Without it,
the current auto-accept flow is preserved unchanged.

### --dry-run + --interactive
Same accordion UI, but summary buttons say "Preview plan" instead of
"Proceed". Submitting prints the plan (source -> dest mappings) and exits.

### Non-TTY stdin
If stdin is not a TTY, `--interactive` is ignored. Fall back to auto-accept.
Log a warning: "Interactive mode requires a terminal."

### Very large imports (100+ groups)
- Groups reduce the count (a season of 24 episodes = 1 group)
- Accordion is a VerticalScroll -- only visible groups render
- Could add a jump-to search (Ctrl+F) to find groups by name

### Progressive identification
- Groups appear in accordion immediately after discovery
- Collapsed lines show `[..]` (loading) while TMDB runs
- Identification runs in textual workers (background threads)
- As each group resolves, its collapsed line updates
- User can expand and review already-resolved groups while others load

---

## 6. Scope and Phasing

### Phase 1: Core accordion with existing grouping
- textual ReviewApp with accordion layout
- One section per MediaGroup (current directory-based grouping)
- Unified file+match rows in expanded view
- Accept/skip/search/manual within expanded group
- Summary section with proceed/cancel
- ImportPlan output, refactored ImportService.execute()
- Post-import log with pipe-delimited format
- No split/merge, no smart grouping

### Phase 2: Local metadata extraction + smart grouping
- `LocalMetadata` dataclass and multi-source extraction
  (filename, parent dir, sidecar NFO/XML, embedded tags)
- Configurable `metadata_priority` in config
- `build_import_groups()` with season/show/multi-part detection
- Locality constraint (same dir or child dirs only)
- `find_companions()` with name-stem matching, max depth 3
- Batched TMDB lookup for TV seasons
- Group labels with content summaries

### Phase 3: Group manipulation
- Split modal
- Merge modal with fuzzy search
- File editor modal (all files under import root)
- Copy-match action
- Label regeneration after manipulation

### Phase 4: Polish
- Progressive loading with textual workers
- Color theming / .tcss stylesheet
- Keyboard shortcut help overlay (? key)
- Ctrl+F jump-to-group search

---

## 7. New Dependencies

```toml
[project]
dependencies = [
    # ... existing ...
    "textual >= 3.0",
]

[dependency-groups]
dev = [
    # ... existing ...
    "textual-dev >= 1.0",  # textual devtools (console, snapshot testing)
]
```

textual pulls in Rich (already a dependency) and typing-extensions.

---

## 8. Files Affected

### New files
- `tapes/ui/__init__.py`
- `tapes/ui/app.py` -- ReviewApp (main textual app)
- `tapes/ui/group_widget.py` -- GroupWidget (collapsible accordion section)
- `tapes/ui/summary_widget.py` -- SummaryWidget (always-visible bottom)
- `tapes/ui/search_form.py` -- inline search form
- `tapes/ui/manual_form.py` -- inline manual entry form
- `tapes/ui/split_modal.py` -- split group modal screen
- `tapes/ui/merge_modal.py` -- merge groups modal screen
- `tapes/ui/file_editor_modal.py` -- file editor modal screen
- `tapes/ui/styles.tcss` -- textual CSS styles
- `tapes/ui/plan.py` -- ImportGroup, ImportPlan, GroupStatus, LocalMetadata
- `tapes/discovery/metadata.py` -- LocalMetadata extraction + priority resolution
- `tapes/discovery/companions.py` -- name-stem companion detection (depth-limited)

### Modified files
- `tapes/importer/service.py` -- add execute(plan) method, pipe-delimited log
- `tapes/cli/commands/import_.py` -- launch ReviewApp when --interactive
- `tapes/discovery/grouper.py` -- extended with smart grouping (Phase 2)
- `tapes/config/schema.py` -- add `metadata_priority` and `companion_depth` config

### Preserved (business logic, no UI)
- `tapes/importer/interactive.py` -- InteractivePrompt, default_action,
  PromptAction (used by GroupWidget to determine initial state)
- `tapes/identification/pipeline.py` -- unchanged
- `tapes/companions/classifier.py` -- unchanged
- `tapes/metadata/tmdb.py` -- unchanged

### Eventually removed
- `_read_key()`, `_clear_lines()` -- raw termios/ANSI handling
- `display_prompt()`, `read_action()`, `edit_companions()` -- old UI
- `search_prompt()`, `manual_prompt()` -- replaced by textual forms

### Test changes
- New `tests/test_ui/` with textual pilot testing
- `tests/test_importer/test_service.py` -- add tests for execute(plan)
- `tests/test_importer/test_interactive.py` -- keep business logic tests,
  old UI rendering tests become obsolete over time

---

## 9. Resolved Decisions

- **TV episodes**: season group = one match. Split individual episodes out
  to correct them. No per-episode inline review.
- **Accept-all**: removed. Summary section has "Proceed + include auto-accepted"
  toggle instead.
- **Navigation**: Ctrl+Up/Down between groups, Up/Down within group.
- **Layout**: vertical accordion, not horizontal tabs.
- **Auto-accepted groups**: shown as collapsed accordion sections with `[**]`
  badge. User can expand to review if desired.

---

## Appendix A: Full Walkthrough with Sample Directory

### A.1 Sample Directory Structure

```
/downloads/
  Dune.2021.2160p.BluRay.x265.DTS-HD.mkv
  Dune.2021.en.srt
  Dune.2021.de.srt
  poster.jpg
  url.lnk                                          <- ignored (IGNORE category)

  Arrival.2016.1080p.WEB-DL.DD5.1.H264.mkv
  Arrival.2016.en.srt

  Kill.Bill.Vol.1.2003.1080p.mkv
  Kill.Bill.Vol.2.2004.1080p.mkv

  LOTR.Fellowship/
    LOTR.Fellowship.CD1.mkv
    LOTR.Fellowship.CD2.mkv
    LOTR.Fellowship.en.srt
    cover.jpg

  Breaking.Bad.S01/
    Breaking.Bad.S01E01.Pilot.720p.mkv
    Breaking.Bad.S01E02.Cats.in.the.Bag.720p.mkv
    Breaking.Bad.S01E03.And.the.Bags.in.the.River.720p.mkv
    Breaking.Bad.S01E01.en.srt
    Breaking.Bad.S01E02.en.srt
    poster.jpg

  Breaking.Bad.S02/
    Breaking.Bad.S02E01.Seven.Thirty.Seven.720p.mkv
    Breaking.Bad.S02E02.Grilled.720p.mkv
    Subs/
      Breaking.Bad.S02E01.en.srt
      Breaking.Bad.S02E02.en.srt

  random_clip.avi                                   <- guessit can't parse, no TMDB match
  bonus_featurette.mkv                              <- loose file, no clear movie
  README.txt                                        <- not a video, ignored by scanner
  nzb/                                              <- hidden-ish dir with junk
    indexer.nzb
```

### A.2 What the Scanner and Grouper Produce

**Scanner finds 11 video files** (README.txt, url.lnk, nzb/ contents ignored):
- Dune.2021.2160p.BluRay.x265.DTS-HD.mkv
- Arrival.2016.1080p.WEB-DL.DD5.1.H264.mkv
- Kill.Bill.Vol.1.2003.1080p.mkv
- Kill.Bill.Vol.2.2004.1080p.mkv
- LOTR.Fellowship.CD1.mkv
- LOTR.Fellowship.CD2.mkv
- Breaking.Bad.S01E01.Pilot.720p.mkv
- Breaking.Bad.S01E02.Cats.in.the.Bag.720p.mkv
- Breaking.Bad.S01E03.And.the.Bags.in.the.River.720p.mkv
- Breaking.Bad.S02E01.Seven.Thirty.Seven.720p.mkv
- Breaking.Bad.S02E02.Grilled.720p.mkv
- random_clip.avi
- bonus_featurette.mkv

**Grouper builds 9 groups**:

| # | Group | Type | Videos | Companions |
|---|-------|------|--------|------------|
| 1 | Dune (2021) | movie | 1 | 2 subs, 1 artwork, 1 ignored |
| 2 | Arrival (2016) | movie | 1 | 1 sub |
| 3 | Kill Bill Vol. 1 (2003) | movie | 1 | 0 |
| 4 | Kill Bill Vol. 2 (2004) | movie | 1 | 0 |
| 5 | LOTR Fellowship | multi-part | 2 (CD1, CD2) | 1 sub, 1 artwork |
| 6 | Breaking Bad S01 | season | 3 | 2 subs, 1 artwork |
| 7 | Breaking Bad S02 | season | 2 | 2 subs (in Subs/ subdir) |
| 8 | Unknown: random_clip.avi | movie | 1 | 0 |
| 9 | Unknown: bonus_featurette.mkv | movie | 1 | 0 |

Kill Bill Vol. 1 and Vol. 2 are separate movies (different TMDB IDs), not a
multi-part movie. LOTR Fellowship is a multi-part movie: one film split across
two disc files (CD1/CD2), sharing a single TMDB ID.

**Identification results** (after TMDB lookup):

| Group | Top candidate | Confidence | Auto-accept? (threshold=0.85) |
|-------|---------------|------------|-------------------------------|
| Dune (2021) | Dune: Part One (2021) tmdb:438631 | 0.94 | yes |
| Arrival (2016) | Arrival (2016) tmdb:329865 | 0.91 | yes |
| Kill Bill Vol. 1 | Kill Bill: Vol. 1 (2003) tmdb:24 | 0.91 | yes |
| Kill Bill Vol. 2 | Kill Bill: Vol. 2 (2004) tmdb:393 | 0.89 | yes |
| LOTR Fellowship | The Fellowship of the Ring (2001) tmdb:120 | 0.93 | yes |
| Breaking Bad S01 | Breaking Bad (2008) tmdb:1396 | 0.87 | yes |
| Breaking Bad S02 | Breaking Bad (2008) tmdb:1396 | 0.87 | yes |
| Unknown: random_clip.avi | (no candidates) | -- | no |
| Unknown: bonus_featurette.mkv | (no candidates) | -- | no |

For the LOTR multi-part group, both CD1 and CD2 share tmdb:120. All parts
get the same match automatically.

For the Breaking Bad seasons, after the show-level match, per-episode
lookups are constrained to that show+season. Each episode gets an individual
confidence score. Episodes that can't be found show `(no match)` in red.

### A.3 Initial Screen -- App Launch

The user runs `tapes import /downloads --interactive`. After scanning and
identification, the textual app launches. Groups 1-7 are auto-accepted.
Groups 8-9 have no match and are pending. Focus starts on the first pending
group.

```
 tapes import /downloads                                        q quit
+--------------------------------------------------------------------+
|                                                                    |
| [**] Dune (2021)            -> Dune: Part One  tmdb:438631  94%   |
| [**] Arrival (2016)         -> Arrival  tmdb:329865  91%          |
| [**] Kill Bill Vol. 1       -> Kill Bill: Vol. 1  tmdb:24  91%    |
| [**] Kill Bill Vol. 2       -> Kill Bill: Vol. 2  tmdb:393  89%   |
| [**] LOTR Fellowship        -> The Fellowship  tmdb:120  93%      |
| [**] Breaking Bad S01       -> Breaking Bad  tmdb:1396  87%       |
| [**] Breaking Bad S02       -> Breaking Bad  tmdb:1396  87%       |
|                                                                    |
| [??] Unknown: random_clip.avi  ->  (no match)             [FOCUS] |
| +----------------------------------------------------------------+ |
| |                                                                | |
| |  Candidates                                                    | |
| |  (no candidates found)                                         | |
| |                                                                | |
| |  Files                                                         | |
| |  video  random_clip.avi                                        | |
| |                                                                | |
| +----------------------------------------------------------------+ |
|                                                                    |
| [??] Unknown: bonus_featurette.mkv  ->  (no match)               |
|                                                                    |
| === Summary ================================================ |
| Auto-accepted: 7    Pending: 2    Skipped: 0                     |
| [Proceed + auto-accepted]  [Cancel]                               |
|                                                                    |
+--------------------------------------------------------------------+
| ^up/^down groups  up/down items  enter accept  s search  m manual |
| x skip  e files  p split  j merge  c copy  q quit                |
+--------------------------------------------------------------------+
```

Notes:
- `[**]` = auto-accepted (blue). These passed the 0.85 threshold.
- `[??]` = pending (yellow). random_clip.avi is focused and expanded.
- Kill Bill Vol. 1 and Vol. 2 are separate movie groups (different TMDB IDs).
- LOTR Fellowship is a multi-part group (CD1+CD2, same TMDB ID).
- File list shows files plainly -- no checkboxes. They are in the group.
- The second pending group (bonus_featurette.mkv) is collapsed below.
- The summary only shows "Proceed + auto-accepted" because there are no
  user-confirmed groups yet. "Proceed" (confirmed only) would import nothing.

### A.4 User Skips Both Unknown Files

The user presses **x** to skip random_clip.avi. Focus auto-advances to the
next pending group (bonus_featurette.mkv). User presses **x** again. No
pending groups remain, so focus moves to the summary section.

```
 tapes import /downloads                                        q quit
+--------------------------------------------------------------------+
|                                                                    |
| [**] Dune (2021)            -> Dune: Part One  tmdb:438631  94%   |
| [**] Arrival (2016)         -> Arrival  tmdb:329865  91%          |
| [**] Kill Bill Vol. 1       -> Kill Bill: Vol. 1  tmdb:24  91%    |
| [**] Kill Bill Vol. 2       -> Kill Bill: Vol. 2  tmdb:393  89%   |
| [**] LOTR Fellowship        -> The Fellowship  tmdb:120  93%      |
| [**] Breaking Bad S01       -> Breaking Bad  tmdb:1396  87%       |
| [**] Breaking Bad S02       -> Breaking Bad  tmdb:1396  87%       |
| [--] Unknown: random_clip.avi  ->  (skipped)                      |
| [--] Unknown: bonus_featurette.mkv  ->  (skipped)                 |
|                                                                    |
| === Summary ====================================================  |
| Auto-accepted: 7    Pending: 0    Skipped: 2              [FOCUS] |
|                                                                    |
| > [Proceed + auto-accepted]                                       |
|   [Cancel]                                                        |
|                                                                    |
+--------------------------------------------------------------------+
| up/down options  enter select                                     |
+--------------------------------------------------------------------+
```

### A.5 User Wants to Review LOTR Fellowship First

Instead of proceeding, the user presses **Ctrl+Up** to navigate back up.
They land on LOTR Fellowship and it expands, showing multi-part movie details:

```
 tapes import /downloads                                        q quit
+--------------------------------------------------------------------+
|                                                                    |
| [**] Dune (2021)            -> Dune: Part One  tmdb:438631  94%   |
| [**] Arrival (2016)         -> Arrival  tmdb:329865  91%          |
| [**] Kill Bill Vol. 1       -> Kill Bill: Vol. 1  tmdb:24  91%    |
| [**] Kill Bill Vol. 2       -> Kill Bill: Vol. 2  tmdb:393  89%   |
|                                                                    |
| [**] LOTR Fellowship        -> The Fellowship  tmdb:120  93%      |
| +----------------------------------------------------------------+ |
| |  Candidates                                                    | |
| |  > The Fellowship of the Ring (2001)  tmdb:120  93%     green  | |
| |    Fellowship (2004)                  tmdb:9912  31%    red    | |
| |                                                                | |
| |  Files                                                         | |
| |  video     LOTR.Fellowship.CD1.mkv     -> The Fellowship  93%  | |
| |  video     LOTR.Fellowship.CD2.mkv     -> The Fellowship  93%  | |
| |  subtitle  LOTR.Fellowship.en.srt                               | |
| |  artwork   cover.jpg                                            | |
| |                                                                | |
| |  Dest: Movies/The Lord of the Rings The Fellowship (2001)/     | |
| +----------------------------------------------------------------+ |
|                                                                    |
| [**] Breaking Bad S01       -> Breaking Bad  tmdb:1396  87%       |
| [**] Breaking Bad S02       -> Breaking Bad  tmdb:1396  87%       |
| [--] Unknown: random_clip.avi  ->  (skipped)                      |
| [--] Unknown: bonus_featurette.mkv  ->  (skipped)                 |
|                                                                    |
| === Summary ================================================ |
| Auto-accepted: 7    Pending: 0    Skipped: 2                     |
+--------------------------------------------------------------------+
| ^up/^down groups  up/down items  enter accept  s search  m manual |
| x skip  e files  p split  j merge  c copy  q quit                |
+--------------------------------------------------------------------+
```

Notes:
- Both CD1 and CD2 show the same match on the same row as the filename.
  All parts share one TMDB ID -- they are one movie split across files.
- Companion files (subtitle, artwork) are grouped below without repeating
  the match.
- The user confirms with **enter**, changing `[**]` -> `[ok]`.

### A.6 User Reviews Breaking Bad S01 with Per-Episode Matches

User navigates to Breaking Bad S01 with Ctrl+Down:

```
| [**] Breaking Bad S01       -> Breaking Bad  tmdb:1396  87%       |
| +----------------------------------------------------------------+ |
| |  Candidates                                                    | |
| |  > Breaking Bad (2008)        tmdb:1396                green   | |
| |                                                                | |
| |  Files                                         avg conf: 90%   | |
| |                                                                | |
| |  video     S01E01.Pilot.720p.mkv       S01E01 Pilot  92% green | |
| |  subtitle  S01E01.en.srt                                       | |
| |                                                                | |
| |  video     S01E02.Cats.in.the.Bag.720p.mkv                    | |
| |                          S01E02 Cat's in the Bag  91% green    | |
| |  subtitle  S01E02.en.srt                                       | |
| |                                                                | |
| |  video     S01E03.And.the.Bags.in.the.River.720p.mkv          | |
| |                     S01E03 ...and the Bag's  88% green         | |
| |                                                                | |
| |  artwork   poster.jpg                       (season-level)     | |
| |                                                                | |
| |  Dest: TV/Breaking Bad (2008)/Season 01/                      | |
| +----------------------------------------------------------------+ |
```

Notes:
- Each video file shows its episode match on the same row (or immediately
  adjacent if the line is too long). Companions for that episode appear
  directly below. Empty lines separate each episode+companions block.
- `poster.jpg` is a season-level companion, not tied to any episode.
- The show-level candidate confidence (87%) was from the initial search.
  The per-episode avg (90%) is computed from individual episode lookups.
- The user sees all three episodes match well. They press **enter** to
  confirm, or notice a problem and split.

### A.7 User Notices S01E03 Is Actually a Different Show -- Splits It

The user sees that S01E03's episode match confidence is lower and the
title looks wrong. They press **p** to split:

```
  +-- Split: Breaking Bad S01 ----------------------------------------+
  |                                                                    |
  |  Mark files to move to a new group:                                |
  |                                                                    |
  |    S01E01.Pilot.720p.mkv                                           |
  |    S01E02.Cats.in.the.Bag.720p.mkv                                 |
  |  * S01E03.And.the.Bags.in.the.River.720p.mkv                marked |
  |    S01E01.en.srt                                                    |
  |    S01E02.en.srt                                                    |
  |    poster.jpg                                                       |
  |                                                                    |
  |  1 file marked  (tab mark, enter split, esc cancel)                |
  +--------------------------------------------------------------------+
```

User marks S01E03 with **Tab**, presses **Enter**. A new group appears:

```
| [**] Breaking Bad S01       -> Breaking Bad  tmdb:1396  91%       |
| +----------------------------------------------------------------+ |
| |  Candidates                                                    | |
| |  > Breaking Bad (2008)        tmdb:1396                green   | |
| |                                                                | |
| |  Files                                         avg conf: 91%   | |
| |                                                                | |
| |  video     S01E01.Pilot.720p.mkv       S01E01 Pilot  92% green | |
| |  subtitle  S01E01.en.srt                                       | |
| |                                                                | |
| |  video     S01E02.Cats.in.the.Bag.720p.mkv                    | |
| |                          S01E02 Cat's in the Bag  91% green    | |
| |  subtitle  S01E02.en.srt                                       | |
| |                                                                | |
| |  artwork   poster.jpg                       (season-level)     | |
| |                                                                | |
| |  Dest: TV/Breaking Bad (2008)/Season 01/                      | |
| +----------------------------------------------------------------+ |
|                                                                    |
| [??] Unknown: S01E03  ->  (pending)                               |
```

Notes:
- Breaking Bad S01 now shows 2 episodes with unified file+match rows.
  Average confidence rose to 91% because the lower-scoring E03 was removed.
- The new group "Unknown: S01E03" is pending below.

### A.8 User Searches for the Split Episode

User presses **Ctrl+Down** to focus "Unknown: S01E03", presses **s**:

```
| [??] Unknown: S01E03  ->  (no match)                      [FOCUS] |
| +----------------------------------------------------------------+ |
| |  Candidates                                                    | |
| |  (no candidates found)                                         | |
| |                                                                | |
| |  Search TMDB                                                   | |
| |  Type:  [tv        v]                                         | |
| |  Title: [Better Call Saul                ]                     | |
| |  Year:  [           ]                                          | |
| |  > [Search]  [Cancel]                                          | |
| |                                                                | |
| |  Files                                                         | |
| |  video  S01E03.And.the.Bags.in.the.River.720p.mkv             | |
| +----------------------------------------------------------------+ |
```

User types "Better Call Saul", presses Search. TMDB returns results:

```
| [??] Unknown: S01E03  ->  (pending)                        [FOCUS] |
| +----------------------------------------------------------------+ |
| |  Candidates                                                    | |
| |  > Better Call Saul (2015)    tmdb:60059  78%           green   | |
| |    Better Call Saul (anime)   tmdb:99421  22%           red     | |
| |                                                                | |
| |  Files                                                         | |
| |  video  S01E03.And.the.Bags.in.the.River.720p.mkv             | |
| |                                                                | |
| |  Dest: TV/Better Call Saul (2015)/Season 01/                   | |
| +----------------------------------------------------------------+ |
```

User presses **enter** to accept. Group becomes `[ok]`. Focus advances
to summary.

### A.9 User Reassigns a Subtitle via File Editor

But wait -- the user realizes that `S01E02.en.srt` in Breaking Bad S01
actually belongs to the bonus_featurette.mkv they skipped earlier.

User presses **Ctrl+Up** to navigate to the bonus_featurette group and
un-skips it (pressing any action key on a skipped group reverts to pending).
Then presses **e** to open the file editor:

```
  +-- Edit Files: bonus_featurette.mkv --------------------------------+
  |                                                                      |
  |  Search: [en.srt                                                   ] |
  |                                                                      |
  |  bonus_featurette.mkv                           bonus_featurette.mkv  |  <- current group (bold cyan)
  |  Arrival.2016.en.srt                            Arrival (2016)        |  <- dim
  |  Dune.2021.en.srt                               Dune (2021)           |  <- dim
  |  Dune.2021.de.srt                               Dune (2021)           |  <- dim
  |  LOTR.Fellowship.en.srt                         LOTR Fellowship        |  <- dim
  |  S01E01.en.srt                                  Breaking Bad S01      |  <- dim
  |> S01E02.en.srt                                  Breaking Bad S01      |  <- dim, cursor here
  |  S02E01.en.srt                                  Breaking Bad S02      |  <- dim
  |  S02E02.en.srt                                  Breaking Bad S02      |  <- dim
  |                                                                      |
  |  9 files matching "en.srt"  (tab toggle, enter confirm, esc cancel)  |
  +----------------------------------------------------------------------+
```

User navigates to `S01E02.en.srt` and presses **Tab**. It moves from
Breaking Bad S01 to the current group (bonus_featurette.mkv) and turns
bold cyan. The Breaking Bad S01 label next to it disappears.

```
  |  bonus_featurette.mkv                           bonus_featurette.mkv  |  <- bold cyan
  |  S01E02.en.srt                                  bonus_featurette.mkv  |  <- bold cyan (just added!)
  |  Arrival.2016.en.srt                            Arrival (2016)        |  <- dim
```

User presses **Enter** to confirm. Modal closes. The bonus_featurette
group now has 2 files, and Breaking Bad S01 lost a subtitle.

### A.10 Final Summary -- User Proceeds

```
 tapes import /downloads                                        q quit
+--------------------------------------------------------------------+
|                                                                    |
| [ok] Dune (2021)            -> Dune: Part One  tmdb:438631  94%   |
| [**] Arrival (2016)         -> Arrival  tmdb:329865  91%          |
| [**] Kill Bill Vol. 1       -> Kill Bill: Vol. 1  tmdb:24  91%    |
| [**] Kill Bill Vol. 2       -> Kill Bill: Vol. 2  tmdb:393  89%   |
| [ok] LOTR Fellowship        -> The Fellowship  tmdb:120  93%      |
| [ok] Breaking Bad S01       -> Breaking Bad  tmdb:1396  91%       |
| [ok] Better Call Saul S01E03 -> Better Call Saul  tmdb:60059  78% |
| [**] Breaking Bad S02       -> Breaking Bad  tmdb:1396  87%       |
| [--] Unknown: random_clip.avi  ->  (skipped)                      |
| [??] bonus_featurette.mkv   -> (pending)                          |
|                                                                    |
| === Summary ====================================================  |
| Accepted: 4    Auto-accepted: 4    Pending: 1    Skipped: 1      |
|                                                                    |
| > [Proceed + auto-accepted]  (will import 8 groups, 12 videos)   |
|   [Proceed]                  (will import 4 groups, 7 videos)    |
|   [Cancel]                                                        |
|                                                                    |
+--------------------------------------------------------------------+
| up/down options  enter select                                     |
+--------------------------------------------------------------------+
```

Notes:
- The user confirmed Dune, LOTR Fellowship, BB S01, and BCS S01E03 manually.
- Arrival, Kill Bill Vol. 1, Kill Bill Vol. 2, and BB S02 remain auto-accepted.
- bonus_featurette.mkv is still pending (user added a subtitle but never
  searched/matched it). "Proceed" would skip it. "Proceed + auto-accepted"
  would also skip it (pending != auto-accepted).
- random_clip.avi was skipped entirely.

User presses enter on "Proceed + auto-accepted". The textual app exits
and returns an ImportPlan. ImportService.execute() runs the file operations.

### A.11 Post-Import Output (after textual exits)

The log uses a table-like format: `mode | source | destination` on one line
per file. Groups from the TUI are separated by empty lines. This format is
both human-readable and easily parsable (pipe-delimited, like a simplified
CSV/markdown table).

```
$ tapes import /downloads --interactive

Importing 12 videos + companions from 8 groups...

 copy | Dune.2021.2160p.BluRay.x265.DTS-HD.mkv          | Movies/Dune Part One (2021)/Dune Part One (2021).mkv
 copy | Dune.2021.en.srt                                 | Movies/Dune Part One (2021)/Dune Part One (2021).en.srt
 copy | Dune.2021.de.srt                                 | Movies/Dune Part One (2021)/Dune Part One (2021).de.srt
 copy | poster.jpg                                       | Movies/Dune Part One (2021)/poster.jpg

 copy | Arrival.2016.1080p.WEB-DL.DD5.1.H264.mkv        | Movies/Arrival (2016)/Arrival (2016).mkv
 copy | Arrival.2016.en.srt                              | Movies/Arrival (2016)/Arrival (2016).en.srt

 copy | Kill.Bill.Vol.1.2003.1080p.mkv                   | Movies/Kill Bill Vol 1 (2003)/Kill Bill Vol 1 (2003).mkv

 copy | Kill.Bill.Vol.2.2004.1080p.mkv                   | Movies/Kill Bill Vol 2 (2004)/Kill Bill Vol 2 (2004).mkv

 copy | LOTR.Fellowship.CD1.mkv                          | Movies/The Fellowship of the Ring (2001)/The Fellowship of the Ring (2001).CD1.mkv
 copy | LOTR.Fellowship.CD2.mkv                          | Movies/The Fellowship of the Ring (2001)/The Fellowship of the Ring (2001).CD2.mkv
 copy | LOTR.Fellowship.en.srt                           | Movies/The Fellowship of the Ring (2001)/The Fellowship of the Ring (2001).en.srt
 copy | cover.jpg                                        | Movies/The Fellowship of the Ring (2001)/cover.jpg

 copy | Breaking.Bad.S01E01.Pilot.720p.mkv               | TV/Breaking Bad (2008)/Season 01/Breaking Bad S01E01.mkv
 copy | S01E01.en.srt                                    | TV/Breaking Bad (2008)/Season 01/Breaking Bad S01E01.en.srt
 copy | Breaking.Bad.S01E02.Cats.in.the.Bag.720p.mkv    | TV/Breaking Bad (2008)/Season 01/Breaking Bad S01E02.mkv
 copy | S01E02.en.srt                                    | TV/Breaking Bad (2008)/Season 01/Breaking Bad S01E02.en.srt

 copy | Breaking.Bad.S01E03.And.the.Bags.720p.mkv       | TV/Better Call Saul (2015)/Season 01/Better Call Saul S01E03.mkv

 copy | Breaking.Bad.S02E01.Seven.Thirty.Seven.720p.mkv | TV/Breaking Bad (2008)/Season 02/Breaking Bad S02E01.mkv
 copy | Subs/Breaking.Bad.S02E01.en.srt                  | TV/Breaking Bad (2008)/Season 02/Breaking Bad S02E01.en.srt
 copy | Breaking.Bad.S02E02.Grilled.720p.mkv            | TV/Breaking Bad (2008)/Season 02/Breaking Bad S02E02.mkv
 copy | Subs/Breaking.Bad.S02E02.en.srt                  | TV/Breaking Bad (2008)/Season 02/Breaking Bad S02E02.en.srt

Imported: 12 videos, 9 companions    Skipped: 2    Errors: 0
```

Format: `mode | source (relative to import root) | destination (relative to library root)`

- Groups from the TUI are reflected as blank-line-separated blocks
- Within a season group, files are ordered by episode, with companions
  following their video
- The `mode` column is `copy`, `move`, or `link` depending on config
- Easily greppable: `grep "^  copy" output.txt | cut -d'|' -f2,3`

Skipped: random_clip.avi (user skipped) and bonus_featurette.mkv (still
pending, not included in proceed + auto-accepted).

## 10. Open Questions

1. Should collapsed groups be clickable (mouse) to expand? textual supports
   mouse -- probably yes for free.
2. Should the destination preview show the full tree (all files) or just
   the video destination?
3. Textual testing strategy: pilot (simulated input) vs snapshot tests?
   Probably both -- pilot for interaction flows, snapshot for layout.
4. What happens to existing E2E tests? They mock `_prompt_user` which
   bypasses the UI entirely -- they should keep working.
