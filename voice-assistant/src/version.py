"""Installed app version. Keep in sync with the Inno Setup script."""

APP_VERSION = "34.5.12"


def version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for item in str(value or "").strip().split("."):
        digits = "".join(ch for ch in item if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(remote: str, local: str) -> bool:
    left = version_tuple(remote)
    right = version_tuple(local)
    width = max(len(left), len(right))
    left += (0,) * (width - len(left))
    right += (0,) * (width - len(right))
    return left > right


def file_version(value: str) -> str:
    parts = list(version_tuple(value))[:4]
    while len(parts) < 4:
        parts.append(0)
    return ".".join(str(part) for part in parts)
