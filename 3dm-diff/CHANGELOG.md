# Changelog

## 0.1.0 (2026-11-15)

- First public release: an ID-based diff of two `.3dm` files covering objects, layers, document settings, and document user text. It produces Markdown and JSON, uses `diff`-style exit codes, and has `--match-geometry`, `--ignore`, and a `--textconv` mode for `git diff`.
- Tested on synthetic files written with rhino3dm 8.35.0 on Linux only. Not tested across Rhino versions.
