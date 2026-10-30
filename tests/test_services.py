"""Tests for the Apple Music actions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.apple_music.const import DOMAIN, SEARCH_URL

from .conftest import OTHER_PLAYER, SONOS_PLAYER

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

pytestmark = pytest.mark.usefixtures("setup_integration", "players")

YELLOW = "https://music.apple.com/be/song/-/1122782283"
PARACHUTES = "https://music.apple.com/be/album/-/1122782080"
SANTE = "https://music.apple.com/be/song/-/1589216089"
DEFILER = "https://music.apple.com/be/song/-/1375875957"
ALORS_ON_DANSE = "https://music.apple.com/be/song/-/1440520983"


@pytest.fixture
def play_media(hass: HomeAssistant) -> list[ServiceCall]:
    """Record the play_media calls to the Sonos speakers."""
    calls: list[ServiceCall] = async_mock_service(hass, "media_player", "play_media")
    return calls


def _played(calls: list[ServiceCall]) -> list[tuple[str, str]]:
    """Return the links and enqueue modes that were sent to the speakers."""
    return [(call.data["media_content_id"], call.data["enqueue"]) for call in calls]


async def _play(hass: HomeAssistant, **data: Any) -> Any:
    """Call the play action on the Sonos speaker and return its response."""
    return await hass.services.async_call(
        DOMAIN,
        "play",
        {"entity_id": SONOS_PLAYER, **data},
        blocking=True,
        return_response=True,
    )


async def test_play_song(hass: HomeAssistant, play_media: list[ServiceCall]) -> None:
    """Test playing the best matching song replaces the Sonos queue."""
    response = await _play(hass, query="yellow coldplay")

    assert _played(play_media) == [(YELLOW, "replace")]
    assert play_media[0].data["entity_id"] == [SONOS_PLAYER]
    assert play_media[0].data["media_content_type"] == "music"
    assert response == {
        "items": [
            {
                "media_type": "song",
                "id": "1122782283",
                "name": "Yellow",
                "artist": "Coldplay",
                "album": "Parachutes",
                "url": YELLOW,
                "media_content_id": "media-source://apple_music/song/1122782283",
                "artwork_url": (
                    "https://is1-ssl.mzstatic.com/image/thumb/Music221/v4/f5/93/8c/"
                    "f5938c49-964c-31d1-4b33-78b634f71fb7/190295978075.jpg/600x600bb.jpg"
                ),
            }
        ]
    }


async def test_play_album(hass: HomeAssistant, play_media: list[ServiceCall]) -> None:
    """Test playing an album plays the album link."""
    await _play(hass, query="parachutes", media_type="album", enqueue="add")

    assert _played(play_media) == [(PARACHUTES, "add")]


@pytest.mark.parametrize(
    ("enqueue", "expected"),
    [
        (
            "replace",
            [(SANTE, "replace"), (DEFILER, "add"), (ALORS_ON_DANSE, "add")],
        ),
        ("add", [(SANTE, "add"), (DEFILER, "add"), (ALORS_ON_DANSE, "add")]),
        ("next", [(ALORS_ON_DANSE, "next"), (DEFILER, "next"), (SANTE, "next")]),
        ("play", [(ALORS_ON_DANSE, "next"), (DEFILER, "next"), (SANTE, "play")]),
    ],
)
async def test_play_artist(
    hass: HomeAssistant,
    play_media: list[ServiceCall],
    mock_catalog: AiohttpClientMocker,
    enqueue: str,
    expected: list[tuple[str, str]],
) -> None:
    """Test the top songs of an artist end up in the queue in order."""
    response = await _play(
        hass, query="stromae", media_type="artist", enqueue=enqueue, limit=3
    )

    assert _played(play_media) == expected
    assert response["items"][0]["name"] == "Santé"
    assert mock_catalog.mock_calls[-1][1].query["limit"] == "3"


async def test_play_url(hass: HomeAssistant, play_media: list[ServiceCall]) -> None:
    """Test playing an Apple Music link as is."""
    url = "https://music.apple.com/be/playlist/le-code/pl.084e56c4114a4a199e582aa7db6e7e56"
    response = await _play(hass, url=url, enqueue="next")

    assert _played(play_media) == [(url, "next")]
    assert response == {"items": []}


async def test_play_only_on_sonos(
    hass: HomeAssistant, play_media: list[ServiceCall]
) -> None:
    """Test speakers that cannot play Apple Music links are left out."""
    await hass.services.async_call(
        DOMAIN,
        "play",
        {"entity_id": [SONOS_PLAYER, OTHER_PLAYER], "query": "yellow"},
        blocking=True,
    )
    assert play_media[0].data["entity_id"] == [SONOS_PLAYER]

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "play",
            {"entity_id": OTHER_PLAYER, "query": "yellow"},
            blocking=True,
        )
    assert err.value.translation_key == "no_sonos_players"


@pytest.mark.parametrize(
    ("data", "translation_key"),
    [
        ({"url": "https://music.apple.com/be/artist/stromae/270954369"}, "invalid_url"),
        ({"url": "https://open.spotify.com/track/1"}, "invalid_url"),
        ({"query": "anything", "media_type": "playlist"}, "not_searchable"),
    ],
)
async def test_play_invalid(
    hass: HomeAssistant,
    play_media: list[ServiceCall],
    data: dict[str, str],
    translation_key: str,
) -> None:
    """Test links and searches Sonos cannot play are refused."""
    with pytest.raises(ServiceValidationError) as err:
        await _play(hass, **data)

    assert err.value.translation_key == translation_key
    assert not play_media


async def test_play_no_results(
    hass: HomeAssistant,
    play_media: list[ServiceCall],
    mock_catalog: AiohttpClientMocker,
) -> None:
    """Test an error is raised when nothing matches the query."""
    mock_catalog.clear_requests()
    mock_catalog.get(SEARCH_URL, json={"resultCount": 0, "results": []})

    with pytest.raises(ServiceValidationError) as err:
        await _play(hass, query="nothing at all")

    assert err.value.translation_key == "no_results"
    assert not play_media


async def test_play_request_failed(
    hass: HomeAssistant, mock_catalog: AiohttpClientMocker
) -> None:
    """Test an error is raised when Apple Music cannot be reached."""
    mock_catalog.clear_requests()
    mock_catalog.get(SEARCH_URL, status=503)

    with pytest.raises(HomeAssistantError) as err:
        await _play(hass, query="yellow")

    assert err.value.translation_key == "request_failed"


async def test_search(hass: HomeAssistant) -> None:
    """Test searching returns the matches."""
    response: Any = await hass.services.async_call(
        DOMAIN,
        "search",
        {"query": "yellow coldplay", "limit": 2},
        blocking=True,
        return_response=True,
    )

    assert response is not None
    assert [(item["name"], item["url"]) for item in response["items"]] == [
        ("Yellow", YELLOW),
        ("Yellow (Live)", "https://music.apple.com/be/song/-/693573510"),
    ]


async def test_not_loaded(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Test the actions fail when the config entry is not loaded."""
    await hass.config_entries.async_unload(setup_integration.entry_id)

    with pytest.raises(ServiceValidationError) as err:
        await _play(hass, query="yellow")
    assert err.value.translation_key == "not_loaded"
