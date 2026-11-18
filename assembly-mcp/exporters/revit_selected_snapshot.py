#! python3
"""pyRevit CPython 3 pushbutton script. Read selected elements; write a NEW JSON file.

Native Revit execution is unverified. No document transaction is opened.
Only use with a scratch project until a native acceptance run has been recorded.
"""
import json
from pyrevit import revit, forms
from Autodesk.Revit.DB import UnitUtils, UnitTypeId


def export_selected(doc, selected_ids):
    rows = []
    for identifier in selected_ids:
        element = doc.GetElement(identifier)
        if element is None: raise ValueError("Selected element is no longer available")
        box = element.get_BoundingBox(None)
        def coordinates(point):
            return [UnitUtils.ConvertFromInternalUnits(v, UnitTypeId.Millimeters) for v in (point.X, point.Y, point.Z)]
        element_type = doc.GetElement(element.GetTypeId())
        rows.append({"id": str(element.UniqueId), "name": element.Name or "",
                     "category": element.Category.Name if element.Category else "",
                     "type_name": element_type.Name if element_type else "",
                     "bbox_mm": {"minimum": coordinates(box.Min), "maximum": coordinates(box.Max)} if box else None})
    return {"schema_version": 1, "host": "revit", "units": "mm", "document_label": doc.Title, "elements": rows}


def main():
    ids = list(revit.uidoc.Selection.GetElementIds())
    if not 1 <= len(ids) <= 1000:
        forms.alert("Select 1 to 1,000 elements in a scratch project before exporting.")
        return
    destination = forms.save_file(file_ext="json", default_name="revit-snapshot.json")
    if not destination: return
    snapshot = export_selected(revit.doc, ids)
    # Exclusive creation protects existing exports. No document paths, parameters or user data are exported.
    with open(destination, "x") as target:
        json.dump(snapshot, target, ensure_ascii=True, allow_nan=False, indent=2)
    forms.alert("Selected-element snapshot exported. The Revit document was not changed.")


if __name__ == "__main__": main()
