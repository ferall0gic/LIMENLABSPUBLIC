# Changelog

## 0.1.0 (2026-11-15)

- First public release: a dependency manifest for Grasshopper `.ghx` files listing recorded plug-in libraries, components, script components, clusters, and absolute file paths. It produces Markdown and JSON, and an allowlist can fail a CI build.
- Reads `.ghx` (XML) only; binary `.gh` is not supported. Tested on synthetic `.ghx` files on Linux only.
