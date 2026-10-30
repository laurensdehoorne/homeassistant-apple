"""Fixtures for the Apple Music integration tests."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
from homeassistant.components.homeassistant.exposed_entities import (
    async_expose_entity,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.apple_music.const import (
    CHARTS_URL,
    CONF_STOREFRONT,
    DOMAIN,
    LOOKUP_URL,
    SEARCH_URL,
)

from . import load_json, load_text

if TYPE_CHECKING:
    from collections.abc import Generator

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

# Import the integration before pytest-homeassistant-custom-component imports
# its own custom_components package, so Home Assistant can find it.
importlib.import_module("custom_components.apple_music")

SONOS_PLAYER = "media_player.keuken"
GROUPED_PLAYER = "media_player.woonkamer"
OTHER_PLAYER = "media_player.google_home"

ALBUM_ID = "1122782080"
ARTIST_ID = "270954369"
SONG_ID = "1122782283"

QUEUE_LENGTH = 5
CURRENT_TRACK = 3


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,  # pylint: disable=unused-argument
) -> None:
    """Enable custom integrations."""


@pytest.fixture(autouse=True)
async def setup_core(hass: HomeAssistant) -> None:
    """Set up Home Assistant's core integration, which Assist needs."""
    assert await async_setup_component(hass, "homeassistant", {})


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
    aioclient_mock.get(f"{LOOKUP_URL}?id={SONG_ID}", json=load_json("search_song.json"))
    aioclient_mock.get(
        CHARTS_URL.format(storefront="be", limit=50, feed="songs"),
        json=load_json("chart_songs.json"),
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
def soco() -> MagicMock:
    """Return the SoCo instance of the Sonos speaker, with a queue of 5 tracks."""
    soco = MagicMock()
    soco.contentDirectory.Browse.return_value = {
        "Result": load_text("sonos_favorites.xml")
    }
    soco.get_current_track_info.return_value = {"playlist_position": str(CURRENT_TRACK)}
    queue_length = QUEUE_LENGTH

    def add_uri_to_queue(args: list[tuple[str, Any]]) -> dict[str, str]:
        """Add a song, or ten tracks for an album or playlist."""
        nonlocal queue_length
        request = dict(args)
        added = 1 if "song%3a" in request["EnqueuedURI"] else 10
        first = request["DesiredFirstTrackNumberEnqueued"] or queue_length + 1
        queue_length += added
        return {
            "FirstTrackNumberEnqueued": str(first),
            "NumTracksAdded": str(added),
            "NewQueueLength": str(queue_length),
        }

    soco.avTransport.AddURIToQueue.side_effect = add_uri_to_queue
    return soco


@pytest.fixture
def players(hass: HomeAssistant, soco: MagicMock) -> Generator[None]:
    """Set up two grouped Sonos speakers and a speaker of another brand."""
    registry = er.async_get(hass)
    for unique_id, object_id in (("RINCON_1", "keuken"), ("RINCON_2", "woonkamer")):
        registry.async_get_or_create(
            "media_player",
            "sonos",
            unique_id,
            suggested_object_id=object_id,
            original_name=object_id.capitalize(),
        )
    registry.async_get_or_create(
        "media_player", "cast", "cast-1", suggested_object_id="google_home"
    )

    # The Sonos integration maps its entities to speakers in its runtime data.
    keuken = SimpleNamespace(soco=soco, coordinator=None)
    woonkamer = SimpleNamespace(soco=MagicMock(), coordinator=keuken)
    sonos_entry = MockConfigEntry(domain="sonos", state=ConfigEntryState.LOADED)
    sonos_entry.add_to_hass(hass)
    sonos_entry.runtime_data = SimpleNamespace(
        unique_id_speaker_mappings={"RINCON_1": keuken, "RINCON_2": woonkamer}
    )
    yield
    # Keep Home Assistant from unloading it with the real Sonos integration.
    sonos_entry.mock_state(hass, ConfigEntryState.NOT_LOADED)


@pytest.fixture
async def voice(
    hass: HomeAssistant,
    players: None,  # noqa: ARG001 # pylint: disable=unused-argument
    config_entry: MockConfigEntry,
    mock_catalog: AiohttpClientMocker,  # noqa: ARG001 # pylint: disable=unused-argument
) -> ar.AreaEntry:
    """Expose the Sonos speakers to Assist and set up Apple Music.

    The woonkamer speaker stands in the area Leefruimte, also called Living.
    """
    area = ar.async_get(hass).async_create("Leefruimte", aliases={"Living"})
    er.async_get(hass).async_update_entity(GROUPED_PLAYER, area_id=area.id)
    for entity_id in (SONOS_PLAYER, GROUPED_PLAYER):
        async_expose_entity(hass, "conversation", entity_id, should_expose=True)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return area
