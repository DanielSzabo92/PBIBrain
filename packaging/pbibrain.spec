# Windows x64 portable distribution.  One Analysis/one _internal directory is
# deliberately shared by the GUI and agent executables.
from pathlib import Path

from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT

ROOT = Path(SPECPATH).parent.resolve()

a = Analysis(
    [str(ROOT / "packaging" / "desktop_entry.py"), str(ROOT / "backend" / "agent.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "frontend" / "dist"), "frontend/dist"),
        (str(ROOT / "runtime" / "native"), "runtime/native"),
        (str(ROOT / "runtime" / "licenses"), "licenses"),
    ],
    hiddenimports=[
        "webview.platforms.edgechromium",
        "clr",
        "pythonnet",
        "ladybug._lbug_capi",
        "backend.mcp_server",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "PySide6", "tkinter", "numpy", "pandas", "torch"],
    noarchive=False,
)

pyz = PYZ(a.pure)
gui_script = next(item for item in a.scripts if item[0] == "desktop_entry")
agent_script = next(item for item in a.scripts if item[0] == "agent")
runtime_scripts = [item for item in a.scripts if item[0] not in {"desktop_entry", "agent"}]

gui = EXE(
    pyz,
    [*runtime_scripts, gui_script],
    [],
    exclude_binaries=True,
    name="PBIBrain",
    console=False,
    icon=str(ROOT / "branding" / "pbibrain.ico"),
    disable_windowed_traceback=False,
    manifest=str(ROOT / "packaging" / "windows.manifest"),
)

agent = EXE(
    pyz,
    [*runtime_scripts, agent_script],
    [],
    exclude_binaries=True,
    name="PBIBrain-Agent",
    console=True,
    manifest=str(ROOT / "packaging" / "windows.manifest"),
)

coll = COLLECT(
    gui,
    agent,
    a.binaries,
    a.datas,
    a.zipfiles,
    name="PBIBrain",
)
