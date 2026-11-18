# Assembly MCP tools — 0.1 alpha

Small architectural assembly, model inspection and spatial-analysis tools for MCP clients.
Two stdio servers share the same nine tools: `limen-rhino-mcp` and `limen-revit-mcp`.

**Rhino reads saved `.3dm` files. Revit reads a JSON snapshot exported from Revit. Neither server controls a running application.**
Assembly previews are inspectable data plans. They do not create native geometry, commit a change, or promise rollback.
This first milestone is deliberately smaller than a modeling engine.

## Install from this checkout

Requires Python 3.11+. Uses the official MCP Python SDK 1.x and rhino3dm 8.x.

```text
python -m pip install -e "./assembly-mcp[test]"
python -m pytest assembly-mcp/tests
```

Add the following to a client that supports MCP stdio. Replace the example paths with files you explicitly intend the client to read.
For an isolated Python environment, use the absolute path to its installed executable as `command`.

```json
{
  "mcpServers": {
    "limen-rhino": {
      "command": "limen-rhino-mcp",
      "env": {"LIMEN_RHINO_MODEL": "/absolute/path/to/scratch.3dm"}
    },
    "limen-revit": {
      "command": "limen-revit-mcp",
      "env": {"LIMEN_REVIT_SNAPSHOT": "/absolute/path/to/revit-snapshot.json"}
    }
  }
}
```

Source binding happens at server startup. Tools cannot choose another path, run scripts, make network requests, or save models.
If no source is bound, the planning and analysis tools still work; inspection/source checks return an error.
Restart to bind another file. Inspection re-reads the file and returns its SHA-256: a changed saved file/export has a new hash.
It cannot detect unsaved edits in the host application. Model/export contents are transmitted to the MCP client when inspected;
bind only files you are authorized to share with that client.

## Tools

| Tool | Input and result |
|---|---|
| `assembly_validate` | Strict assembly schema, unique IDs, relationship references, explicit unknown thicknesses |
| `assembly_preview` | Ordered layer offsets, known vs unknown thickness, deterministic host-specific plan hash; **plan only** |
| `assembly_layer_schedule` | Material/role schedule; volume only when the caller supplies both area and thickness |
| `assembly_query_relationships` | Declared edges touching an assembly; no inferred support or physical continuity |
| `model_inspect` | Paged metadata from a bound `.3dm` or Revit snapshot; 200 objects per page maximum |
| `assembly_check_sources` | Referenced object IDs present/missing in the bound source |
| `spatial_connectivity` | Four-neighbour components of a binary occupancy grid |
| `spatial_access` | Four-neighbour shortest paths in a binary walkable grid, points in `[x,y]` order |
| `analytical_decay` | Ideal amplitude and energy retention for supplied frequency, Q and elapsed seconds |

See [examples/wall.json](examples/wall.json) for an assembly specification and
[docs/RESEARCH-TO-TOOLS.md](docs/RESEARCH-TO-TOOLS.md) for the scale and evidence boundaries.
Unknown membrane thickness stays `null`; no nominal thickness or material property is invented.
All layer positions after an unknown thickness are also unknown.

## Revit snapshot workflow

1. In a **scratch Revit project**, select up to 1,000 elements.
2. Run [exporters/revit_selected_snapshot.py](exporters/revit_selected_snapshot.py) from a pyRevit **CPython 3** pushbutton (not IronPython 2).
3. Pick a new JSON filename. The exporter writes selected names, category/type names and axis-aligned bounds in mm.
   It opens no Revit transaction, edits no element, and refuses to overwrite a file.
4. Bind that JSON with `LIMEN_REVIT_SNAPSHOT`, then call `model_inspect`.

The exporter source is supplied for review and **has not been run inside Revit**.
The included [synthetic snapshot](examples/revit-snapshot.json) is a hand-authored contract fixture, not evidence of a native export.

## Limits and evidence

- Tests use synthetic `.3dm` files, synthetic Revit snapshots, mathematical controls, and the real MCP stdio client/server.
  No live Rhino/Revit acceptance or physical testing is claimed.
- No native `.rvt` reader. No Revit add-in installation, ExternalEvent execution, live document binding, or native transactions.
- No geometry construction, joins, boolean openings, sections, drawings, sheet composition, PDFs, commit or rollback tools yet.
- Connectivity is not architectural organization. Grid access is not circulation adequacy, accessibility or fire egress.
- The decay model is `amplitude=exp(-pi*f*t/Q)`, `energy=amplitude^2`. Q is an assumption supplied by the caller.
  No floor, joint, support, thermal, acoustic or structural performance is established.
- Source limits: 256 MiB `.3dm`, 16 MiB JSON, 10,000 objects. Grid limits: 128×128, 128 destinations.
- rhino3dm 9.x/pre-release compatibility is untested and intentionally outside the dependency range.

MIT, following the repository's existing license. [LICENSE](LICENSE).
