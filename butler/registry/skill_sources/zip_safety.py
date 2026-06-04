"""Zip safety helpers for skill source adapters (Sprint 20-2 SEC-20-A-2).

When extracting community-published skill bundles (lobehub / clawhub), we
must reject zip entries that are not plain regular files. The standard
`zipfile.ZipInfo` API in Python < 3.12 lacks `is_symlink()` and friends,
so we decode the Unix mode bits from `external_attr` ourselves.

`create_system == 3` indicates a Unix-created zip whose upper 16 bits of
`external_attr` carry the file mode. Default Python `ZipFile.writestr`
zips are MS-DOS / FAT (`create_system == 0`, mode == 0) — those are
treated as regular files because there's no special-type signal.

Special file types rejected (any of these bits set in the upper 16):

  - S_IFLNK  (0o120000) — symlink (target path is "data" — leaks /etc/passwd
                            path strings into the bundle)
  - S_IFCHR  (0o020000) — character device
  - S_IFBLK  (0o060000) — block device
  - S_IFIFO  (0o010000) — named pipe
  - S_IFSOCK (0o140000) — unix domain socket
  - S_IFDIR  (0o040000) — directory (defense in depth; `is_dir()` already
                            filters most cases via filename suffix)
"""

from __future__ import annotations

import stat
import zipfile


def is_unsafe_zip_entry(info: zipfile.ZipInfo) -> bool:
    """True if *info* is a symlink, special file, or non-regular Unix entry."""
    if info.create_system != 3:
        return False
    mode = info.external_attr >> 16
    if mode == 0:
        return False
    return bool(
        stat.S_ISLNK(mode)
        or stat.S_ISDIR(mode)
        or stat.S_ISCHR(mode)
        or stat.S_ISBLK(mode)
        or stat.S_ISFIFO(mode)
        or stat.S_ISSOCK(mode)
    )
