# Small tools, explicit evidence

This package explores a limited research-to-practice workflow: define, inspect, measure, report.
The implementation and demonstration inputs are original. No private research code, datasets, papers, visual assets,
or project models are distributed here. The public repository's existing MIT terms apply to these new files.

| Direction | Small tool provided | Boundary |
|---|---|---|
| Semantic assemblies | Strict material/layer records, declared relationships, source IDs, layer schedules | Metadata consistency, not geometric verification |
| Spatial organization | Connected-component counts on a supplied occupancy grid | Connectivity is a measure, not an organization criterion |
| Occupation and access | Shortest-path lengths to supplied destinations | Point agents, no body width or building regulations |
| Vibration and loss | Ideal amplitude/energy decay with a supplied Q | Analytical assumptions, no inferred material properties |
| Reproducible evidence | Source hashes, deterministic plans and evidence labels | Saved file/export state; no unsaved live state |
| Documentation | A material schedule derived only from supplied quantities | No generated drawing or callout is claimed |

## Why these reductions

Large generative experiments depend on parameter schedules, controls and evaluation criteria. A small connectivity tool
can be checked against exact examples without claiming it reproduces a generative study. Likewise, a path calculation
does not establish that a building is accessible or safe. A single-mode decay calculation is useful for inspecting
an assumption; it cannot stand in for a structural or acoustic simulation.

Assembly planning keeps unspecified thickness visible rather than assigning a convenient nominal geometry.
Plan hashes include the normalized specification, schema version and host. They identify plans; they are not native
approval credentials, model revision tokens or authorization to edit a model.

## Platform references

- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk): this alpha pins the 1.x API.
- [McNeel rhino3dm API](https://developer.rhino3d.com/api/rhino3dm/): saved-file inspection, not Rhino application control.
- [MIT damped free oscillations](https://ocw.mit.edu/courses/8-01sc-classical-mechanics-fall-2016/mit8_01scs22_chapter23.pdf): amplitude and energy decay with explicit assumptions.
- [Autodesk Revit units guide](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API/files/Revit_API_Developers_Guide/Introduction/Application_and_Document/Revit_API_Revit_API_Developers_Guide_Introduction_Application_and_Document_Units_html.html): export converts internal lengths to mm.

## Native-host milestone

The optional live tools now demonstrate explicit scratch document binding, stale-revision refusal and a native box lifecycle.
Full assembly edits still need inspectable geometry previews, human authorization and transaction failure recovery.
No assembly commit/rollback is exposed as a placeholder success tool. Native checks are recorded separately from headless tests.
