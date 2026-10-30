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

from .conftest import ALBUM_ID, ARTIST_ID, OTHER_PLAYER, SONOS_PLAYER

if TYPE_CHECKING:
    from collections.abc import Sequence

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
        ("Top playlists", f"{ROOT}/charts/playlist"),
    ]


async def test_browse_chart(hass: HomeAssistant) -> None:
    """Test a chart lists playable items Sonos shows in its media browser."""
    chart = await media_source.async_browse_media(hass, f"{ROOT}/charts/playlist")

    assert chart.title == "Top playlists"
    assert [child.title for child in _children(chart)] == ["LE CODE", "Hits français"]
    playlist = _children(chart)[0]
    assert playlist.media_content_id == (
        f"{ROOT}/playlist/pl.084e56c4114a4a199e582aa7db6e7e56"
    )
    assert playlist.media_class == MediaClass.PLAYLIST
    assert playlist.media_content_type.startswith("audio/")
    assert playlist.can_play
    assert not playlist.can_expand
    assert (playlist.thumbnail or "").endswith("600x600SC.DN02.jpg?l=en-GB")


async def test_browse_chart_failed(hass: HomeAssistant) -> None:
    """Test an error is raised when a chart cannot be loaded."""
    with pytest.raises(BrowseError):
        await media_source.async_browse_media(hass, f"{ROOT}/charts/album")


async def test_browse_chart_cached(
    hass: HomeAssistant, mock_catalog: AiohttpClientMocker
) -> None:
    """Test the last chart is shown when Apple's chart feed is down."""
    await media_source.async_browse_media(hass, f"{ROOT}/charts/playlist")

    mock_catalog.clear_requests()
    mock_catalog.get(
        CHARTS_URL.format(storefront="be", limit=50, feed="playlists"), status=502
    )
    with patch("custom_components.apple_music.api.time.monotonic", return_value=10**9):
        chart = await media_source.async_browse_media(hass, f"{ROOT}/charts/playlist")

    assert len(mock_catalog.mock_calls) == 1
    assert len(_children(chart)) == 2


async def test_browse_album(hass: HomeAssistant) -> None:
    """Test an album lists its songs."""
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
    """Test an artist lists the top songs and the albums."""
    artist = await media_source.async_browse_media(hass, f"{ROOT}/artist/{ARTIST_ID}")

    assert artist.title == "Stromae"
    assert [
        (child.media_class, child.title.split(" · ")[0]) for child in _children(artist)
    ] == [
        (MediaClass.TRACK, "Santé"),
        (MediaClass.TRACK, "Défiler (Bande originale de la capsule No. 5 Mosaert)"),
        (MediaClass.TRACK, "Alors on danse (Radio Edit)"),
        (MediaClass.ALBUM, "Racine carrée"),
        (MediaClass.ALBUM, "Cheese"),
    ]


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


async def test_resolve_on_sonos(hass: HomeAssistant) -> None:
    """Test songs, albums and playlists resolve to links Sonos plays."""
    for identifier, url in (
        ("song/1122782283", "https://music.apple.com/be/song/-/1122782283"),
        ("album/1122782080", "https://music.apple.com/be/album/-/1122782080"),
        ("playlist/pl.abc", "https://music.apple.com/be/playlist/-/pl.abc"),
    ):
        media = await media_source.async_resolve_media(
            hass, f"{ROOT}/{identifier}", SONOS_PLAYER
        )
        assert media.url == url


@pytest.mark.parametrize(
    ("identifier", "target", "translation_key"),
    [
        ("song/1122782283", OTHER_PLAYER, "sonos_only"),
        (f"artist/{ARTIST_ID}", SONOS_PLAYER, "not_playable"),
        ("charts/song", SONOS_PLAYER, "not_playable"),
    ],
)
async def test_resolve_unplayable(
    hass: HomeAssistant, identifier: str, target: str, translation_key: str
) -> None:
    """Test items or speakers that cannot play Apple Music links are refused."""
    with pytest.raises(media_source.Unresolvable) as err:
        await media_source.async_resolve_media(hass, f"{ROOT}/{identifier}", target)

    assert err.value.translation_key == translation_key
