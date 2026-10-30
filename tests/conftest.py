"""Fixtures for the Apple Music integration tests."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.apple_music.const import (
    CHARTS_URL,
    CONF_STOREFRONT,
    DOMAIN,
    LOOKUP_URL,
    SEARCH_URL,
)

from . import load_json

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

# Import the integration before pytest-homeassistant-custom-component imports
# its own custom_components package, so Home Assistant can find it.
importlib.import_module("custom_components.apple_music")

SONOS_PLAYER = "media_player.keuken"
OTHER_PLAYER = "media_player.google_home"

ALBUM_ID = "1122782080"
ARTIST_ID = "270954369"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,  # pylint: disable=unused-argument
) -> None:
    """Enable custom integrations."""


@pytest.fixture
def mock_catalog(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Answer catalog requests with recorded Apple Music responses."""
    for entity, fixture in (
        ("song", "search_song.json"),
        ("album", "search_album.json"),
        ("musicArtist", "search_artist.json"),
    ):
        aioclient_mock.get(f"{SEARCH_URL}?entity={entity}", json=load_json(fixture))
    for item_id, entity, fixture in (
        (ALBUM_ID, "song", "album_songs.json"),
        (ARTIST_ID, "song", "artist_songs.json"),
        (ARTIST_ID, "album", "artist_albums.json"),
    ):
        aioclient_mock.get(
            f"{LOOKUP_URL}?id={item_id}&entity={entity}", json=load_json(fixture)
        )
    aioclient_mock.get(
        CHARTS_URL.format(storefront="be", limit=50, feed="playlists"),
        json=load_json("chart_playlists.json"),
    )
    aioclient_mock.get(
        CHARTS_URL.format(storefront="be", limit=50, feed="albums"), status=502
    )
    return aioclient_mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return an Apple Music config entry for Belgium."""
    return MockConfigEntry(
        domain=DOMAIN, title="Apple Music (BE)", data={CONF_STOREFRONT: "be"}
    )


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_catalog: AiohttpClientMocker,  # noqa: ARG001 # pylint: disable=unused-argument
) -> MockConfigEntry:
    """Set up the Apple Music integration."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


@pytest.fixture
def players(hass: HomeAssistant) -> None:
    """Register a Sonos speaker and a speaker of another brand."""
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "media_player", "sonos", "RINCON_1", suggested_object_id="keuken"
    )
    registry.async_get_or_create(
        "media_player", "cast", "cast-1", suggested_object_id="google_home"
    )
