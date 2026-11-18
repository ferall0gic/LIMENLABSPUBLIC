"""Windows-only launcher: NEW Rhino/Revit process and NEW scratch document every time."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from xml.sax.saxutils import escape
from limen_assembly_mcp.live import create_scratch_session


def prepare_rhino(root, host_script):
    import rhino3dm
    model = rhino3dm.File3dm(); model.Settings.ModelUnitSystem = rhino3dm.UnitSystem.Millimeters
    scratch = root / "scratch.3dm"
    if scratch.exists() or not model.Write(str(scratch), 8): raise ValueError("Could not create a new scratch file")
    bootstrap = ("#! python 3\nfrom pathlib import Path\nimport traceback\ntry:\n"
        "    exec(compile(Path(" + repr(str(host_script)) + ").read_text(encoding='utf-8'), " + repr(str(host_script)) + ", 'exec'), globals())\n"
        "    print(start(" + repr(str(root)) + "))\nexcept Exception:\n"
        "    Path(" + repr(str(root / "startup-error.txt")) + ").write_text(traceback.format_exc(), encoding='utf-8')\n")
    with (root / "bootstrap.py").open("x", encoding="utf-8") as target: target.write(bootstrap)


def revit_manifest(assembly):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<RevitAddIns><AddIn Type="Application">'
        '<Name>LIMEN Labs Public Scratch</Name><Assembly>' + escape(str(assembly)) + '</Assembly>'
        '<AddInId>31A5D7D5-7521-41B3-A6B6-0F221A5A6731</AddInId>'
        '<FullClassName>LimenLabs.Scratch.Revit.ScratchApplication</FullClassName><VendorId>LMNL</VendorId>'
        '<VendorDescription>LIMEN Labs scratch-only development host</VendorDescription></AddIn></RevitAddIns>\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", choices=("rhino", "revit")); parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--executable", type=Path); parser.add_argument("--revit-assembly", type=Path)
    args = parser.parse_args()
    if os.name != "nt": parser.error("Native launcher currently supports Windows only")
    checkout = Path(__file__).resolve().parents[1]
    executable = args.executable or Path("C:/Program Files/Rhino 8/System/Rhino.exe" if args.host == "rhino" else "C:/Program Files/Autodesk/Revit 2025/Revit.exe")
    if not executable.is_file(): parser.error("Host executable not found")
    env = dict(os.environ)
    if args.host == "revit":
        assembly = (args.revit_assembly or checkout / "hosts/revit/bin/Release/net8.0-windows/LimenLabs.Scratch.Revit.dll").resolve()
        if not assembly.is_file(): parser.error("Build the Revit host first, or supply --revit-assembly")
        manifest = Path(env["APPDATA"]) / "Autodesk/Revit/Addins/2025/LIMENLabsPublicScratch.addin"
        text = revit_manifest(assembly)
        if manifest.exists() and manifest.read_text(encoding="utf-8") != text:
            parser.error("The dedicated scratch add-in registration already exists with different contents; it was not modified")
        manifest.parent.mkdir(parents=True, exist_ok=True)
        if not manifest.exists():
            with manifest.open("x", encoding="utf-8") as target: target.write(text)
    root = create_scratch_session(args.root, args.host)
    if args.host == "rhino":
        prepare_rhino(root, checkout / "hosts/rhino_scratch.py")
        command = [str(executable), str(root / "scratch.3dm"), "/nosplash", '/runscript=_-ScriptEditor _R "' + str(root / "bootstrap.py") + '"']
    else:
        env["LIMEN_REVIT_SCRATCH_ROOT"] = str(root)
        command = [str(executable), "/nosplash", "/language", "ENU"]
    startup = subprocess.STARTUPINFO(); startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startup.wShowWindow = subprocess.SW_HIDE
    process = subprocess.Popen(command, env=env, startupinfo=startup)
    (root / "launched-process.json").write_text(json.dumps({"host": args.host, "process_id": process.pid}), encoding="utf-8")
    print(json.dumps({"host": args.host, "session_directory": str(root), "process_id": process.pid}, indent=2))


if __name__ == "__main__": main()
