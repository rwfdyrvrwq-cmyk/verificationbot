#!/usr/bin/env python3
"""
swf2png_client.py
-----------------

Utility for rendering AQW characters without the CharPage UI by talking to the
`swf2png` TCP service (https://github.com/anthony-hyo/swf2png).

Workflow:
1. Fetch the official CharPage and extract all FlashVars.
2. Convert FlashVars into the payload shape expected by the swf2png service.
3. Send the payload over TCP, receive a Base64-encoded PNG, and save it.

This script can be used standalone:

    python swf2png_client.py Yenne -o renders/yen.png

or imported from other modules:

    client = SWF2PNGClient()
    png_bytes = await client.render_character("Yenne")
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qsl, quote_plus, unquote

import httpx

try:
    from PIL import Image  # type: ignore
except ImportError:  # pragma: no cover - Pillow is already in requirements.txt
    Image = None  # type: ignore


CHARPAGE_URL = "https://account.aq.com/CharPage?id={name}"
ASSET_BASE_URL = "https://game.aq.com/game/gamefiles/"
SWF_SOURCE = f"{ASSET_BASE_URL}etc/chardetail/characterB.swf?v=2"

FLASHVARS_PATTERNS = [
    re.compile(r'flashvars="([^"]+)"', re.IGNORECASE),
    re.compile(r'<param[^>]+name="FlashVars"[^>]+value="([^"]+)"', re.IGNORECASE),
]


def _normalize_flashvars(raw: str) -> Dict[str, str]:
    """Convert the FlashVars string into a simple dict."""
    decoded = unquote(raw.replace("&amp;", "&"))
    pairs = parse_qsl(decoded, keep_blank_values=True)
    flashvars: Dict[str, str] = {}
    for key, value in pairs:
        flashvars[key] = value
    return flashvars


async def fetch_flashvars(character: str, timeout: float = 20.0) -> Dict[str, str]:
    """Download the CharPage HTML and extract FlashVars."""
    url = CHARPAGE_URL.format(name=quote_plus(character))
    headers = {
        "User-Agent":
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36"
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, headers=headers, follow_redirects=True)
        response.raise_for_status()
        html = response.text

    for pattern in FLASHVARS_PATTERNS:
        match = pattern.search(html)
        if match:
            return _normalize_flashvars(match.group(1))

    if "is wandering in the Void" in html:
        raise ValueError("Character is inactive or does not exist.")
    raise ValueError("Unable to locate FlashVars on the CharPage.")


def _int(flashvars: Dict[str, str], key: str, default: int = 0) -> int:
    value = flashvars.get(key)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _equipment_slot(
    flashvars: Dict[str, str],
    file_key: str,
    link_key: str,
    name_key: Optional[str] = None,
    *,
    fallback_file: str = "none",
    fallback_link: str = "",
    fallback_name: str = "",
) -> Dict[str, str]:
    return {
        "File": flashvars.get(file_key, fallback_file),
        "Link": flashvars.get(link_key, fallback_link),
        "Name": flashvars.get(name_key, fallback_name) if name_key else "",
    }


def build_payload(
    flashvars: Dict[str, str],
    *,
    use_cosmetics: bool = False,
    url: str = ASSET_BASE_URL,
) -> Dict[str, Any]:
    """Construct a swf2png payload from FlashVars."""

    def pick(primary: Tuple[str, str, str],
             cosmetic: Tuple[str, str, str]) -> Dict[str, str]:
        file_key, link_key, name_key = primary
        cos_file, cos_link, cos_name = cosmetic
        if use_cosmetics and flashvars.get(cos_file, "none") not in ("", "none"):
            return _equipment_slot(flashvars, cos_file, cos_link, cos_name)
        return _equipment_slot(flashvars, file_key, link_key, name_key)

    equipment = {
        "en": {
            "File": flashvars.get("strEntityFile", "none"),
            "Link": flashvars.get("strEntityLink", ""),
        },
        "co": pick(
            ("strClassFile", "strClassLink", "strClassName"),
            ("strCustArmorFile", "strCustArmorLink", "strCustArmorName")),
        "he": pick(
            ("strHelmFile", "strHelmLink", "strHelmName"),
            ("strCustHelmFile", "strCustHelmLink", "strCustHelmName")),
        "Weapon": pick(
            ("strWeaponFile", "strWeaponLink", "strWeaponName"),
            ("strCustWeaponFile", "strCustWeaponLink", "strCustWeaponName")),
        "ba": pick(
            ("strCapeFile", "strCapeLink", "strCapeName"),
            ("strCustCapeFile", "strCustCapeLink", "strCustCapeName")),
        "pe": pick(
            ("strPetFile", "strPetLink", "strPetName"),
            ("strCustPetFile", "strCustPetLink", "strCustPetName")),
        "mi": _equipment_slot(
            flashvars, "strMiscFile", "strMiscLink", "strMiscName"),
    }

    weapon_type = flashvars.get("strWeaponType", "")
    if weapon_type:
        equipment["Weapon"]["Type"] = weapon_type

    payload = {
        "type": "character",
        "data": {
            "url": url,
            "gender": flashvars.get("strGender", "M"),
            "ia1": _int(flashvars, "ia1"),
            "swf": SWF_SOURCE,
            "equipment": equipment,
            "hair": {
                "File": flashvars.get("strHairFile", "hair/M/Normal.swf"),
                "Name": flashvars.get("strHairName", "Default"),
            },
            "intColorHair": _int(flashvars, "intColorHair", 16777215),
            "intColorSkin": _int(flashvars, "intColorSkin", 16777215),
            "intColorEye": _int(flashvars, "intColorEye", 0),
            "intColorTrim": _int(flashvars, "intColorTrim", 0),
            "intColorBase": _int(flashvars, "intColorBase", 0),
            "intColorAccessory": _int(flashvars, "intColorAccessory", 0),
        },
    }
    return payload


def decode_image(response: bytes) -> bytes:
    """
    Decode the swf2png service response.

    The service typically returns either:
    - Raw Base64 (bytes)
    - JSON containing `png`, `image`, or `data` keys
    """
    text = response.strip().decode("utf-8", errors="ignore")
    if not text:
        raise ValueError("Empty response from swf2png service.")

    if text.startswith("{"):
        payload = json.loads(text)
        b64_data = (
            payload.get("png") or payload.get("image")
            or payload.get("data") or payload.get("result"))
        if not b64_data:
            raise ValueError(f"Service response missing image data: {payload}")
        return base64.b64decode(b64_data)

    return base64.b64decode(text)


@dataclass
class RenderResult:
    image_bytes: bytes
    format: str = "png"
    source_character: str = ""
    used_cosmetics: bool = False


class SWF2PNGClient:
    """Async TCP client for the swf2png rendering service."""

    def __init__(self,
                 host: str = "127.0.0.1",
                 port: int = 4567,
                 timeout: float = 20.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    async def is_available(self) -> bool:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout / 2)
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    async def render_character(self,
                               character: str,
                               *,
                               use_cosmetics: bool = False,
                               asset_base_url: str = ASSET_BASE_URL) -> RenderResult:
        flashvars = await fetch_flashvars(character)
        payload = build_payload(
            flashvars, use_cosmetics=use_cosmetics, url=asset_base_url)

        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            timeout=self.timeout)
        data = json.dumps(payload).encode("utf-8")
        writer.write(data)
        writer.write(b"\n")
        await writer.drain()

        response = await asyncio.wait_for(reader.read(), timeout=self.timeout)
        writer.close()
        await writer.wait_closed()

        png_bytes = decode_image(response)
        return RenderResult(
            image_bytes=png_bytes,
            format="png",
            source_character=character,
            used_cosmetics=use_cosmetics,
        )


async def _cli(args: argparse.Namespace) -> None:
    client = SWF2PNGClient(host=args.host, port=args.port, timeout=args.timeout)

    if not await client.is_available():
        raise SystemExit(
            f"swf2png service is not reachable on {args.host}:{args.port}. "
            "Start Item.swf from the swf2png project first.")

    result = await client.render_character(
        args.character,
        use_cosmetics=args.cosmetics,
        asset_base_url=args.asset_base,
    )

    image_bytes = result.image_bytes
    target_format = args.format.lower()
    output_path = Path(args.output or f"renders/{args.character}.{target_format}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if target_format == "png":
        output_path.write_bytes(image_bytes)
        print(f"Saved PNG render to {output_path}")
        return

    if target_format == "gif":
        if Image is None:
            raise SystemExit("Pillow is required to export GIFs.")
        with Image.open(BytesIO(image_bytes)) as img:
            rgba = img.convert("RGBA")
            gif_bytes = BytesIO()
            rgba.save(gif_bytes, format="GIF", save_all=False, transparency=0)
            output_path.write_bytes(gif_bytes.getvalue())
        print(f"Saved GIF render to {output_path}")
        return

    raise SystemExit(f"Unsupported output format: {args.format}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render AQW characters without CharPage UI using swf2png.")
    parser.add_argument("character", help="Character IGN to render.")
    parser.add_argument("-o",
                        "--output",
                        help="Output file path. Defaults to renders/<IGN>.<ext>")
    parser.add_argument("-f",
                        "--format",
                        choices=("png", "gif"),
                        default="png",
                        help="Image format to save (default: png).")
    parser.add_argument("--cosmetics",
                        action="store_true",
                        help="Render cosmetic items instead of equipped gear.")
    parser.add_argument("--host",
                        default=os.environ.get("SWF2PNG_HOST", "127.0.0.1"),
                        help="Hostname where Item.swf is listening.")
    parser.add_argument("--port",
                        type=int,
                        default=int(os.environ.get("SWF2PNG_PORT", "4567")),
                        help="TCP port for the swf2png service.")
    parser.add_argument("--timeout",
                        type=float,
                        default=20.0,
                        help="Socket timeout in seconds.")
    parser.add_argument("--asset-base",
                        default=ASSET_BASE_URL,
                        help="Override the AQW asset base URL if needed.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(_cli(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
