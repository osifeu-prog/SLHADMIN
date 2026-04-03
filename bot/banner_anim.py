from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

BANNER_REL = Path("assets") / "banner.txt"

def _is_banner_asset_path(p: str) -> bool:
    try:
        pp = Path(p).as_posix().lower()
        return pp.endswith("/assets/banner.txt") or pp.endswith("assets/banner.txt") or pp == "assets/banner.txt"
    except Exception:
        return False

def should_animate_banner(asset_path: Optional[str]) -> bool:
    # env switch: set BANNER_ANIM=0 to disable
    if os.getenv("BANNER_ANIM", "1") != "1":
        return False
    if not asset_path:
        return False
    return _is_banner_asset_path(asset_path)

async def send_banner_animated(
    *,
    message,  # telegram.Message
    banner_text: str,
    footer_text: str,
    delay_s: float = 0.05,
    max_frames: int = 60,
) -> None:
    """
    Animate ASCII art left->right using message edits.
    Safe fallback: if edit fails, stop anim and keep last content.
    """
    lines = banner_text.splitlines()
    if not lines:
        await message.reply_text(footer_text)
        return

    width = max((len(l) for l in lines), default=0)
    if width <= 0:
        await message.reply_text(footer_text)
        return

    # limit frames to avoid rate-limits
    step = max(1, width // max_frames)

    # initial placeholder message to edit
    try:
        msg = await message.reply_text("```\\n\\n```\\n" + footer_text, parse_mode="Markdown")
    except Exception:
        return

    for w in range(1, width + 1, step):
        frame_lines = [l[:w] for l in lines]
        frame = "```\\n" + "\\n".join(frame_lines) + "\\n```\\n" + footer_text
        try:
            await msg.edit_text(frame, parse_mode="Markdown")
        except Exception:
            break
        await asyncio.sleep(delay_s)

    final = "```\\n" + "\\n".join(lines) + "\\n```\\n" + footer_text
    try:
        await msg.edit_text(final, parse_mode="Markdown")
    except Exception:
        pass
