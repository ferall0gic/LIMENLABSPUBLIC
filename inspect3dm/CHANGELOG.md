# Changelog

## Unreleased (work in progress on branch `rhino9-compat`; not released)

Changed
- rhino3dm 9.x readiness: every rhino3dm call that changed shape in 9.x goes through a small feature-detecting module (`_rh.py`). The dependency pin stays `rhino3dm>=8,<9`; 9.x is pre-release.
- A check that cannot be evaluated on an object (validity, extents bounding box) is now reported as an `info` finding with rule `tool_error` instead of being skipped silently. Under rhino3dm 9.2 the previous code would have dropped every openNURBS validity message and every bounding box without a word. `info` findings never count as errors or warnings and never change the exit code.

Tests
- Fake-based tests for both API shapes; fixture script works under rhino3dm 8 and 9. `INSPECT3DM_FIXTURES=<folder>` runs the suite on fixtures built earlier (rhino3dm 9.2.0b0/b1 cannot set `ModelUnitSystem` from Python).
- Box run, synthetic fixtures: rhino3dm 8.35.0 159 passed; rhino3dm 9.2.0b1 155 passed, 4 skipped (unit-setter and README-sample tests).

## 0.2.0 (2026-11-15)

Added
- Built-in `revit` profile (`--profile revit`) that checks a `.3dm` against known Revit import limits before the file leaves Rhino. It does not run Revit and has been tested on synthetic files only.
- `short_edges` rule: Brep edges (Extrusions via their Brep form) and, optionally, loose curve segments shorter than `min_length_mm` (default 0.79375 mm, about 1/32 in; that value comes from Autodesk forum and blog posts, not primary documentation, and is configurable). Lengths are bracketed between a sampled-chord lower bound and a control-polygon upper bound and labelled `certain`, `uncertain`, or `near_threshold`. Edges that cannot be read are reported as `short_edges_unmeasured`.
- `extents` rule: objects farther than 10 miles (16.09 km) from the world origin and models whose bounding-box diagonal exceeds 20 miles (32.19 km), per Autodesk Revit Help.
- Unit-aware document tolerance keys `absolute_tolerance_min_mm` / `absolute_tolerance_max_mm` and a separate `tolerance_severity`.
- `mm_rules_skipped` warning when mm-based rules cannot run because the model has no units.
- JSON findings from the new rules carry `measured`, `threshold`, `units`, and `certainty`.
- `--list-profiles` option.
- `examples/revit-office-profile.toml`, 10 new synthetic fixtures in `scripts/make_fixtures.py`, and tests for the new rules and length bounds.

Unchanged
- `default` and `strict` profiles: Markdown and JSON reports are identical to 0.1.0 (apart from the version number) on all 23 fixtures.
- Exit codes, report layout, and v0.1 finding fields.

Not included
- No PyPI or Food4Rhino release. No CI workflow in this repository yet.

## 0.1.0 (2026-11-12)

- First public release: headless inspector for `.3dm` files with `default` and `strict` profiles (validity, units and tolerances, meshes, layers), Markdown and JSON reports, and CI exit codes.
