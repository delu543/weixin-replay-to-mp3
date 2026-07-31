from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIBRARY_ROOT = Path(os.environ.get("REPLAY_MP3_LIBRARY", PROJECT_ROOT / "library")).expanduser().resolve()
WORK_ROOT = PROJECT_ROOT / "work"
AUTHORIZED_FETCHERS = PROJECT_ROOT / "outputs" / "authorized_fetchers"
STATIC_ROOT = Path(__file__).resolve().parent / "static"

PLATFORMS = {
    "xiaohongshu": {
        "label": "小红书",
        "folder": "xiaohongshu",
        "accent": "#d9413d",
    },
    "weixin": {
        "label": "视频号",
        "folder": "weixin",
        "accent": "#10a37f",
    },
    "third_party": {
        "label": "第三方网站",
        "folder": "third_party",
        "accent": "#4f46e5",
    },
    "other": {
        "label": "其他",
        "folder": "other",
        "accent": "#64748b",
    },
}


def platform_folder(platform: str) -> Path:
    if platform not in PLATFORMS:
        raise ValueError(f"Unknown platform: {platform}")
    return LIBRARY_ROOT / PLATFORMS[platform]["folder"]


def ensure_layout() -> None:
    LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    for name in PLATFORMS:
        platform_folder(name).mkdir(parents=True, exist_ok=True)
