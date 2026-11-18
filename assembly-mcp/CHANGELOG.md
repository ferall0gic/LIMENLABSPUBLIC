# Changelog

## 0.2.0a1 — 2026-11-18

- Optional live context, object listing, scratch box creation and session-owned deletion (13 tools when configured).
- Fresh scratch directories, explicit process/document/session binding, revision checks and expired-request refusals.
- Local file queues with atomic claims; a timeout never automatically retries native mutations.
- Rhino 8 CPython/UI-thread host and Revit 2025 .NET 8 add-in with ExternalEvent processing.
- Separate-instance startup helper and native acceptance script. No existing user document is adopted.
- Live smoke acceptance passed in separate Rhino 8.35 and Revit 2025.4 processes: box dimensions, stale-revision refusal,
  foreign-ID refusal, deletion back to zero test objects and foreign-document binding refusal.
- Fixed Rhino's soft-deleted-object count after the first native probe exposed it; fixed background Revit polling.

Native evidence is limited to those scratch lifecycle checks. Assembly plans remain data-only.

## 0.1.0a1 — 2026-11-18

- Two independent stdio entry points for the same nine bounded MCP tools.
- Declarative assembly validation, data-only layer plans, schedules and declared-relationship queries.
- Read-only saved `.3dm` inspection and strict Revit JSON snapshot inspection.
- Selected-element pyRevit CPython 3 exporter source; fake-API tests only, native execution unverified.
- Small grid connectivity, grid access and analytical decay measures.
- Explicit evidence labels and limits; no native mutation, arbitrary scripts or network tools.

34 tests cover synthetic data, generated `.3dm` files, a fake Revit exporter API,
and real MCP SDK/client stdio sessions. This is an alpha source release from a checkout.
