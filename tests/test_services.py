"""Tests for the Apple Music actions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.apple_music.const import DOMAIN, LOOKUP_URL, SEARCH_URL

from .conftest import CURRENT_TRACK, GROUPED_PLAYER, OTHER_PLAYER, SONOS_PLAYER

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

pytestmark = pytest.mark.usefixtures("setup_integration", "players")

ACCOUNT = "SA_RINCON52231_X_#Svc52231-1a2b3c4d-Token"
YELLOW = "x-sonos-http:song%3a1122782283.mp4?sid=204&flags=8232&sn=28"
PARACHUTES = "x-rincon-cpcontainer:1004206calbum%3a1122782080?sid=204&flags=8300&sn=28"
LE_CODE = (
    "x-rincon-cpcontainer:1006206cplaylist%3apl.084e56c4114a4a199e582aa7db6e7e56"
    "?sid=204&flags=8300&sn=28"
)
# A playlist in the library of the account, not in the catalog.
DINNER = (
    "x-rincon-cpcontainer:1006206clibraryplaylist%3ap.0EMR6fVXaXKR"
    "?sid=204&flags=8300&sn=28"
)
SANTE = "x-sonos-http:song%3a1589216089.mp4?sid=204&flags=8232&sn=28"
DEFILER = "x-sonos-http:song%3a1375875957.mp4?sid=204&flags=8232&sn=28"
ALORS_ON_DANSE = "x-sonos-http:song%3a1440520983.mp4?sid=204&flags=8232&sn=28"
QMUSIC = "https://audio-streaming.qmusic.be/qmusic.mp3"


def _queued(soco: MagicMock) -> list[tuple[str, int]]:
    """Return the URIs added to the Sonos queue, with the position asked for."""
    requests = (
        dict(args[0]) for args, _ in soco.avTransport.AddURIToQueue.call_args_list
    )
    return [
        (request["EnqueuedURI"], request["DesiredFirstTrackNumberEnqueued"])
        for request in requests
    ]


def _metadata(soco: MagicMock) -> str:
    """Return the metadata of the first item added to the Sonos queue."""
    metadata: str = dict(soco.avTransport.AddURIToQueue.call_args.args[0])[
        "EnqueuedURIMetaData"
    ]
    return metadata


async def _play(hass: HomeAssistant, **data: Any) -> Any:
    """Call the play action on the Sonos speaker and return its response."""
    return await hass.services.async_call(
        DOMAIN,
        "play",
        {"entity_id": SONOS_PLAYER, **data},
        blocking=True,
        return_response=True,
    )


async def test_play_song(hass: HomeAssistant, soco: MagicMock) -> None:
    """Test the best matching song replaces the queue, with the household account."""
    response = await _play(hass, query="yellow coldplay")

    soco.clear_queue.assert_called_once()
    assert _queued(soco) == [(YELLOW, 0)]
    metadata = _metadata(soco)
    assert '<item id="10032020song%3a1122782283"' in metadata
    assert "<dc:title>Yellow</dc:title>" in metadata
    assert "<dc:creator>Coldplay</dc:creator>" in metadata
    assert "<upnp:album>Parachutes</upnp:album>" in metadata
    assert "<upnp:class>object.item.audioItem.musicTrack</upnp:class>" in metadata
    assert ACCOUNT in metadata
    soco.play_from_queue.assert_called_once_with(0)
    assert response == {
        "items": [
            {
                "media_type": "song",
                "id": "1122782283",
                "name": "Yellow",
                "artist": "Coldplay",
                "album": "Parachutes",
                "url": "https://music.apple.com/be/song/-/1122782283",
                "media_content_id": "media-source://apple_music/song/1122782283",
                "artwork_url": (
                    "https://is1-ssl.mzstatic.com/image/thumb/Music221/v4/f5/93/8c/"
                    "f5938c49-964c-31d1-4b33-78b634f71fb7/190295978075.jpg/600x600bb.jpg"
                ),
            }
        ]
    }


async def test_play_album(hass: HomeAssistant, soco: MagicMock) -> None:
    """Test an album is added to the queue as a whole."""
    await _play(hass, query="parachutes", media_type="album", enqueue="add")

    assert _queued(soco) == [(PARACHUTES, 0)]
    assert "object.container.album.musicAlbum" in _metadata(soco)
    soco.clear_queue.assert_not_called()
    soco.play_from_queue.assert_not_called()


@pytest.mark.parametrize(
    ("enqueue", "expected"),
    [
        ("replace", [(SANTE, 0), (DEFILER, 0), (ALORS_ON_DANSE, 0)]),
        ("add", [(SANTE, 0), (DEFILER, 0), (ALORS_ON_DANSE, 0)]),
        ("next", [(SANTE, 4), (DEFILER, 5), (ALORS_ON_DANSE, 6)]),
        ("play", [(SANTE, 4), (DEFILER, 5), (ALORS_ON_DANSE, 6)]),
    ],
)
async def test_play_artist(
    hass: HomeAssistant,
    soco: MagicMock,
    mock_catalog: AiohttpClientMocker,
    enqueue: str,
    expected: list[tuple[str, int]],
) -> None:
    """Test the top songs of an artist end up in the queue in order."""
    response = await _play(
        hass, query="stromae", media_type="artist", enqueue=enqueue, limit=3
    )

    assert _queued(soco) == expected
    assert soco.clear_queue.called is (enqueue == "replace")
    # Replace plays the new queue, play the first song after the current track.
    if (played_from := {"replace": 0, "play": CURRENT_TRACK}.get(enqueue)) is None:
        soco.play_from_queue.assert_not_called()
    else:
        soco.play_from_queue.assert_called_once_with(played_from)
    assert response["items"][0]["name"] == "Santé"
    assert mock_catalog.mock_calls[-1][1].query["limit"] == "3"


@pytest.mark.parametrize(
    ("url", "expected", "title"),
    [
        (
            "https://music.apple.com/be/playlist/le-code/pl.084e56c4114a4a199e582aa7db6e7e56",
            LE_CODE,
            "<dc:title></dc:title>",
        ),
        (
            "https://music.apple.com/library/playlist/p.0EMR6fVXaXKR",
            DINNER,
            '<item id="1006206clibraryplaylist%3ap.0EMR6fVXaXKR"',
        ),
        (
            "https://music.apple.com/be/album/parachutes/1122782080",
            PARACHUTES,
            "<dc:title></dc:title>",
        ),
        (
            "https://music.apple.com/be/album/parachutes/1122782080?i=1122782283",
            YELLOW,
            "<dc:title>Yellow</dc:title>",
        ),
        ("https://music.apple.com/be/song/yellow/1122782283", YELLOW, "Yellow"),
    ],
)
async def test_play_url(
    hass: HomeAssistant, soco: MagicMock, url: str, expected: str, title: str
) -> None:
    """Test Apple Music links play, songs with their title looked up."""
    response = await _play(hass, url=url, enqueue="next")

    assert _queued(soco) == [(expected, CURRENT_TRACK + 1)]
    assert title in _metadata(soco)
    assert len(response["items"]) == 1


async def test_play_artist_url(
    hass: HomeAssistant, soco: MagicMock, mock_catalog: AiohttpClientMocker
) -> None:
    """Test an artist link plays the top songs of the artist."""
    response = await _play(
        hass, url="https://music.apple.com/be/artist/stromae/270954369", limit=3
    )

    assert _queued(soco) == [(SANTE, 0), (DEFILER, 0), (ALORS_ON_DANSE, 0)]
    assert len(response["items"]) == 3
    assert mock_catalog.mock_calls[-1][1].query["limit"] == "3"


async def test_play_artist_url_failed(
    hass: HomeAssistant, soco: MagicMock, mock_catalog: AiohttpClientMocker
) -> None:
    """Test an artist link without songs, or without Apple Music, plays nothing."""
    url = "https://music.apple.com/be/artist/stromae/270954369"
    mock_catalog.clear_requests()
    mock_catalog.get(LOOKUP_URL, json={"resultCount": 0, "results": []})
    with pytest.raises(ServiceValidationError) as err:
        await _play(hass, url=url)
    assert err.value.translation_key == "no_results"

    mock_catalog.clear_requests()
    mock_catalog.get(LOOKUP_URL, status=503)
    with pytest.raises(HomeAssistantError) as failed:
        await _play(hass, url=url)
    assert failed.value.translation_key == "request_failed"
    soco.avTransport.AddURIToQueue.assert_not_called()


async def test_play_url_without_catalog(
    hass: HomeAssistant, soco: MagicMock, mock_catalog: AiohttpClientMocker
) -> None:
    """Test a song link still plays when its title cannot be looked up."""
    mock_catalog.clear_requests()
    mock_catalog.get(LOOKUP_URL, status=503)

    await _play(hass, url="https://music.apple.com/be/song/yellow/1122782283")

    assert _queued(soco) == [(YELLOW, 0)]


async def test_play_grouped(hass: HomeAssistant, soco: MagicMock) -> None:
    """Test grouped speakers share the queue of their coordinator."""
    await hass.services.async_call(
        DOMAIN,
        "play",
        {"entity_id": [SONOS_PLAYER, GROUPED_PLAYER], "query": "yellow"},
        blocking=True,
    )

    assert _queued(soco) == [(YELLOW, 0)]


async def test_play_only_on_sonos(hass: HomeAssistant, soco: MagicMock) -> None:
    """Test speakers that cannot play Apple Music are left out."""
    await hass.services.async_call(
        DOMAIN,
        "play",
        {"entity_id": [SONOS_PLAYER, OTHER_PLAYER], "query": "yellow"},
        blocking=True,
    )
    assert _queued(soco) == [(YELLOW, 0)]

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
        (
            {"url": "https://music.apple.com/be/curator/apple-music/976439548"},
            "invalid_url",
        ),
        ({"url": "https://open.spotify.com/track/1"}, "invalid_url"),
        ({"query": "anything", "media_type": "playlist"}, "not_searchable"),
    ],
)
async def test_play_invalid(
    hass: HomeAssistant, soco: MagicMock, data: dict[str, str], translation_key: str
) -> None:
    """Test links and searches Sonos cannot play are refused."""
    with pytest.raises(ServiceValidationError) as err:
        await _play(hass, **data)

    assert err.value.translation_key == translation_key
    soco.avTransport.AddURIToQueue.assert_not_called()


async def test_play_no_account(hass: HomeAssistant, soco: MagicMock) -> None:
    """Test an error is raised when no Sonos favorite shows the Apple Music account."""
    soco.contentDirectory.Browse.return_value = {"Result": "<DIDL-Lite></DIDL-Lite>"}

    with pytest.raises(HomeAssistantError) as err:
        await _play(hass, query="yellow")

    assert err.value.translation_key == "no_account"
    soco.clear_queue.assert_not_called()


async def test_play_sonos_error(hass: HomeAssistant, soco: MagicMock) -> None:
    """Test errors of the Sonos speaker are raised as readable errors."""
    soco.avTransport.AddURIToQueue.side_effect = RuntimeError("UPnP Error 800")

    with pytest.raises(HomeAssistantError) as err:
        await _play(hass, query="yellow")

    assert err.value.translation_key == "sonos_error"
    assert err.value.translation_placeholders == {"error": "UPnP Error 800"}


async def test_play_speaker_unavailable(hass: HomeAssistant, soco: MagicMock) -> None:
    """Test an error is raised for a speaker the Sonos integration does not know."""
    entry = hass.config_entries.async_entries("sonos")[0]
    entry.runtime_data.unique_id_speaker_mappings.clear()

    with pytest.raises(HomeAssistantError) as err:
        await _play(hass, query="yellow")

    assert err.value.translation_key == "speaker_unavailable"
    soco.avTransport.AddURIToQueue.assert_not_called()


async def test_play_no_results(
    hass: HomeAssistant, soco: MagicMock, mock_catalog: AiohttpClientMocker
) -> None:
    """Test an error is raised when nothing matches the query."""
    mock_catalog.clear_requests()
    mock_catalog.get(SEARCH_URL, json={"resultCount": 0, "results": []})

    with pytest.raises(ServiceValidationError) as err:
        await _play(hass, query="nothing at all")

    assert err.value.translation_key == "no_results"
    soco.avTransport.AddURIToQueue.assert_not_called()


async def test_play_request_failed(
    hass: HomeAssistant, mock_catalog: AiohttpClientMocker
) -> None:
    """Test an error is raised when Apple Music cannot be reached."""
    mock_catalog.clear_requests()
    mock_catalog.get(SEARCH_URL, status=503)

    with pytest.raises(HomeAssistantError) as err:
        await _play(hass, query="yellow")

    assert err.value.translation_key == "request_failed"


@pytest.mark.parametrize(
    ("data", "title"),
    [({"name": "Qmusic"}, "Qmusic"), ({}, QMUSIC)],
)
async def test_play_radio(
    hass: HomeAssistant, soco: MagicMock, data: dict[str, str], title: str
) -> None:
    """Test a radio stream plays once on grouped speakers, named after the station."""
    await hass.services.async_call(
        DOMAIN,
        "play_radio",
        {"entity_id": [SONOS_PLAYER, GROUPED_PLAYER], "url": QMUSIC, **data},
        blocking=True,
    )

    soco.play_uri.assert_called_once_with(QMUSIC, title=title, force_radio=True)


async def test_play_radio_only_on_sonos(hass: HomeAssistant, soco: MagicMock) -> None:
    """Test a radio stream is refused for speakers of another brand."""
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "play_radio",
            {"entity_id": OTHER_PLAYER, "url": QMUSIC},
            blocking=True,
        )

    assert err.value.translation_key == "no_sonos_players"
    soco.play_uri.assert_not_called()


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
        ("Yellow", "https://music.apple.com/be/song/-/1122782283"),
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
