# Verification

Tested on Windows, Python 3.12.14, MCP SDK 1.30.0 and rhino3dm 8.35.0.
Run the projects separately: their independent suites use some of the same fixture names.

```text
cd assembly-mcp
python -m pytest -q
```

Result for 0.2.0a1: **63 passed**. Headless evidence includes:

- Synthetic assembly validation and unknown-thickness controls.
- Known-grid connectivity and shortest-path controls, malformed-input refusals.
- Analytical amplitude/energy decay controls and invalid-input refusals.
- A generated synthetic `.3dm`, read without changing its bytes.
- Synthetic Revit snapshots and a fake Revit API for export/unit conversion/exclusive file creation.
- Both server identities exercised through the real MCP SDK's stdio client: initialization, discovery, tool calls,
  strict boolean/integer validation, unavailable-source refusal, and unknown-tool refusal.
- Optional live tool registration/annotations, exact scratch routing and stale-session refusal.
- Emulated-host expiry/revision/foreign-ID refusal and non-replay after response-write failure.
- Rhino soft-deleted object-count regression and fresh scratch-file preparation.

Existing public project checks, each from its own project directory:

| Project | Result |
|---|---|
| inspect3dm | 144 passed, 1 skipped |
| 3dm-diff | 17 passed |
| ghx-deps | 15 passed |

## Live native acceptance — 2026-11-18

Separate Rhino **8.35.26251.13001** and Revit **2025.4** processes, each using a newly created scratch model.
The real MCP stdio client/server and native host adapters passed these six checks per host:

1. Exact scratch session/document context with zero starting test objects.
2. Create a native box and measure its bounds as 100×200×300 mm.
3. Refuse creation with the stale pre-creation revision.
4. Refuse deletion of an object ID not created by the session.
5. Delete the created object and verify zero remaining test objects.
6. Refuse a foreign document binding.

The first development runs exposed Rhino's soft-deleted undo-object count and inactive Revit polling. Those runs failed;
the passing runs followed the count fix and ExternalEvent polling implementation. The Revit host builds against the
installed 2025 API with **0 warnings and 0 errors**. [Sanitized native reports](NATIVE-ACCEPTANCE.json).

No existing user model was opened or adopted. No real-project, physical-performance, macOS/Linux, Rhino 9,
semantic-assembly generation, generalized native-edit recovery or production approval evidence is claimed.
