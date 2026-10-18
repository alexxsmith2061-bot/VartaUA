
import asyncio
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

router = APIRouter()
BASE = Path(__file__).resolve().parent

OWNER = "yaroslav2901"
REPO = "OE_OUTAGE_DATA"
API = f"https://api.github.com/repos/{OWNER}/{REPO}/contents"

QUEUES = [
    "1.1", "1.2", "2.1", "2.2",
    "3.1", "3.2", "4.1", "4.2",
    "5.1", "5.2", "6.1", "6.2"
]

HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "VartaUA-Power/2.0"
}

_cache = {
    "updated": 0,
    "checked_at": None,
    "data": None,
    "images": {},
    "source_updated": None,
    "error": None
}

_lock = asyncio.Lock()


def matches_lviv(name):
    return bool(
        re.search(
            r"lviv|льв|loe",
            name,
            re.IGNORECASE
        )
    )


async def get_json(client, url):
    response = await client.get(url)
    response.raise_for_status()
    return response.json()


async def find_file(client, directory, extension):
    entries = await get_json(
        client,
        f"{API}/{directory}"
    )

    if not isinstance(entries, list):
        return None

    for entry in entries:
        name = entry.get("name", "")
        if (
            matches_lviv(name)
            and name.lower().endswith(extension)
            and entry.get("type") == "file"
        ):
            return entry

    return None


async def find_image_directory(client):
    entries = await get_json(client, f"{API}/images")

    if not isinstance(entries, list):
        return None

    for entry in entries:
        if (
            entry.get("type") == "dir"
            and matches_lviv(entry.get("name", ""))
        ):
            return entry.get("path")

    return None


async def update_cache():
    now = time.monotonic()

    async with _lock:
        if now - _cache["updated"] < 300:
            return

        _cache["updated"] = now

        try:
            async with httpx.AsyncClient(
                timeout=20,
                follow_redirects=True,
                headers=HEADERS
            ) as client:

                file = await find_file(
                    client, "data", ".json"
                )

                if not file:
                    raise ValueError(
                        "Файл графіків Львівщини не знайдено"
                    )

                download_url = file.get("download_url")

                if not download_url:
                    raise ValueError(
                        "Немає адреси JSON"
                    )

                data = await get_json(
                    client, download_url
                )

                if not isinstance(data, dict):
                    raise ValueError(
                        "Неправильний формат JSON"
                    )

                image_directory = (
                    await find_image_directory(client)
                )

                images = {}

                if image_directory:
                    entries = await get_json(
                        client,
                        f"{API}/{image_directory}"
                    )

                    if isinstance(entries, list):
                        for entry in entries:
                            name = entry.get(
                                "name", ""
                            ).lower()

                            for queue in QUEUES:
                                expected = (
                                    "gpv-"
                                    + queue.replace(".", "-")
                                    + ".png"
                                )

                                if name == expected:
                                    images[queue] = (
                                        entry.get("download_url")
                                    )

                _cache["data"] = data
                _cache["images"] = images
                _cache["source_updated"] = (
                    data.get("lastUpdated")
                    or data.get("fact", {}).get("update")
                    if isinstance(
                        data.get("fact"), dict
                    )
                    else data.get("lastUpdated")
                )

                _cache["checked_at"] = (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                )

                _cache["error"] = None

        except Exception as exc:
            _cache["error"] = str(exc)


def get_date_keys(data):
    fact = data.get("fact", {})

    if not isinstance(fact, dict):
        return []

    days = fact.get("data", {})

    if not isinstance(days, dict):
        return []

    return list(days.keys())


@router.get("/power")
async def power_page():
    return FileResponse(BASE / "power.html")


@router.get("/api/power/schedule")
async def schedule():
    await update_cache()

    data = _cache["data"] or {}
    images = _cache["images"]

    return {
        "source": (
            f"https://github.com/{OWNER}/{REPO}"
        ),
        "checked_at": _cache["checked_at"],
        "source_updated": _cache["source_updated"],
        "error": _cache["error"],
        "queues": QUEUES,
        "images": list(images.keys()),
        "dates": get_date_keys(data),
        "available": bool(images),
        "has_json": bool(data)
    }


@router.get("/api/power/image/{queue}")
async def power_image(queue: str):
    if queue not in QUEUES:
        raise HTTPException(
            status_code=404,
            detail="Невідома черга"
        )

    await update_cache()

    url = _cache["images"].get(queue)

    if not url:
        raise HTTPException(
            status_code=404,
            detail="Зображення графіка недоступне"
        )

    try:
        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers=HEADERS
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        if not response.headers.get(
            "content-type", ""
        ).startswith("image/"):
            raise ValueError(
                "Джерело не повернуло зображення"
            )

        return Response(
            content=response.content,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=300"
            }
        )

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Не вдалося завантажити графік"
        )
