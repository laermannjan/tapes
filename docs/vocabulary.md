# Vocabulary Reference

Canonical terminology for the tapes codebase. When renaming, use these terms.

## Terms

| Concept | Canonical term | Was | Notes |
|---|---|---|---|
| File's accumulated metadata | `node.metadata` | `node.result` | Dict of fields (title, year, etc.) |
| A potential match from TMDB/guessit | `Candidate` | `Source` | Has `.metadata`, `.score`, `.name` |
| Candidate's metadata dict | `candidate.metadata` | `source.fields` | Same key structure as node.metadata |
| One key-value pair in a metadata dict | "field" | "field" | Unchanged |
| Match quality measurement | `.score` | `.confidence` | Float 0-1 from similarity function |
| List of candidates on a file node | `node.candidates` | `node.sources` | |
| Choosing a candidate for the file | "accept" | "accept"/"apply" | `accept_current_candidate()` |
| Finalizing an inline field edit | "apply" | "commit" | `apply_edit()` |
| Executing file operations | "commit" | "commit" | Unchanged |
| App state machine states | `AppState` | `AppMode` | Enum values: TREE, METADATA, COMMIT, HELP, TREE_SEARCH |
| Metadata curation view/state | METADATA / MetadataView | DETAIL / DetailView | |
| Help view widget | HelpView | HelpOverlay | Already named HelpView, just the file |
| Metadata extraction module | `tapes/extract.py` | `tapes/metadata.py` | guessit wrapper, future nfo parsing |
| Template/path utilities | `tapes/templates.py` | scattered in `tapes/ui/tree_render.py` | |
| Color palette + semantic tokens | `tapes/ui/colors.py` | top of `tapes/ui/tree_render.py` | |
| Auto-accept gate params | `min_score`, `min_prominence` | `margin_accept_threshold`, `min_accept_margin` | Single gate, no tiers |
| Bundled pipeline params | `PipelineParams` | 10-13 kwargs | Dataclass |

## Pipeline flow (canonical terms)

1. **Scan.** Find files in the input directory.
2. **Extract.** Parse each filename with guessit to produce initial
   `node.metadata` and a guessit `Candidate`.
3. **Search.** Query TMDB using extracted title/year. Each result becomes a
   `Candidate` with a `.score` from the similarity function.
4. **Auto-accept gate.** If the top candidate's `.score` meets `min_score`
   and its prominence over the runner-up meets `min_prominence`, accept it
   automatically. For TV files, acceptance triggers an episode query.
5. **Curate (TUI).** User browses the tree, opens the MetadataView to
   inspect candidates, accepts or edits fields, and stages files.
6. **Commit.** Staged files are processed (copy/move/link) into the library.
