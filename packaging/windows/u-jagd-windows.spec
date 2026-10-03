# PyInstaller spec of the Windows program: one U-Jagd-Windows.exe that starts
# the game straight away (src/launcher/entry.py).
# Build from the repository root:  pyinstaller packaging/windows/u-jagd-windows.spec
import os

from PyInstaller.utils.hooks import collect_submodules

root = os.path.abspath(SPECPATH + "/../..")
datas = []
for folder, dirs, files in os.walk(os.path.join(root, "data")):
    dirs[:] = sorted(d for d in dirs if d != "__pycache__")
    for name in sorted(files):
        if not name.endswith((".pyc", ".pyo")):
            relative = os.path.relpath(folder, root)
            datas.append((os.path.join(folder, name), relative))

a = Analysis(
    [os.path.join(SPECPATH, "u_jagd_windows.py")],
    pathex=[root],
    datas=datas,
    # The microphone (noise discipline) imports SDL capture only when
    # switched on: name it so the bundle always carries it.
    hiddenimports=collect_submodules("src") + ["main", "pygame._sdl2.audio",
                                               "pygame._sdl2.sdl2", "certifi"],
    excludes=["pytest", "tkinter"],  # no Tk window any more
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="U-Jagd-Windows",
    console=False,
    upx=False,
    strip=False,
    debug=False,
)
