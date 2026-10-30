"""Serve the Apple Music dashboard card and load it in the frontend."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

CARD_PATH = Path(__file__).parent / "www" / "apple-music-card.js"
CARD_URL = "/apple_music/apple-music-card.js"


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the card and add it to every dashboard, so it needs no resource."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_PATH), cache_headers=False)]
    )
    # The hash makes browsers load a new card after an update.
    content = await hass.async_add_executor_job(CARD_PATH.read_bytes)
    add_extra_js_url(hass, f"{CARD_URL}?v={hashlib.sha256(content).hexdigest()[:8]}")
