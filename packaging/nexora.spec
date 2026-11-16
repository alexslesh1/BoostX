# PyInstaller spec for the Windows build: one Nexora.exe.
#   pyinstaller packaging/nexora.spec
# Run from the repository root after `pip install . pyinstaller`.
from pathlib import Path

root = Path(SPECPATH).parent
resources = root / "src" / "boostx" / "resources"

a = Analysis(
    [str(root / "packaging" / "nexora_main.py")],
    pathex=[str(root / "src")],
    # AppPaths.resources_dir() looks for them at <_MEIPASS>/resources.
    datas=[(str(resources), "resources")],
    hiddenimports=["PySide6.QtSvg", "PySide6.QtCharts"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="Nexora",
    console=False,
    # UPX-packed executables are flagged by antivirus far more often.
    upx=False,
    # The app itself never needs administrator rights; only the routing
    # engine it starts does, and that asks for them on its own.
    uac_admin=False,
)
