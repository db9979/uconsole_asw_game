# PyInstaller spec of the macOS program: U-Jagd.app (windowed, one folder in
# a bundle) that starts the game straight away (src/launcher/entry.py).
# Build on a Mac from the repository root:
#   pyinstaller --noconfirm packaging/macos/u-jagd-macos.spec
# The bundle is built for Apple silicon (arm64) only; there is no Intel
# build. It is ad-hoc signed only (no Apple developer certificate).
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
    # The microphone (noise discipline) imports SDL capture only when
    # switched on: name it so the bundle always carries it.
    hiddenimports=collect_submodules("src") + ["main", "pygame._sdl2.audio",
                                               "pygame._sdl2.sdl2", "certifi"],
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
        # Without it macOS refuses (or ends) the app when the microphone
        # of noise discipline opens; with it the system asks the player.
        "NSMicrophoneUsageDescription":
            "Noise discipline: only the loudness of your voice is measured, "
            "nothing is recorded.",
        "NSLocalNetworkUsageDescription":
            "Remote Crew: browsers in your network join the game as crew stations.",
        "NSHumanReadableCopyright": "Copyright © 2026 Dominik Bornhäußer, PolyForm Strict License 1.0.0",
    },
)
