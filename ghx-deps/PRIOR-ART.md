# What exists already, and why this is different (checked 2026-11-15)

| Existing | What it does | Gap left |
|---|---|---|
| Grasshopper **Package Restore** and missing-component placeholders (https://developer.rhino3d.com/en/guides/yak/package-restore-in-grasshopper/) | Finds and installs missing packages when a file is opened | Only inside Grasshopper, one file at a time, at open time |
| **MetaHopper** DocumentInfo, **Pancake** Portability report / Addon manager (McNeel Discourse: https://discourse.mcneel.com/t/python-parse-ghx-files-with-elementtree/48864 , https://discourse.mcneel.com/t/grasshopper-document-list-external-dependencies-installed-plugins-3rd-party-libraries-version-referenced-files/112179) | Lists components, add-ons, and referenced files from inside Grasshopper | Needs Rhino and Grasshopper running. Users report one missing-plug-in dialog per file when batch-scanning folders |
| **GH_IO_Viewer.exe** (ships with Grasshopper) | Manual tree view of any .gh/.ghx archive | Manual; Windows; no report |
| **sonomirco/agents-and-commands** grasshopper-analyzer skill (https://github.com/sonomirco/agents-and-commands) | Analyses a .ghx (workflow graph, scripts, dependencies) to produce a narrative report for an AI agent | One-file analysis report; its SKILL.md describes no allowlist gate, CI exit codes, or folder manifest |
| **gh2ghx** (https://gitlab.com/tsevis/gh2ghx) | Converts .gh to .ghx, with a best-effort report when GH_IO isn't available | A converter, not a dependency manifest |

**What ghx-deps adds:** a dependency-free, headless command that scans a folder of `.ghx` definitions on any OS (scheduled job, file server, CI) and writes a JSON/Markdown manifest of recorded plug-in libraries, components, script components, clusters, and absolute file paths. It can also **fail the build** when a definition needs a library that isn't on an office allowlist. No tool that does this was found in today's searches, though that doesn't prove none exists. The main limitation is that it can't read binary `.gh` (see README).

Sources were read only; nobody was contacted. GH_IO is GPL-licensed and none of its code is used. The XML layout was learned from openly published `.ghx` files, and all fixtures here are synthetic.
