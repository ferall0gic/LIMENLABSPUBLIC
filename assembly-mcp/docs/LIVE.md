# Separate-instance live scratch tools

Windows alpha: Rhino 8 CPython and Revit 2025/.NET 8. Existing user documents are never adopted.
The launcher makes a unique session directory and a new empty scratch model for each run.
Do not run the host scripts manually against your working models.

## Start a scratch host

From a checkout with the package installed:

```text
python assembly-mcp/scripts/start_scratch.py rhino --root C:/scratch/limen-mcp
```

For Revit, build the development add-in first using your local Autodesk API assemblies:

```text
dotnet build assembly-mcp/hosts/revit/LimenLabs.Scratch.Revit.csproj -c Release
python assembly-mcp/scripts/start_scratch.py revit --root C:/scratch/limen-mcp
```

The default installation paths are Rhino 8 and Revit 2025. `--executable` accepts a different installed executable.
`--revit-assembly` accepts the built scratch add-in DLL. The project property `RevitApiDir` controls the API reference location.
Autodesk and McNeel binaries are not distributed in this repository.

Revit startup registers **only** `LIMENLabsPublicScratch.addin` in the current user's Revit 2025 add-in directory.
It refuses to overwrite an existing registration with different contents. Other add-in registrations are not changed.
The add-in does nothing unless its process inherits `LIMEN_REVIT_SCRATCH_ROOT` from this launcher.
It creates and saves a new background scratch project; it does not open or close an existing project.
Application licensing, authentication and unrelated startup dialogs may require user interaction.

Rhino opens the launcher's newly generated empty `scratch.3dm` in a new process and runs a CPython bootstrap.
The host refuses startup unless the active file is exactly that session's scratch file and contains no objects.

The launcher prints the session directory and process ID. Wait for `session.json` with a fresh heartbeat.
Bind the matching server with one environment variable:

```json
{
  "mcpServers": {
    "limen-rhino-live": {
      "command": "limen-rhino-mcp",
      "env": {"LIMEN_RHINO_LIVE_SESSION": "C:/scratch/limen-mcp/rhino-<session>"}
    },
    "limen-revit-live": {
      "command": "limen-revit-mcp",
      "env": {"LIMEN_REVIT_LIVE_SESSION": "C:/scratch/limen-mcp/revit-<session>"}
    }
  }
}
```

No live configuration means the existing nine offline tools remain the entire tool surface.

## Four live tools

| Tool | Behavior |
|---|---|
| `live_context` | Current session/process/document identity, revision and scratch object count |
| `live_list_objects` | Up to 200 live object/DirectShape records and native bounds |
| `live_create_scratch_box` | One native box from `origin_mm`, positive `size_mm`, and the current `expected_revision` |
| `live_delete_scratch_objects` | Exactly one ID created by this same session, with the current revision |

Dimensions are limited to 10,000 mm; origin coordinates to ±100,000 mm; 500 active test objects maximum.
Revit boxes are Generic Model DirectShapes, not parametric Wall/Floor/Roof elements.
Rhino revisions fingerprint active geometry and attributes; Revit revisions use a session-local change counter.
These are scratch-operation guards, not a general model-content or production approval policy.
Native mutations execute on the host API/UI thread. Revit uses native transactions.
Rhino groups the individual operations in undo records, but no programmatic rollback tool is exposed.

## Transport and failure behavior

The transport uses local request/response files, not a network listener. Each request contains its binding, a unique ID,
expiry and (for mutations) the observed revision. The host atomically claims a request before executing it.
Claimed requests are never replayed, including when response writing fails. No timeout automatically retries a mutation.
After a timeout, inspect the scratch host and its fresh context before deciding what to do next.

Session binding prevents accidental cross-instance/document routing. It is not a security boundary against another local
process that already has permission to change the session files. Keep the directory local to the intended user.
Switching the active document or changing the scratch file path causes refusal. No arbitrary script, file-open, save-as,
shell, general deletion, existing-object edit, assembly commit or assembly rollback tool is exposed.

## Reproduce native acceptance

Use a fresh session; the test requires zero starting test objects:

```text
python assembly-mcp/scripts/native_acceptance.py --host rhino --session <session-directory> --report rhino-result.json
python assembly-mcp/scripts/native_acceptance.py --host revit --session <session-directory> --report revit-result.json
```

It drives the real MCP stdio server, creates/measures/deletes one box and checks stale-revision, foreign-ID and
foreign-document refusals. The report is created exclusively; an existing report is not overwritten.
The first live development probe found Rhino's undo-deleted object count and inactive Revit polling; both were corrected
before the passing acceptance runs. See [TESTING.md](TESTING.md) for the verified scope.

After testing, close only the separate scratch process. The startup output records its PID. The dedicated
`LIMENLabsPublicScratch.addin` registration may be removed after all scratch Revit instances have closed; leave other add-ins alone.
