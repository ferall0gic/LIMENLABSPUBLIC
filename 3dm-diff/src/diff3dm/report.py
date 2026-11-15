"""Markdown, JSON and git-textconv output."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import rhino3dm

from . import TOOL_NAME, __version__
from .diff import Diff
from .snapshot import Snapshot

RHINO3DM_VERSION = getattr(rhino3dm, "__version__", "unknown")
NOTE = ("Objects and layers are matched by ID. \"geometry\" means the openNURBS serialization differs; "
        "it does not say how much the shape changed. Read with rhino3dm; files were not modified.")


def num(v: Any) -> str:
    if isinstance(v, float):
        return format(Decimal(repr(round(v, 9))).normalize(), "f")
    return str(v)


def _cell(v: Any) -> str:
    if v is None or v == "":
        return "\u2014"
    return str(v).replace("|", "\\|").replace("\n", " ")


def _short(h: Any) -> Any:
    return h[:12] if isinstance(h, str) and len(h) == 64 else h


def summary_line(d: Diff) -> str:
    c = d.counts()
    if d.is_empty:
        return f"No differences. {c['objects_unchanged']} objects unchanged."
    parts = [f"{c['objects_added']} added", f"{c['objects_removed']} removed", f"{c['objects_changed']} changed"]
    if c["objects_reidentified"]:
        parts.append(f"{c['objects_reidentified']} re-identified")
    parts.append(f"{c['objects_unchanged']} unchanged")
    lay = c["layers_added"] + c["layers_removed"] + c["layers_changed"]
    extra = []
    if lay:
        extra.append(f"{lay} layer change" + ("" if lay == 1 else "s"))
    if c["settings_changed"]:
        extra.append("document settings changed")
    if c["document_text_changed"]:
        extra.append("document text changed")
    return "Objects: " + ", ".join(parts) + "." + (" " + "; ".join(extra).capitalize() + "." if extra else "")


def render_markdown(d: Diff) -> str:
    L = [summary_line(d), "", f"{TOOL_NAME} {__version__}, rhino3dm {RHINO3DM_VERSION}.",
         f"Old: {d.old.path}", f"New: {d.new.path}", ""]
    if d.settings:
        L += ["## Document settings", "", "| Setting | Old | New |", "|---|---|---|"]
        L += [f"| {k} | {_cell(num(a))} | {_cell(num(b))} |" for k, (a, b) in d.settings.items()]
        L.append("")
    if d.document_text:
        L += ["## Document text", "", "| Key | Old | New |", "|---|---|---|"]
        L += [f"| {_cell(k)} | {_cell(a)} | {_cell(b)} |" for k, (a, b) in d.document_text.items()]
        L.append("")
    if d.layers_added or d.layers_removed or d.layers_changed:
        L += ["## Layers", "", "| Change | Layer | Detail |", "|---|---|---|"]
        L += [f"| added | {_cell(x['full_path'])} | \u2014 |" for x in d.layers_added]
        L += [f"| removed | {_cell(x['full_path'])} | \u2014 |" for x in d.layers_removed]
        for x in d.layers_changed:
            det = "; ".join(f"{k}: {v['old']} \u2192 {v['new']}" for k, v in x["changed"].items())
            L.append(f"| changed | {_cell(x['full_path'])} | {_cell(det)} |")
        L.append("")
    if d.objects_added or d.objects_removed or d.objects_changed or d.objects_reidentified:
        L += ["## Objects", "", "| Change | Object ID | Type | Layer | Detail |", "|---|---|---|---|---|"]
        for o in d.objects_added:
            L.append(f"| added | {o.id} | {o.type} | {_cell(o.layer)} | {_cell(o.name)} |")
        for o in d.objects_removed:
            L.append(f"| removed | {o.id} | {o.type} | {_cell(o.layer)} | {_cell(o.name)} |")
        for c in d.objects_changed:
            bits = []
            for k, (a, b) in c.changed.items():
                if k == "geometry":
                    g = "geometry"
                    if c.moved_by is not None:
                        g += f" (bounding-box centre moved {num(c.moved_by)} {d.new.settings['units']}"
                        g += ", size changed)" if c.resized else ", same size)"
                    bits.append(g)
                elif k == "user_text":
                    keys = sorted(set(a) ^ set(b) | {x for x in set(a) & set(b) if a[x] != b[x]})
                    bits.append("user text " + ", ".join(
                        f"{k}: {a.get(k, '(none)')} \u2192 {b.get(k, '(none)')}" for k in keys))
                else:
                    bits.append(f"{k}: {_cell(a)} \u2192 {_cell(b)}")
            L.append(f"| changed | {c.id} | {c.type} | {_cell(c.layer)} | {_cell('; '.join(bits))} |")
        for a, b in d.objects_reidentified:
            L.append(f"| re-identified | {b.id} | {b.type} | {_cell(b.layer)} | same geometry; old ID {a.id} |")
        L.append("")
    L += ["---", "", NOTE, ""]
    return "\n".join(L)


def render_json(d: Diff) -> str:
    def obj(o):
        return {"id": o.id, "type": o.type, "layer": o.layer, "name": o.name,
                "user_text": dict(o.user_text), "geometry_hash": o.geometry_hash}
    doc = {
        "tool": TOOL_NAME, "tool_version": __version__, "rhino3dm_version": RHINO3DM_VERSION,
        "old": d.old.path, "new": d.new.path, "identical": d.is_empty, "summary": d.counts(),
        "settings": {k: {"old": a, "new": b} for k, (a, b) in d.settings.items()},
        "document_text": {k: {"old": a, "new": b} for k, (a, b) in d.document_text.items()},
        "layers": {"added": d.layers_added, "removed": d.layers_removed, "changed": d.layers_changed},
        "objects": {
            "added": [obj(o) for o in d.objects_added],
            "removed": [obj(o) for o in d.objects_removed],
            "changed": [c.to_dict() for c in d.objects_changed],
            "reidentified": [{"old_id": a.id, "new_id": b.id, "type": b.type, "layer": b.layer}
                             for a, b in d.objects_reidentified],
        },
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def render_textconv(s: Snapshot) -> str:
    """Stable, line-per-record text for `git diff` (git textconv driver)."""
    L = [f"units: {s.settings['units']}",
         f"absolute_tolerance: {num(s.settings['absolute_tolerance'])}",
         f"angle_tolerance_degrees: {num(s.settings['angle_tolerance_degrees'])}"]
    for k in sorted(s.document_text):
        L.append(f"text {k} = {s.document_text[k]}")
    for lay in sorted(s.layers.values(), key=lambda x: (x.full_path, x.id)):
        flags = ("" if lay.visible else " hidden") + (" locked" if lay.locked else "")
        L.append(f"layer {lay.full_path} color={','.join(map(str, lay.color))}{flags} id={lay.id}")
    for o in sorted(s.objects.values(), key=lambda x: (x.layer or "", x.type, x.id)):
        ut = "".join(f" {k}={v}" for k, v in o.user_text)
        nm = f" name={o.name}" if o.name else ""
        L.append(f"object {o.layer or '-'} {o.type} {o.id} geom={_short(o.geometry_hash)}{nm}{ut}")
    return "\n".join(L) + "\n"
