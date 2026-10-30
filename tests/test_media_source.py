"""Tests for the Apple Music media source."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from homeassistant.components import media_source
from homeassistant.components.media_player import (
    BrowseError,
    BrowseMedia,
    MediaClass,
    SearchMediaQuery,
)

from custom_components.apple_music.const import CHARTS_URL

from .conftest import ALBUM_ID, ARTIST_ID, OTHER_PLAYER, SONG_ID, SONOS_PLAYER

if TYPE_CHECKING:
    from collections.abc import Sequence
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

pytestmark = pytest.mark.usefixtures("setup_integration", "players")

ROOT = "media-source://apple_music"


def _children(item: BrowseMedia) -> Sequence[BrowseMedia]:
    """Return the children of a browsed item."""
    assert item.children is not None
    return item.children


async def test_browse_root(hass: HomeAssistant) -> None:
    """Test the root lists the charts and can be searched."""
    root = await media_source.async_browse_media(hass, ROOT)

    assert root.title == "Apple Music"
    assert root.can_search
    assert [(child.title, child.media_content_id) for child in _children(root)] == [
        ("Top songs", f"{ROOT}/charts/song"),
        ("Top albums", f"{ROOT}/charts/album"),
    ]


async def test_browse_chart(hass: HomeAssistant) -> None:
    """Test the songs chart lists songs Sonos shows and plays in its browser."""
    chart = await media_source.async_browse_media(hass, f"{ROOT}/charts/song")

    assert chart.title == "Top songs"
    assert len(_children(chart)) == 2
    song = _children(chart)[0]
    assert song.title == "Housewife · Tate McRae"
    assert song.media_content_id == f"{ROOT}/song/6822497774"
    assert song.media_class == MediaClass.TRACK
    assert song.media_content_type.startswith("audio/")
    assert song.can_play
    assert not song.can_expand


async def test_browse_chart_failed(hass: HomeAssistant) -> None:
    """Test an error is raised when a chart cannot be loaded."""
    with pytest.raises(BrowseError):
        await media_source.async_browse_media(hass, f"{ROOT}/charts/album")


async def test_browse_chart_cached(
    hass: HomeAssistant, mock_catalog: AiohttpClientMocker
) -> None:
    """Test the last chart is shown when Apple's chart feed is down."""
    await media_source.async_browse_media(hass, f"{ROOT}/charts/song")

    mock_catalog.clear_requests()
    mock_catalog.get(
        CHARTS_URL.format(storefront="be", limit=50, feed="songs"), status=502
    )
    with patch("custom_components.apple_music.api.time.monotonic", return_value=10**9):
        chart = await media_source.async_browse_media(hass, f"{ROOT}/charts/song")

    assert len(mock_catalog.mock_calls) == 1
    assert len(_children(chart)) == 2


async def test_browse_album(hass: HomeAssistant) -> None:
    """Test an album opens to its songs."""
    album = await media_source.async_browse_media(hass, f"{ROOT}/album/{ALBUM_ID}")

    assert album.title == "Parachutes"
    assert [child.title for child in _children(album)] == [
        "Don't Panic · Coldplay",
        "Shiver · Coldplay",
        "Spies · Coldplay",
        "Sparks · Coldplay",
    ]
    assert all(child.can_play for child in _children(album))


async def test_browse_artist(hass: HomeAssistant) -> None:
    """Test an artist lists the top songs and the albums, which open."""
    artist = await media_source.async_browse_media(hass, f"{ROOT}/artist/{ARTIST_ID}")

    assert artist.title == "Stromae"
    assert [
        (child.media_class, child.title.split(" · ")[0], child.can_play)
        for child in _children(artist)
    ] == [
        (MediaClass.TRACK, "Santé", True),
        (
            MediaClass.TRACK,
            "Défiler (Bande originale de la capsule No. 5 Mosaert)",
            True,
        ),
        (MediaClass.TRACK, "Alors on danse (Radio Edit)", True),
        (MediaClass.ALBUM, "Racine carrée", False),
        (MediaClass.ALBUM, "Cheese", False),
    ]
    assert all(child.can_expand for child in _children(artist)[3:])


async def test_browse_unknown(hass: HomeAssistant) -> None:
    """Test browsing an unknown item raises an error."""
    with pytest.raises(BrowseError):
        await media_source.async_browse_media(hass, f"{ROOT}/song/1")


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (
            SearchMediaQuery(
                search_query="yellow", media_filter_classes=[MediaClass.TRACK]
            ),
            [MediaClass.TRACK, MediaClass.TRACK],
        ),
        (
            SearchMediaQuery(search_query="anything"),
            [MediaClass.TRACK, MediaClass.TRACK, MediaClass.ALBUM, MediaClass.ARTIST],
        ),
    ],
)
async def test_search(
    hass: HomeAssistant, query: SearchMediaQuery, expected: list[MediaClass]
) -> None:
    """Test searching the catalog from the media browser."""
    result = await media_source.async_search_media(hass, ROOT, query)

    assert [item.media_class for item in result.result] == expected


async def test_resolve_song(hass: HomeAssistant, soco: MagicMock) -> None:
    """Test a song resolves to its URI with the household's Apple Music account."""
    media = await media_source.async_resolve_media(
        hass, f"{ROOT}/song/{SONG_ID}", SONOS_PLAYER
    )

    assert media.url == f"x-sonos-http:song%3a{SONG_ID}.mp4?sid=204&flags=8232&sn=28"
    assert media.mime_type == "audio/mp4"
    soco.avTransport.AddURIToQueue.assert_not_called()


@pytest.mark.parametrize(
    ("identifier", "target", "translation_key"),
    [
        (f"song/{SONG_ID}", OTHER_PLAYER, "sonos_only"),
        (f"song/{SONG_ID}", None, "sonos_only"),
        (f"album/{ALBUM_ID}", SONOS_PLAYER, "not_playable"),
        (f"artist/{ARTIST_ID}", SONOS_PLAYER, "not_playable"),
        ("charts/song", SONOS_PLAYER, "not_playable"),
    ],
)
async def test_resolve_unplayable(
    hass: HomeAssistant, identifier: str, target: str | None, translation_key: str
) -> None:
    """Test items or speakers that cannot play from the browser are refused."""
    with pytest.raises(media_source.Unresolvable) as err:
        await media_source.async_resolve_media(hass, f"{ROOT}/{identifier}", target)

    assert err.value.translation_key == translation_key


async def test_resolve_no_account(hass: HomeAssistant, soco: MagicMock) -> None:
    """Test a song cannot resolve without a Sonos favorite showing the account."""
    soco.contentDirectory.Browse.return_value = {"Result": "<DIDL-Lite></DIDL-Lite>"}

    with pytest.raises(media_source.Unresolvable) as err:
        await media_source.async_resolve_media(
            hass, f"{ROOT}/song/{SONG_ID}", SONOS_PLAYER
        )

    assert err.value.translation_key == "no_account"
