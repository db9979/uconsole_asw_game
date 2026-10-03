# PyInstaller spec of the macOS program: U-Jagd.app (windowed, one folder in
# a bundle) that starts the game straight away (src/launcher/entry.py).
# Build on a Mac from the repository root:
#   pyinstaller --noconfirm packaging/macos/u-jagd-macos.spec
# The bundle is built for the processor of the building Python (arm64 or
# x86_64): pygame and NumPy publish no universal2 wheels. It is ad-hoc
# signed only (no Apple developer certificate).
import os
import re

from PyInstaller.utils.hooks import collect_submodules

root = os.path.abspath(SPECPATH + "/../..")
with open(os.path.join(root, "src", "core", "version.py"), encoding="utf-8") as handle:
    version = re.search(r'^APP_VERSION = "([0-9.]+)"', handle.read(), re.MULTILINE).group(1)

datas = []
for folder, dirs, files in os.walk(os.path.join(root, "data")):
    dirs[:] = sorted(d for d in dirs if d != "__pycache__")
    for name in sorted(files):
        if not name.endswith((".pyc", ".pyo")):
            relative = os.path.relpath(folder, root)
            datas.append((os.path.join(folder, name), relative))

a = Analysis(
    [os.path.join(SPECPATH, "u_jagd_macos.py")],
    pathex=[root],
    datas=datas,
    hiddenimports=collect_submodules("src") + ["main", "certifi"],
    excludes=["pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="U-Jagd",  # update.MAC_EXECUTABLE
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    upx=False,
    strip=False,
    debug=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="U-Jagd", upx=False, strip=False)
app = BUNDLE(
    coll,
    name="U-Jagd.app",  # update.MAC_APP_NAME
    icon=None,
    bundle_identifier="de.ujagd.game",
    version=version,
    info_plist={
        "CFBundleName": "U-Jagd",
        "CFBundleDisplayName": "U-Jagd",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSApplicationCategoryType": "public.app-category.simulation-games",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSLocalNetworkUsageDescription":
            "Remote Crew: browsers in your network join the game as crew stations.",
        "NSHumanReadableCopyright": "MIT License, Dominik Bornhäußer",
    },
)
