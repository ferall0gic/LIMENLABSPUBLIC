"""Write synthetic .ghx definitions for the tests.

The element layout (Archive > Definition > GHALibraries / DefinitionObjects,
typed <item> values) follows the public GHX format as seen in openly published
.ghx files; every name, GUID and value written here is made up for the tests.
Run:  python scripts/make_fixtures.py <output-folder>
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

HEADER = """<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<Archive name="Root">
  <!--Synthetic test archive written by ghx-deps scripts/make_fixtures.py-->
  <items count="1">
    <item name="ArchiveVersion" type_name="gh_version" type_code="80">
      <Major>0</Major><Minor>2</Minor><Revision>2</Revision>
    </item>
  </items>
  <chunks count="1">
    <chunk name="Definition">
      <items count="1">
        <item name="plugin_version" type_name="gh_version" type_code="80">
          <Major>1</Major><Minor>0</Minor><Revision>{gh_rev}</Revision>
        </item>
      </items>
      <chunks count="2">
"""
FOOTER = """      </chunks>
    </chunk>
  </chunks>
</Archive>
"""


def _s(name, value, code=10, tname="gh_string"):
    return f'<item name="{name}" type_name="{tname}" type_code="{code}">{escape(value)}</item>'


def _library(i, name, version, asm_version, author, lid):
    full = f"{name}, Version={asm_version}, Culture=neutral, PublicKeyToken=null"
    return f"""<chunk name="Library" index="{i}"><items count="6">
      {_s("AssemblyFullName", full)}{_s("AssemblyVersion", asm_version)}{_s("Author", author)}
      {_s("Id", lid, 9, "gh_guid")}{_s("Name", name)}{_s("Version", version)}
    </items></chunk>"""


def _object(i, name, guid, extra_strings=()):
    extras = "".join(_s(k, v) for k, v in extra_strings)
    return f"""<chunk name="Object" index="{i}">
      <items count="2">{_s("GUID", guid, 9, "gh_guid")}{_s("Name", name)}</items>
      <chunks count="1"><chunk name="Container"><items count="{2 + len(extra_strings)}">
        {_s("InstanceGuid", f"00000000-0000-4000-8000-{i:012d}", 9, "gh_guid")}{_s("Name", name)}{extras}
      </items></chunk></chunks>
    </chunk>"""


def ghx(libraries, objects, gh_rev=7) -> str:
    libs = "".join(_library(i, *lib) for i, lib in enumerate(libraries))
    objs = "".join(_object(i, *o) for i, o in enumerate(objects))
    return (HEADER.format(gh_rev=gh_rev)
            + f"""<chunk name="GHALibraries"><items count="1">{_s("Count", str(len(libraries)), 3, "gh_int32")}</items>
            <chunks count="{len(libraries)}">{libs}</chunks></chunk>
            <chunk name="DefinitionObjects"><items count="1">{_s("ObjectCount", str(len(objects)), 3, "gh_int32")}</items>
            <chunks count="{len(objects)}">{objs}</chunks></chunk>
"""
            + FOOTER)


SLIDER = ("Number Slider", "aaaaaaaa-0000-4000-8000-000000000001")
BOX = ("Box", "aaaaaaaa-0000-4000-8000-000000000002")
SCRIPT = ("C# Script", "aaaaaaaa-0000-4000-8000-000000000003")
CLUSTER = ("Cluster", "aaaaaaaa-0000-4000-8000-000000000004")
PANEL_WITH_PATH = ("Read File", "aaaaaaaa-0000-4000-8000-000000000005",
                   (("Path", r"C:\Projects\Tower\site_survey.csv"),))
PANEL_REL = ("Panel", "aaaaaaaa-0000-4000-8000-000000000006", (("UserText", "notes.txt"),))
MESHKIT = ("MeshKit", "2.1.0", "2.1.0.0", "Example Author", "bbbbbbbb-0000-4000-8000-000000000001")
SOLARLAB = ("SolarLab", "", "0.9.3.0", "", "bbbbbbbb-0000-4000-8000-000000000002")

FIXTURES = {
    "core_only.ghx": lambda: ghx([], [SLIDER, SLIDER, BOX]),
    "two_plugins.ghx": lambda: ghx([MESHKIT, SOLARLAB],
                                   [SLIDER, ("Kit Smooth", "cccccccc-0000-4000-8000-000000000001"),
                                    ("Sun Path", "cccccccc-0000-4000-8000-000000000002"), BOX]),
    "scripts_clusters_paths.ghx": lambda: ghx([MESHKIT], [SCRIPT, SCRIPT, CLUSTER, PANEL_WITH_PATH, PANEL_REL]),
}


def build_all(outdir) -> dict[str, Path]:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, fn in FIXTURES.items():
        p = outdir / name
        p.write_text(fn(), encoding="utf-8")
        out[name] = p
    (outdir / "not_xml.ghx").write_text("this is not xml <", encoding="utf-8")
    (outdir / "other_xml.ghx").write_text("<?xml version='1.0'?><svg/>", encoding="utf-8")
    (outdir / "binary.gh").write_bytes(b"\x78\x9c\x00\x01binary")
    out.update({k: outdir / k for k in ("not_xml.ghx", "other_xml.ghx", "binary.gh")})
    return out


if __name__ == "__main__":
    for p in build_all(sys.argv[1] if len(sys.argv) > 1 else "fixtures-out").values():
        print(p)
