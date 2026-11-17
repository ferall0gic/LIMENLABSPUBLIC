# Changelog

## Unreleased (work in progress on branch `rhino9-compat`; not released)

- rhino3dm 9.x readiness through the same `_rh.py` module as inspect3dm (layer visibility/lock, object IDs, bounding boxes, document text, missing-file reads). Pin stays `rhino3dm>=8,<9`.
- Fixed: document user text was silently read as empty under rhino3dm 9.2 (the string table has no `len`/indexing there). Errors reading document text are no longer swallowed.
- `DIFF3DM_FIXTURES=<folder>` runs the suite on prebuilt fixtures. Box run: rhino3dm 8.35.0 and 9.2.0b1 both 27 passed (9.x on fixtures built under 8.35).

## 0.1.0 (2026-11-15)

- First public release: an ID-based diff of two `.3dm` files covering objects, layers, document settings, and document user text. It produces Markdown and JSON, uses `diff`-style exit codes, and has `--match-geometry`, `--ignore`, and a `--textconv` mode for `git diff`.
- Tested on synthetic files written with rhino3dm 8.35.0 on Linux only. Not tested across Rhino versions.
