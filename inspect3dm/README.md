# 3dm-inspect

`3dm-inspect` checks Rhino `.3dm` files against a rule profile without Rhino, so you can inspect one model or a whole folder in batch, on a file server, or in CI (including Linux). It reports invalid objects, model units and tolerances, open or non-manifold meshes, layer hygiene, and (with `--profile revit`) edges and curves shorter than Revit's short-curve tolerance and geometry beyond Revit's distance limits, as a Markdown report for people or JSON for machines, with exit codes for CI. Input: a `.3dm` file or a folder. Output: a report on standard output or in a file.

Validity results come from McNeel's openNURBS library (via rhino3dm). They may differ from Rhino's Check command. This tool reports problems; it does not repair models, and it is not a substitute for Check, SelBadObjects, or your own review.

## What it does not do

- It does not repair, modify, or write back to your `.3dm` files. It only reads them.
- It does not claim parity with Rhino's `Check`. Parity has not been tested on a Rhino host.
- It does not run Rhino-only analysis (self-intersections, `MeshRepair`-level diagnostics).
- It does not run Revit. The `revit` profile checks a file against published or widely reported Revit limits; a clean report does not guarantee that Revit will import the file.
- It does not approve or certify a model. A clean report means no findings for the chosen profile, nothing more.
- No GUI, no telemetry, no network calls.

This is v0.2, an alpha release, not a finished product. v0.2 has been run and tested on Linux only. The `revit` profile has been tested on synthetic files only; it has not been checked against imports in Revit. Windows and macOS should install via `rhino3dm` wheels but are untested. Large (5–10 GB) files are untested.

## Install

Requires Python 3.10–3.14 on Windows, macOS, or Linux (the versions and platforms that `rhino3dm` 8.x publishes wheels for). The Python package is `inspect3dm`; it installs the `3dm-inspect` command.

There is no PyPI or Food4Rhino listing. Install from a checkout of this repository:

```text
git clone https://github.com/ferall0gic/LIMENLABSPUBLIC.git
cd LIMENLABSPUBLIC
python -m pip install ./inspect3dm
```

For development, including tests:

```text
python -m pip install -e "./inspect3dm[test]"
```

This installs `rhino3dm>=8,<9` as a dependency.

## First run

From the `inspect3dm` directory in the checkout, inspect the provided sample file:

```text
cd inspect3dm
3dm-inspect samples/sample.3dm
```

It prints this report and exits with code 1, because the sample contains one invalid object:

```text
Result: fail. 1 file inspected (0 pass, 1 fail); 1 error, 1 warning.

3dm-inspect 0.2.0, rhino3dm 8.35.0. Profile: default. Fail on: error.

## samples/sample.3dm

Status: fail. 1 error, 1 warning. 2 objects, 2 layers.

Units: millimeters. Absolute tolerance: 0.001 millimeters. Angle tolerance: 1 degree.

| Severity | Rule | Object ID | Type | Layer | Message |
|---|---|---|---|---|---|
| Error | validity | 97792e56-e576-db4f-af5d-79619c8905ad | LineCurve | A-WALL | Line points are coincident. |
| Warning | empty_layer | — | Layer | A-ANNO | Layer has no objects (on it or its sublayers). |

Next steps in Rhino: Check, SelBadObjects.

---

Validity is checked with openNURBS (via rhino3dm) and may differ from Rhino's Check command. This report does not repair models and is not a substitute for Check or for your own review.
```

The report starts with one summary line, then the tool line, then each file's settings and a findings table (errors first). When there are validity or mesh findings, one line points to the matching Rhino commands. Those are pointers; `3dm-inspect` does not run them:

- Validity findings: `Check`, `SelBadObjects`.
- Mesh findings: `CheckMesh`, `MeshRepair`.
- Short-edge findings (`revit` profile): `ShowEdges`, `MergeAllEdges`, `RebuildEdges`.
- Extents findings (`revit` profile): `Zoom` (Extents), `Move`.

For a folder, a one-line-per-file index comes before the per-file sections:

```text
3dm-inspect exports/
```

Folders are searched recursively for `*.3dm` (case-insensitive), in sorted order. An unreadable file is recorded as `unreadable` and the run continues.

## Use in CI

Use `--format json` in CI and choose what fails the build with `--fail-on`:

```text
3dm-inspect exports/ --format json --output report.json
3dm-inspect exports/ --format json --fail-on warning
```

- `--fail-on error` (default): errors fail the run; warnings are informational.
- `--fail-on warning`: any finding fails the run.
- `--fail-on never`: report only. Unreadable files still exit 2.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | All files were read and no finding met `--fail-on`. The run result (Markdown first line and JSON `summary.result`) is `pass`, or `report` (`Result: report only.`) when `--fail-on never` and findings are present. |
| 1 | All files were read and one or more findings met `--fail-on`. The run result is `fail`. |
| 2 | Usage error, invalid profile, no `.3dm` files found in a folder, or a file could not be read. A folder run continues past an unreadable file and exits 2. When a report is produced, the run result is `incomplete` (`Result: incomplete.`). Usage errors and empty folders print an error message and exit 2 with no report. |

An empty folder exits 2, so CI cannot pass when nothing was inspected:

```text
No .3dm files found in 'exports/'. Check the path, or pass a .3dm file directly.
```

### JSON fields

Every run has `tool` (`3dm-inspect`), `tool_version`, `rhino3dm_version`, `profile`, `fail_on`, `generated_at`, `validation_basis` (`openNURBS via rhino3dm; may differ from Rhino Check`), `summary` (`result` is one of `pass`, `fail`, `report`, `incomplete`; also `exit_code`, file counts, `errors`, `warnings`), and `files`. Each file has `path`, `status` (`pass`, `fail`, or `unreadable`), units and tolerances (raw values plus `*_display` strings in model units and degrees), `summary`, `findings`, and `next_steps` when there is a Rhino command to point to. An unreadable file has a `message` instead of settings. Each finding has `severity` (`error` or `warning`), `rule`, `object_id`, `object_type`, `layer`, and `message`. Findings from the v0.2 `short_edges` and `extents` rules also have `measured` and `threshold` (in model units), `units`, and `certainty` (`certain`, `uncertain`, or `near_threshold`); other findings are unchanged from v0.1.

Repeated runs on the same files and profile give identical JSON except `generated_at`.

## Options

| Option | Default | Purpose |
|---|---|---|
| `--profile NAME\|FILE` | `default` | Built-in profile (`default`, `strict`, `revit`) or a `.toml` profile file. |
| `--list-profiles` | | List the built-in profiles and exit. |
| `--format md\|json` | `md` | Report format. If omitted, inferred from an `--output` file ending in `.md` or `.json`. If both are given and disagree, exit 2. Never switched automatically by terminal type. |
| `--fail-on error\|warning\|never` | `error` | Which findings make the run exit 1. |
| `--output FILE` | standard output | Write the report to a file. |
| `--quiet` | off | One line per file plus a total (one line for a single file). No finding detail, no footer. With `--format json`, findings are omitted. |
| `--no-color` | color only on a terminal | Plain text. Color is also off when `NO_COLOR` is set or output is not a terminal. Severity is always written as a word. |
| `--help` | | Options, examples, exit codes. |
| `--version` | | Tool and `rhino3dm` versions. |

## Rules

| Profile section | Rule IDs in reports | Default severity | Default profile | Strict profile | Revit profile |
|---|---|---|---|---|---|
| `validity` | `validity` | error | on | on | on |
| `document` | `units`, `tolerance_range`, `angle_tolerance_range` | warning | on | on | on (units: error; tolerance: warning) |
| `mesh` | `mesh_not_closed`, `mesh_non_manifold` | warning (error in strict) | off | on | off |
| `layers` | `layer_name`, `empty_layer`, `object_without_layer`, `object_on_default_layer` | warning | on (default-layer check off) | on (default-layer check on) | on (default-layer check off) |
| `short_edges` (v0.2) | `short_edges`, `short_edges_unmeasured` | error | off | off | on |
| `extents` (v0.2) | `extents` | warning | off | off | on |

When `short_edges` or `extents` is on and the model has no units (or custom units), those rules cannot convert their millimeter limits and report one `mm_rules_skipped` warning instead of staying silent.

- **validity**: openNURBS `IsValidWithLog` on every object; the openNURBS message is reported unedited, with object ID, type, and layer full path.
- **document**: warns when units are none or unset, or not in `allowed_units`; when absolute tolerance is outside `absolute_tolerance_min`–`absolute_tolerance_max` (default 0.0001–0.01, in model units, following McNeel forum guidance); and when angle tolerance (in degrees) is outside an optional range.
- **mesh**: `Mesh` objects only. "Not closed" uses openNURBS `IsClosed`. "Non-manifold" means an edge shared by more than two faces, counted with vertices merged by identical position (rhino3dm 8.35's `Mesh.IsManifold` reported a single open triangle as non-manifold, so it is not used).
- **short_edges** (v0.2): every Brep edge (Extrusions are converted to their Brep form) and, with `include_curves = true`, every loose curve (each segment of polylines and polycurves) shorter than `min_length_mm`, converted to model units. rhino3dm has no curve-length function, so the tool brackets each length: a lower bound from sampled chords and an upper bound from the NURBS control polygon. If the upper bound is below the minimum the finding is `certain`; if the bounds straddle it, `uncertain`. Lengths up to `near_band` (default 10%) above the minimum get a `near_threshold` warning. An edge that cannot be read is reported as `short_edges_unmeasured`, not skipped silently.
- **extents** (v0.2): each object's bounding box (rhino3dm's `GetBoundingBox()`, which can be slightly larger than the geometry) is checked for its farthest corner from the world origin against `max_distance_from_origin_mm`, and the whole model's bounding-box diagonal against `max_total_extent_mm`. Distances are from the Rhino world origin; where the geometry lands in Revit also depends on how the file is positioned on import.
- **document `*_mm` keys** (v0.2): `absolute_tolerance_min_mm` / `absolute_tolerance_max_mm` are converted to model units; when set and the units are known, each replaces the model-unit key on the same side. `tolerance_severity` sets a separate severity for tolerance findings.
- **layers**: each layer name (not the full path) must match `name_pattern` (empty by default: no naming convention); a layer is empty when neither it nor its sublayers hold objects; objects whose layer index does not resolve to a layer; optionally objects on a layer named in `default_layer_names`.

## Checking files for Revit

```text
3dm-inspect model.3dm --profile revit
3dm-inspect exports/ --profile revit --format json --fail-on error
```

The `revit` profile looks for problems that are commonly reported when Rhino geometry goes into Revit (3DM import, or DirectShapes and families through Rhino.Inside.Revit). It reads the `.3dm` only. It has not been run against Revit, so treat it as an early warning, not a prediction of what Revit will do.

| Check | Value in the profile | Where the value comes from |
|---|---|---|
| Model units set (not "none") | error | Unitless and mismatched-unit files come up again and again in McNeel forum threads about Revit imports. |
| Brep edges and curves at least ~0.79 mm | 0.79375 mm (1/32 in), error | Revit's API has a fixed short-curve tolerance (`Application.ShortCurveTolerance`), and curve creation rejects anything shorter. Autodesk's API reference does not print the value; **the 1/32 in figure comes from Autodesk forum posts and a developer blog**, not from primary documentation. Change it with `min_length_mm` if your Revit reports something different. |
| Lengths within 10% above that minimum | warning | Heads-up band, `near_band = 0.10`. |
| Absolute tolerance no coarser than 1/10 of the short-curve tolerance | 0.079375 mm, warning | A rule of thumb repeated in secondary sources. No primary McNeel or Autodesk source has been found, so it is a warning, not an error. |
| Object within 10 miles of the origin | 16.09 km, warning | Autodesk Revit Help, "About the Maximum Distance Limit". |
| Whole model spans less than 20 miles | 32.19 km, warning | Autodesk Revit Help, "Geometry in the File Has Extents Greater Than 20 Miles (33km)" and "Graphics Issues after Linking or Importing CAD". |
| Invalid objects | error | Revit rejects invalid NURBS and falls back to mesh (Rhino.Inside.Revit guide, "Rhino to Revit"). Same openNURBS check as the default profile. |

Every value can be changed. Write a profile that extends `revit` and lists only what you change; see [examples/revit-office-profile.toml](examples/revit-office-profile.toml):

```toml
[profile]
name = "revit-office"
extends = "revit"

[rules.short_edges]
min_length_mm = 0.8        # what `app.ShortCurveTolerance` reports in your Revit, converted to mm
include_curves = false     # only Brep edges; loose curves are not sent to Revit here

[rules.extents]
severity = "error"         # make stray far-away objects fail the CI gate
```

Not checked yet: meshes (Revit handles them separately), SubD, block instances (geometry inside block definitions is not inspected), and Revit's limits on very large or very small solids. If you can open a model in both Rhino and Revit and compare the results, please report them in an issue.

Sources (accessed 2026-11-13 and 2026-11-15):
- Autodesk, About the Maximum Distance Limit: https://help.autodesk.com/cloudhelp/2027/ENU/Revit-Troubleshooting/files/GUID-3F79BF5A-F051-49F3-951E-D3E86F51BECC.htm
- Autodesk, Geometry in the File Has Extents Greater Than 20 Miles (33km): https://help.autodesk.com/cloudhelp/2027/ENU/Revit-Troubleshooting/files/GUID-D30C39FF-3A53-47DE-8E9E-11B2AB808A07.htm
- Autodesk, Graphics Issues after Linking or Importing CAD: https://help.autodesk.com/cloudhelp/2027/ENU/Revit-Troubleshooting/files/GUID-FF308831-85AF-4B29-A694-184CD15FC665.htm
- Autodesk Revit API forum, "How to avoid the 0.8mm pitfall in Revit?" (forum, not primary): https://forums.autodesk.com/t5/revit-api-forum/how-to-avoid-the-0-8mm-pitfall-in-revit/td-p/12985636
- Autodesk developer blog, "DirectShape Performance and Minimum Size" (blog, not primary): https://blog.autodesk.io/directshape-performance-and-minimum-size/
- Rhino.Inside.Revit guide, Rhino to Revit: https://www.rhino3d.com/inside/revit/1.0/guides/rhino-to-revit
- McNeel Discourse, "Edge tolerance problem Rhino.Inside Revit": https://discourse.mcneel.com/t/edge-tolerance-problem-rhino-inside-revit/118712

## Write an office profile

A profile is a TOML file. List only what you change; everything else comes from `extends` (`default` unless you say `strict` or `revit`). See [examples/office-profile.toml](examples/office-profile.toml):

```toml
# Example office profile for 3dm-inspect.
# Use with:  3dm-inspect exports/ --profile examples/office-profile.toml
# Only the keys you list here change; the rest come from `extends`.

[profile]
name = "example-office"
extends = "default"

[rules.document]
allowed_units = ["millimeters", "meters"]
absolute_tolerance_min = 0.001
absolute_tolerance_max = 0.01
angle_tolerance_min_degrees = 0.1
angle_tolerance_max_degrees = 2.0

[rules.mesh]
enabled = true            # meshes must be closed and manifold
severity = "warning"

[rules.layers]
# AIA-style names such as A-WALL or A-WALL-EXTR (each layer level is checked).
name_pattern = '^[A-Z]-[A-Z0-9]+(-[A-Z0-9]+)*$'
flag_objects_on_default_layer = true
```

```text
3dm-inspect exports/ --profile examples/office-profile.toml
```

The built-in profiles are in [src/inspect3dm/profiles/](src/inspect3dm/profiles/) and list every key. A profile with a typo, an unknown key, a bad regular expression, a minimum above its maximum, or invalid TOML stops the run with a specific message and exit 2.

## Report issues and license

This tool is part of [LIMEN Labs Public](https://github.com/ferall0gic/LIMENLABSPUBLIC). Open an issue there with the command you ran, the `3dm-inspect --version` line, and the report. Attach a model only if you are allowed to share it. Feedback is especially welcome from computational designers who can test on Windows or macOS, or compare results with Rhino's Check command.

License: MIT. See [LICENSE](LICENSE). `rhino3dm` is McNeel's, under the MIT license.

## Development

From the repository root:

```text
python -m pip install -e "./inspect3dm[test]"
python -m pytest inspect3dm/tests
```

Or from this directory:

```text
python -m pip install -e ".[test]"
python -m pytest
python scripts/make_fixtures.py fixtures-out   # write every test fixture to a folder
python scripts/make_sample.py                  # regenerate samples/sample.3dm (object IDs change)
```

Fixtures are generated with `rhino3dm` by `scripts/make_fixtures.py`; there are no client or third-party models in this repository. See [CHANGELOG.md](CHANGELOG.md) for what changed in each version.

---

Validity is checked with openNURBS (via rhino3dm) and may differ from Rhino's Check command. This report does not repair models and is not a substitute for Check or for your own review.
