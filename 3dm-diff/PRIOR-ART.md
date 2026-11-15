# What exists already, and why this is different (checked 2026-11-15)

| Existing | What it does | Gap left |
|---|---|---|
| Rhino **Worksession** / Import + **SelDup** (McNeel Discourse, "Comparing files", 2020: https://discourse.mcneel.com/t/comparing-files/109106) | Manual visual comparison inside Rhino | Needs Rhino and a person; no list of changes |
| **RevisionCheck** (Food4Rhino, May 2026: https://discourse.mcneel.com/t/revisioncheck-visual-geometry-comparison-between-revisions/218918) | Rhino plug-in; overlays two revisions and highlights mismatched geometry | Runs inside Rhino (Windows); visual and geometric, not an ID or attribute changelog |
| **Elephant** (dfma.tools: https://dfma.tools/products/elephant/) | Rhino 8 plug-in that writes a JSON change log on every save and can auto-commit to git | Only covers files saved with the plug-in installed; needs Rhino |
| **diffCheck** (EPFL, announced on McNeel Discourse 2024: https://discourse.mcneel.com/t/3d-geometry-comparison-tool/29602) | Compares fabricated or scanned elements with the CAD model | Different problem (as-built vs. design) |
| Speckle versioning | Version history of models streamed through Speckle | Needs the Speckle platform and connectors; it does not diff two arbitrary `.3dm` files |

**What 3dm-diff adds:** a headless command that diffs any two `.3dm` files, including files from people who don't have a plug-in installed. It needs no Rhino licence and runs on Linux, macOS, or Windows. It produces an ID-based change list covering objects, layers, settings, and user text, with exit codes, JSON for CI, and a git textconv mode. No headless open-source tool that does this was found in today's searches, though that doesn't prove none exists.

Sources were read only; nobody was contacted. No code was copied from any of these projects.
