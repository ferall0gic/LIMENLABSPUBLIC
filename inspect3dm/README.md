# 3dm-inspect

`3dm-inspect` checks Rhino `.3dm` files against a rule profile without Rhino, so you can inspect one model or a whole folder in batch, on a file server, or in CI (including Linux). It reports invalid objects, model units and tolerances, open or non-manifold meshes, and layer hygiene, as a Markdown report for people or JSON for machines, with exit codes for CI. Input: a `.3dm` file or a folder. Output: a report on standard output or in a file.

Validity results come from McNeel's openNURBS library (via rhino3dm). They may differ from Rhino's Check command. This tool reports problems; it does not repair models, and it is not a substitute for Check, SelBadObjects, or your own review.

## What it does not do

- It does not repair, modify, or write back to your `.3dm` files. It only reads them.
- It does not claim parity with Rhino's `Check`. Parity has not been tested on a Rhino host.
- It does not run Rhino-only analysis (self-intersections, `MeshRepair`-level diagnostics).
- It does not approve or certify a model. A clean report means no findings for the chosen profile, nothing more.
- No GUI, no telemetry, no network calls.

This is v0.1, an alpha release, not a finished product. v0.1 has been run and tested on Linux only. Windows and macOS should install via `rhino3dm` wheels but are untested. Large (5–10 GB) files are untested.

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

3dm-inspect 0.1.0, rhino3dm 8.35.0. Profile: default. Fail on: error.

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

Every run has `tool` (`3dm-inspect`), `tool_version`, `rhino3dm_version`, `profile`, `fail_on`, `generated_at`, `validation_basis` (`openNURBS via rhino3dm; may differ from Rhino Check`), `summary` (`result` is one of `pass`, `fail`, `report`, `incomplete`; also `exit_code`, file counts, `errors`, `warnings`), and `files`. Each file has `path`, `status` (`pass`, `fail`, or `unreadable`), units and tolerances (raw values plus `*_display` strings in model units and degrees), `summary`, `findings`, and `next_steps` when there is a Rhino command to point to. An unreadable file has a `message` instead of settings. Each finding has `severity` (`error` or `warning`), `rule`, `object_id`, `object_type`, `layer`, and `message`.

Repeated runs on the same files and profile give identical JSON except `generated_at`.

## Options

| Option | Default | Purpose |
|---|---|---|
| `--profile NAME\|FILE` | `default` | Built-in profile (`default`, `strict`) or a `.toml` profile file. |
| `--format md\|json` | `md` | Report format. If omitted, inferred from an `--output` file ending in `.md` or `.json`. If both are given and disagree, exit 2. Never switched automatically by terminal type. |
| `--fail-on error\|warning\|never` | `error` | Which findings make the run exit 1. |
| `--output FILE` | standard output | Write the report to a file. |
| `--quiet` | off | One line per file plus a total (one line for a single file). No finding detail, no footer. With `--format json`, findings are omitted. |
| `--no-color` | color only on a terminal | Plain text. Color is also off when `NO_COLOR` is set or output is not a terminal. Severity is always written as a word. |
| `--help` | | Options, examples, exit codes. |
| `--version` | | Tool and `rhino3dm` versions. |

## Rules (v0.1)

| Profile section | Rule IDs in reports | Default severity | Default profile | Strict profile |
|---|---|---|---|---|
| `validity` | `validity` | error | on | on |
| `document` | `units`, `tolerance_range`, `angle_tolerance_range` | warning | on | on |
| `mesh` | `mesh_not_closed`, `mesh_non_manifold` | warning (error in strict) | off | on |
| `layers` | `layer_name`, `empty_layer`, `object_without_layer`, `object_on_default_layer` | warning | on (default-layer check off) | on (default-layer check on) |

- **validity**: openNURBS `IsValidWithLog` on every object; the openNURBS message is reported unedited, with object ID, type, and layer full path.
- **document**: warns when units are none or unset, or not in `allowed_units`; when absolute tolerance is outside `absolute_tolerance_min`–`absolute_tolerance_max` (default 0.0001–0.01, in model units, following McNeel forum guidance); and when angle tolerance (in degrees) is outside an optional range.
- **mesh**: `Mesh` objects only. "Not closed" uses openNURBS `IsClosed`. "Non-manifold" means an edge shared by more than two faces, counted with vertices merged by identical position (rhino3dm 8.35's `Mesh.IsManifold` reported a single open triangle as non-manifold, so it is not used).
- **layers**: each layer name (not the full path) must match `name_pattern` (empty by default: no naming convention); a layer is empty when neither it nor its sublayers hold objects; objects whose layer index does not resolve to a layer; optionally objects on a layer named in `default_layer_names`.

## Write an office profile

A profile is a TOML file. List only what you change; everything else comes from `extends` (`default` unless you say `strict`). See [examples/office-profile.toml](examples/office-profile.toml):

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

Fixtures are generated with `rhino3dm` by `scripts/make_fixtures.py`; there are no client or third-party models in this repository.

---

Validity is checked with openNURBS (via rhino3dm) and may differ from Rhino's Check command. This report does not repair models and is not a substitute for Check or for your own review.
