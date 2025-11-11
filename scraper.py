from typing import Optional, Dict
import re
import requests
from bs4 import BeautifulSoup
import aiohttp
import asyncio


BASE = "https://account.aq.com/CharPage"


def _first_text_by_label(soup: BeautifulSoup, label: str) -> Optional[str]:
    el = soup.find(text=re.compile(re.escape(label), re.I))
    if not el:
        return None
    
    parent = el.parent
    
    if parent:
        link = parent.find('a')
        if link and link.text.strip():
            return link.text.strip()
    
    if parent:
        current = parent
        while current:
            next_elem = current.next_sibling
            if next_elem is None:
                break
            if isinstance(next_elem, str):
                text = next_elem.strip()
                if text and text not in (':', '---'):
                    return text
            elif hasattr(next_elem, 'get_text'):
                text = next_elem.get_text(strip=True)
                if text and text not in (':', '---'):
                    return text
            current = next_elem
            if current and hasattr(current, 'name') and current.name in ('br', 'div', 'p'):
                break
    
    txt = el.strip()
    parts = re.split(re.escape(label), txt, flags=re.I)
    if len(parts) >= 2:
        remaining = parts[1].strip()
        if remaining and remaining not in (':', '---'):
            return remaining
    
    return None


def get_character_info(char_id: str) -> Dict[str, Optional[str]]:
    params = {"id": char_id}
    try:
        resp = requests.get(BASE, params=params, timeout=10)
    except Exception as e:
        raise RuntimeError(f"Network error when fetching character page: {e}")
    if resp.status_code != 200:
        raise RuntimeError(f"Character page returned status {resp.status_code}")

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "name": None,
        "guild": None,
        "class": None,
        "level": None,
        "experience": None,
        "health": None,
        "mana": None,
        "raw_html": html
    }

    for tagname in ("h1", "h2", "h3", "title"):
        t = soup.find(tagname)
        if t and t.text.strip():
            text = t.text.strip()
            if len(text) <= 40:  # heuristic length
                result["name"] = text
                break

    if not result["name"]:
        result["name"] = _first_text_by_label(soup, "Character") or _first_text_by_label(soup, "Name")

    result["guild"] = _first_text_by_label(soup, "Guild")
    if not result["guild"]:
        m = re.search(r"Guild[:\s]*<[^>]*>([^<]+)</", html, re.I)
        if m:
            result["guild"] = m.group(1).strip()
    if not result["guild"]:
        m2 = re.search(r"Guild[:\s]*([A-Za-z0-9 _-]{2,50})", html, re.I)
        if m2:
            result["guild"] = m2.group(1).strip()

    result["class"] = _first_text_by_label(soup, "Class")

    level_text = _first_text_by_label(soup, "Level")
    if level_text:
        m = re.search(r"\d+", level_text)
        if m:
            result["level"] = m.group(0)

    result["experience"] = _first_text_by_label(soup, "Experience") or _first_text_by_label(soup, "EXP")

    result["health"] = _first_text_by_label(soup, "Health") or _first_text_by_label(soup, "HP")

    result["mana"] = _first_text_by_label(soup, "Mana") or _first_text_by_label(soup, "MP")

    for key in result:
        if key != "raw_html":
            val = result[key]
            result[key] = val.strip() if val and val.strip() else None

    return result


async def get_character_info_async(char_id: str, session: aiohttp.ClientSession) -> Dict[str, Optional[str]]:
    params = {"id": char_id}
    try:
        async with session.get(BASE, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Character page returned status {resp.status}")
            html = await resp.text()
    except asyncio.TimeoutError:
        raise RuntimeError(f"Timeout when fetching character page (server took too long)")
    except Exception as e:
        raise RuntimeError(f"Network error when fetching character page: {e}")

    soup = BeautifulSoup(html, "html.parser")

    result = {
        "name": None,
        "guild": None,
        "class": None,
        "level": None,
        "experience": None,
        "health": None,
        "mana": None,
        "raw_html": html
    }

    for tagname in ("h1", "h2", "h3", "title"):
        t = soup.find(tagname)
        if t and t.text.strip():
            text = t.text.strip()
            if len(text) <= 40:
                result["name"] = text
                break

    if not result["name"]:
        result["name"] = _first_text_by_label(soup, "Character") or _first_text_by_label(soup, "Name")

    result["guild"] = _first_text_by_label(soup, "Guild")
    if not result["guild"]:
        m = re.search(r"Guild[:\s]*<[^>]*>([^<]+)</", html, re.I)
        if m:
            result["guild"] = m.group(1).strip()
    if not result["guild"]:
        m2 = re.search(r"Guild[:\s]*([A-Za-z0-9 _-]{2,50})", html, re.I)
        if m2:
            result["guild"] = m2.group(1).strip()

    result["class"] = _first_text_by_label(soup, "Class")

    level_text = _first_text_by_label(soup, "Level")
    if level_text:
        m = re.search(r"\d+", level_text)
        if m:
            result["level"] = m.group(0)

    result["experience"] = _first_text_by_label(soup, "Experience") or _first_text_by_label(soup, "EXP")
    result["health"] = _first_text_by_label(soup, "Health") or _first_text_by_label(soup, "HP")
    result["mana"] = _first_text_by_label(soup, "Mana") or _first_text_by_label(soup, "MP")

    for key in result:
        if key != "raw_html":
            val = result[key]
            result[key] = val.strip() if val and val.strip() else None

    return result


if __name__ == "__main__":
    import sys
    import asyncio
    if len(sys.argv) >= 2:
        cid = sys.argv[1]
        async def test():
            async with aiohttp.ClientSession() as session:
                info = await get_character_info_async(cid, session)
                print("Name:", info['name'])
                print("Guild:", info['guild'])
        asyncio.run(test())
    else:
        print("Usage: python scraper.py <char_id>")
