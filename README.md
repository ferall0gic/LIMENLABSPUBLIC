# LIMEN Labs Public

Open-source research and tools for computational design and architectural software.

## First tool: inspect3dm

[`inspect3dm`](inspect3dm/) is a headless, rule-based inspector for Rhino `.3dm` files. It reads a model or a folder, checks it against a rule profile, and writes a Markdown or JSON report. The Rhino application is not required.

This is **v0.2 / alpha**, not a finished product. New in v0.2: a `revit` profile that flags edges and curves shorter than Revit's short-curve tolerance (about 0.79 mm), geometry beyond Revit's 10-mile and 20-mile distance limits, missing units, and coarse tolerances, before the file goes to Revit. It reads the `.3dm` only and has been tested on synthetic files, not against Revit itself. See [CHANGELOG](inspect3dm/CHANGELOG.md).

- Tested on Linux only. Windows and macOS should install via `rhino3dm` wheels but are untested.
- Large (5–10 GB) files are untested.
- Validity results come from McNeel's openNURBS library (via rhino3dm) and may differ from Rhino's Check command.
- The tool reports problems; it does not repair models, and it is not a substitute for Check.

### Try it

```text
git clone https://github.com/ferall0gic/LIMENLABSPUBLIC.git
cd LIMENLABSPUBLIC
python -m pip install ./inspect3dm
3dm-inspect inspect3dm/samples/sample.3dm
3dm-inspect your-model.3dm --profile revit
```

See the [inspect3dm README](inspect3dm/README.md) for options, exit codes, profiles, and known limits.

### Run the tests

```text
python -m pip install -e "./inspect3dm[test]"
python -m pytest inspect3dm/tests
```

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 Sydney DeVille.

## Feedback

This is an early release. Please [open an issue](https://github.com/ferall0gic/LIMENLABSPUBLIC/issues) if you try the tool — especially if you can test on Windows or macOS, compare results with Rhino's Check command, or compare `--profile revit` findings with what Revit reports on import.
