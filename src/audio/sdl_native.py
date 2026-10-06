"""The SDL2 library pygame itself runs on, reached through ``ctypes``.

pygame's ``AudioDevice.pause()``/``close()`` call SDL while holding the GIL.
SDL first takes the device's lock, which its audio thread holds while it runs
the Python capture callback, and that callback waits for the GIL: stopping a
capture device mid-block deadlocks the game (the macOS build's self-test hung
there, 1.3.234).  ``ctypes`` releases the GIL around a foreign call, so the
same SDL function called through it lets the running callback finish first.

Only the copy of SDL that pygame already loaded is used (found among the
process's loaded libraries, never loaded from a path of its own): a second
copy would know nothing of pygame's devices.
"""

from __future__ import annotations

import ctypes
import os
import sys

SDL_INIT_AUDIO = 0x10

_UNSET = object()
_library = _UNSET


def _is_sdl(path: str) -> bool:
    """``libSDL2-2.0.so.0``, ``libSDL2-2-1667c208.0.so…`` (wheel), ``SDL2.dll``,
    ``libSDL2-2.0.0.dylib``; never ``SDL2_mixer``/``_ttf``/``_image``."""
    name = os.path.basename(path).lower()
    if name.startswith("lib"):
        name = name[3:]
    return name.startswith("sdl2") and name[4:5] in ("-", ".")


def _loaded_paths() -> list:
    """Paths (Windows: module names) of the SDL2 libraries in this process."""
    if sys.platform == "win32":
        return ["SDL2.dll"]
    if sys.platform == "darwin":
        system = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        system._dyld_image_count.restype = ctypes.c_uint32
        system._dyld_get_image_name.restype = ctypes.c_char_p
        system._dyld_get_image_name.argtypes = [ctypes.c_uint32]
        names = (system._dyld_get_image_name(i) or b""
                 for i in range(system._dyld_image_count()))
        return [n for n in (raw.decode("utf-8", "replace") for raw in names)
                if _is_sdl(n)]
    paths = []
    with open("/proc/self/maps", encoding="utf-8", errors="replace") as maps:
        for line in maps:
            parts = line.split(None, 5)
            path = parts[5].strip() if len(parts) == 6 else ""
            if path.startswith("/") and _is_sdl(path) and path not in paths:
                paths.append(path)
    return paths


def _open(path: str):
    if sys.platform == "win32":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetModuleHandleW.restype = ctypes.c_void_p
        kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        handle = kernel.GetModuleHandleW(path)
        if not handle:
            return None
        return ctypes.CDLL(path, handle=handle)
    # Already loaded: dlopen hands back the same library, not a new copy.
    return ctypes.CDLL(path)


def library():
    """pygame's SDL2 with its audio subsystem running, or None."""
    global _library
    if _library is not _UNSET:
        return _library
    found = None
    try:
        for path in _loaded_paths():
            lib = _open(path)
            if lib is None or not hasattr(lib, "SDL_CloseAudioDevice"):
                continue
            lib.SDL_WasInit.restype = ctypes.c_uint32
            lib.SDL_WasInit.argtypes = [ctypes.c_uint32]
            if not lib.SDL_WasInit(SDL_INIT_AUDIO) & SDL_INIT_AUDIO:
                continue
            lib.SDL_CloseAudioDevice.restype = None
            lib.SDL_CloseAudioDevice.argtypes = [ctypes.c_uint32]
            found = lib
            break
    except Exception:  # noqa: BLE001 - no reachable SDL: the caller falls back
        found = None
    # Only a successful lookup is kept: before SDL's audio runs it is not
    # found yet, and the next stop looks again.
    if found is not None:
        _library = found
    return found


def close_audio_device(device_id: int) -> bool:
    """Close an SDL audio device without holding the GIL; False when pygame's
    SDL cannot be reached (the caller then closes it the pygame way)."""
    lib = library()
    if lib is None or not isinstance(device_id, int) or device_id <= 0:
        return False
    lib.SDL_CloseAudioDevice(device_id)
    return True
