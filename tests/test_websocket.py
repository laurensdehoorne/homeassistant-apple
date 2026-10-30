"""Tests for the WebSocket commands of the Apple Music card."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from custom_components.apple_music.const import SEARCH_URL

from .conftest import ALBUM_ID, ARTIST_ID, OTHER_PLAYER, SONOS_PLAYER

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )
    from pytest_homeassistant_custom_component.typing import WebSocketGenerator

pytestmark = pytest.mark.usefixtures("setup_integration")


async def _send(hass_ws_client: WebSocketGenerator, **message: Any) -> Any:
    """Send a command and return the response."""
    client = await hass_ws_client()
    await client.send_json_auto_id(message)
    return await client.receive_json()


def _names(items: list[dict[str, Any]]) -> list[str]:
    """Return the names of catalog items."""
    return [item["name"] for item in items]


async def test_charts(hass_ws_client: WebSocketGenerator) -> None:
    """Test the card gets the most played songs."""
    response = await _send(hass_ws_client, type="apple_music/charts", media_type="song")

    assert response["success"]
    assert response["result"]["items"][0] == {
        "media_type": "song",
        "id": "6822497774",
        "name": "Housewife",
        "artist": "Tate McRae",
        "album": None,
        "url": "https://music.apple.com/be/song/-/6822497774",
        "media_content_id": "media-source://apple_music/song/6822497774",
        "artwork_url": response["result"]["items"][0]["artwork_url"],
    }


async def test_charts_of_playlists(hass_ws_client: WebSocketGenerator) -> None:
    """Test there is no chart of playlists, Sonos plays those by link only."""
    response = await _send(
        hass_ws_client, type="apple_music/charts", media_type="playlist"
    )

    assert response["error"]["code"] == "invalid_format"


async def test_album(hass_ws_client: WebSocketGenerator) -> None:
    """Test the card gets the songs on an album."""
    response = await _send(hass_ws_client, type="apple_music/album", album_id=ALBUM_ID)

    assert _names(response["result"]["songs"]) == [
        "Don't Panic",
        "Shiver",
        "Spies",
        "Sparks",
    ]


async def test_artist(hass_ws_client: WebSocketGenerator) -> None:
    """Test the card gets the top songs and the albums of an artist."""
    response = await _send(
        hass_ws_client, type="apple_music/artist", artist_id=ARTIST_ID
    )

    assert _names(response["result"]["songs"])[0] == "Santé"
    assert _names(response["result"]["albums"]) == ["Racine carrée", "Cheese"]


async def test_search(hass_ws_client: WebSocketGenerator) -> None:
    """Test the card searches songs, albums and artists at once."""
    response = await _send(hass_ws_client, type="apple_music/search", query="x")

    assert {group: _names(items) for group, items in response["result"].items()} == {
        "songs": ["Yellow", "Yellow (Live)"],
        "albums": ["Parachutes"],
        "artists": ["Stromae"],
    }


async def test_request_failed(
    hass_ws_client: WebSocketGenerator, mock_catalog: AiohttpClientMocker
) -> None:
    """Test an error is sent when Apple Music cannot be reached."""
    mock_catalog.clear_requests()
    mock_catalog.get(SEARCH_URL, status=503)

    response = await _send(hass_ws_client, type="apple_music/search", query="x")

    assert response["error"]["code"] == "request_failed"


async def test_not_loaded(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    setup_integration: MockConfigEntry,
) -> None:
    """Test an error is sent when Apple Music is not set up."""
    await hass.config_entries.async_unload(setup_integration.entry_id)

    response = await _send(hass_ws_client, type="apple_music/album", album_id="1")

    assert response["error"]["code"] == "not_loaded"


@pytest.mark.usefixtures("players")
async def test_playlists(hass_ws_client: WebSocketGenerator) -> None:
    """Test the card gets the Apple Music playlists in the Sonos favorites."""
    response = await _send(
        hass_ws_client, type="apple_music/playlists", entity_id=SONOS_PLAYER
    )

    assert _names(response["result"]["items"]) == [
        "Old account playlist",
        "Current account playlist",
        "Older account playlist",
    ]
    assert response["result"]["items"][1]["url"] == (
        "https://music.apple.com/be/playlist/-/pl.bbb"
    )


@pytest.mark.usefixtures("players")
async def test_playlists_of_other_speaker(hass_ws_client: WebSocketGenerator) -> None:
    """Test only Sonos speakers have playlists."""
    response = await _send(
        hass_ws_client, type="apple_music/playlists", entity_id=OTHER_PLAYER
    )

    assert response["error"]["code"] == "not_sonos"


@pytest.mark.usefixtures("players")
async def test_playlists_sonos_error(
    hass_ws_client: WebSocketGenerator, soco: MagicMock
) -> None:
    """Test an error is sent when the Sonos speaker cannot be reached."""
    soco.contentDirectory.Browse.side_effect = OSError("No route to host")

    response = await _send(
        hass_ws_client, type="apple_music/playlists", entity_id=SONOS_PLAYER
    )

    assert response["error"]["code"] == "sonos_error"
