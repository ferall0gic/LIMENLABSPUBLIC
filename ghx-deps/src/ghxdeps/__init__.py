"""ghxdeps: headless dependency manifest for Grasshopper .ghx definitions.

Installs the ``ghx-deps`` command. Standard library only; Rhino and
Grasshopper are not required, and files are never modified.
"""

__version__ = "0.1.0"
TOOL_NAME = "ghx-deps"

from .manifest import Library, Manifest, read_manifest  # noqa: E402

__all__ = ["__version__", "TOOL_NAME", "Library", "Manifest", "read_manifest"]
