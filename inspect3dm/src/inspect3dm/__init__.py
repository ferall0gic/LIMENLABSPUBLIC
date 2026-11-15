"""inspect3dm: headless, rule-based inspector for Rhino .3dm files.

Installs the ``3dm-inspect`` command. Validity is checked with openNURBS
(via rhino3dm) and may differ from Rhino's Check command.
"""

__version__ = "0.2.0"
TOOL_NAME = "3dm-inspect"
VALIDATION_BASIS = "openNURBS via rhino3dm; may differ from Rhino Check"

from .inspector import FileResult, Finding, RunResult, inspect_file, inspect_paths  # noqa: E402
from .profile import Profile, ProfileError, load_profile  # noqa: E402

__all__ = [
    "__version__", "TOOL_NAME", "VALIDATION_BASIS",
    "Finding", "FileResult", "RunResult", "inspect_file", "inspect_paths",
    "Profile", "ProfileError", "load_profile",
]
