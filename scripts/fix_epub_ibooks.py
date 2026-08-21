#!/usr/bin/env python3
"""Patch Apple Books display options so themes work on iOS dark mode."""

from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

DISPLAY_OPTIONS = "META-INF/com.apple.ibooks.display-options.xml"
PATCHED = b"""<?xml version="1.0" encoding="UTF-8"?>
<display_options>
  <platform name="*">
    <option name="specified-fonts">false</option>
  </platform>
</display_options>
"""


def copy_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    copied = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
    copied.compress_type = info.compress_type
    copied.external_attr = info.external_attr
    copied.internal_attr = info.internal_attr
    copied.create_system = info.create_system
    copied.comment = info.comment
    copied.extra = info.extra
    return copied


def patch_epub(path: Path) -> None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp:
        tmp_path = Path(tmp.name)

    try:
        with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(
            tmp_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as target:
            names = set(source.namelist())
            for info in source.infolist():
                data = PATCHED if info.filename == DISPLAY_OPTIONS else source.read(info)
                copied = copy_info(info)
                if info.filename == "mimetype":
                    copied.compress_type = zipfile.ZIP_STORED
                target.writestr(copied, data)

            if DISPLAY_OPTIONS not in names:
                target.writestr(DISPLAY_OPTIONS, PATCHED)

        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <file.epub>", file=sys.stderr)
        return 1
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"error: {path} not found", file=sys.stderr)
        return 1
    patch_epub(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
