"""Shared helper for small, bounded, symlink-safe opt-in diagnostic logs.

Used by ``AudioEngine.debug_log`` (``U_JAGD_AUDIO_DEBUG``) and ``Game``'s
perf-debug hook (``U_JAGD_PERF_DEBUG``): both are opt-in via an environment
variable, write a bounded log file under ``config.SAVE_DIR``, and must never
follow a symlinked root directory or log file, matching this project's
general rule against writing through a symlinked destination.
"""

import os


def append_bounded_log(root, filename: str, line: str, max_bytes: int) -> None:
    """Append ``line`` to ``<root>/<filename>``, truncating first past ``max_bytes``.

    Silently does nothing on any ``OSError``, or if ``root``/the log file is
    (or would be reached through) a symlink. Single-writer diagnostics only;
    not safe for concurrent writers across processes.
    """
    try:
        root = os.path.abspath(os.path.expanduser(os.fspath(root)))
        if os.path.lexists(root) and os.path.islink(root):
            return
        os.makedirs(root, mode=0o700, exist_ok=True)
        if os.path.islink(root) or not os.path.isdir(root):
            return
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_flags |= getattr(os, "O_NOFOLLOW", 0)
        directory = os.open(root, directory_flags)
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(filename, flags, 0o600, dir_fd=directory)
            with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                if os.fstat(handle.fileno()).st_size >= max_bytes:
                    handle.seek(0)
                    handle.truncate()
                handle.write(line)
        finally:
            os.close(directory)
    except OSError:
        pass
