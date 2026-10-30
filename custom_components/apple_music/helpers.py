"""Helpers shared by the Apple Music actions and media source."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, SONOS_DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .api import AppleMusicCatalog


def get_catalog(hass: HomeAssistant) -> AppleMusicCatalog | None:
    """Return the catalog of the loaded config entry, if any."""
    if not (entries := hass.config_entries.async_loaded_entries(DOMAIN)):
        return None
    catalog: AppleMusicCatalog = entries[0].runtime_data
    return catalog


def is_sonos_player(hass: HomeAssistant, entity_id: str) -> bool:
    """Return whether the entity is a Sonos speaker, which plays Apple Music links."""
    entry = er.async_get(hass).async_get(entity_id)
    return (
        entry is not None
        and entry.domain == MEDIA_PLAYER_DOMAIN
        and entry.platform == SONOS_DOMAIN
    )
