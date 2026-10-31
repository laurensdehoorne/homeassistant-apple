"""Apple Music playlists found through Music Assistant.

Apple's public search knows no playlists. Music Assistant, when it is installed with
its Apple Music provider, searches the whole catalog, playlists included. Only the
search goes through Music Assistant: the playlists play on Sonos like any other.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError

from .api import CatalogItem, resize_artwork
from .const import REQUEST_TIMEOUT, Kind

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

MUSIC_ASSISTANT_DOMAIN = "music_assistant"
SERVICE_SEARCH = "search"

# Music Assistant names an Apple Music playlist after the provider instance, like
# apple_music--wHd9x2h6://playlist/pl.6a236667fbc046a49b48ea9cf4e8b639.
_PLAYLIST = re.compile(r"^apple_music(?:--[^:]+)?://playlist/(pl?\.[-a-zA-Z0-9]+)$")


async def async_search_playlists(
    hass: HomeAssistant, query: str, limit: int
) -> list[CatalogItem]:
    """Return the Apple Music playlists Music Assistant finds, if it is installed."""
    entries = hass.config_entries.async_loaded_entries(MUSIC_ASSISTANT_DOMAIN)
    if not entries or not hass.services.has_service(
        MUSIC_ASSISTANT_DOMAIN, SERVICE_SEARCH
    ):
        return []
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            response = await hass.services.async_call(
                MUSIC_ASSISTANT_DOMAIN,
                SERVICE_SEARCH,
                {
                    "config_entry_id": entries[0].entry_id,
                    "name": query,
                    "media_type": [Kind.PLAYLIST.value],
                    "limit": limit,
                },
                blocking=True,
                return_response=True,
            )
    except (HomeAssistantError, TimeoutError) as err:
        # The playlists are extra: the rest of a search works without them.
        _LOGGER.debug("Music Assistant could not search for %s: %s", query, err)
        return []
    found: Any = (response or {}).get("playlists") or []
    return [
        CatalogItem(
            kind=Kind.PLAYLIST,
            id=match.group(1),
            name=playlist.get("name") or "",
            artwork_url=resize_artwork(image)
            if (image := playlist.get("image"))
            else None,
        )
        for playlist in found
        if (match := _PLAYLIST.match(playlist.get("uri") or ""))
    ]
