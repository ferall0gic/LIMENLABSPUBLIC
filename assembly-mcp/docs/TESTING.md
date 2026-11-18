# Verification

Tested on Windows, Python 3.12.14, MCP SDK 1.30.0 and rhino3dm 8.35.0.
Run the projects separately: their independent suites use some of the same fixture names.

```text
cd assembly-mcp
python -m pytest -q
```

Result: **34 passed**. Evidence includes:

- Synthetic assembly validation and unknown-thickness controls.
- Known-grid connectivity and shortest-path controls, malformed-input refusals.
- Analytical amplitude/energy decay controls and invalid-input refusals.
- A generated synthetic `.3dm`, read without changing its bytes.
- Synthetic Revit snapshots and a fake Revit API for export/unit conversion/exclusive file creation.
- Both server identities exercised through the real MCP SDK's stdio client: initialization, discovery, tool calls,
  strict boolean/integer validation, unavailable-source refusal, and unknown-tool refusal.

Existing public project checks, each from its own project directory:

| Project | Result |
|---|---|
| inspect3dm | 144 passed, 1 skipped |
| 3dm-diff | 17 passed |
| ghx-deps | 15 passed |

No live Rhino or Revit run, real-project model, physical measurement, macOS/Linux run,
Rhino 9 acceptance, building-performance validation or native-edit recovery is claimed.
