"""Tests for queueing Apple Music on Sonos speakers."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from homeassistant.components.media_player import MediaPlayerEnqueue
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.apple_music.api import CatalogItem
from custom_components.apple_music.const import Kind
from custom_components.apple_music.sonos import (
    AppleMusicAccount,
    async_join,
    async_play,
    find_account,
    find_playlists,
    item_uri,
)

from . import load_text
from .conftest import CURRENT_TRACK, GROUPED_PLAYER, SONOS_PLAYER

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant

ACCOUNT = AppleMusicAccount(serial="28", token="1a2b3c4d")
# A speaker that leads a group, and one that plays alone.
LEADER = "media_player.eetruimte"
STANDALONE = "media_player.badkamer"


def test_find_account() -> None:
    """Test the most recently linked Apple Music account is used."""
    account = find_account(load_text("sonos_favorites.xml"))

    assert account == ACCOUNT
    assert account.desc == "SA_RINCON52231_X_#Svc52231-1a2b3c4d-Token"


@pytest.mark.parametrize(
    "favorites",
    [
        "<DIDL-Lite></DIDL-Lite>",
        # Only the radio station of another music service.
        re.sub(
            r'<item id="FV:2/(?:5|4|67)".*?</item>',
            "",
            load_text("sonos_favorites.xml"),
        ),
    ],
)
def test_find_no_account(favorites: str) -> None:
    """Test no account is found without Apple Music favorites."""
    assert "Radio" in favorites or favorites == "<DIDL-Lite></DIDL-Lite>"
    assert find_account(favorites) is None


@pytest.mark.parametrize(
    ("kind", "item_id", "uri"),
    [
        (
            Kind.SONG,
            "1122782283",
            "x-sonos-http:song%3a1122782283.mp4?sid=204&flags=8232&sn=28",
        ),
        (
            Kind.ALBUM,
            "1122782080",
            "x-rincon-cpcontainer:1004206calbum%3a1122782080?sid=204&flags=8300&sn=28",
        ),
        (
            Kind.PLAYLIST,
            "pl.abc",
            "x-rincon-cpcontainer:1006206cplaylist%3apl.abc?sid=204&flags=8300&sn=28",
        ),
    ],
)
def test_item_uri(kind: Kind, item_id: str, uri: str) -> None:
    """Test the URIs Sonos plays Apple Music songs, albums and playlists from."""
    assert item_uri(ACCOUNT, kind, item_id) == uri


@pytest.mark.usefixtures("players")
async def test_play_next_after_albums(hass: HomeAssistant, soco: MagicMock) -> None:
    """Test items played next stay in order after albums of several tracks."""
    albums = [
        CatalogItem(Kind.ALBUM, "1", "Racine carrée", artist="Stromae & <Co>"),
        CatalogItem(Kind.ALBUM, "2", "Cheese"),
        CatalogItem(Kind.SONG, "3", "Santé"),
    ]

    await async_play(hass, [SONOS_PLAYER], albums, MediaPlayerEnqueue.PLAY)

    positions = [
        dict(args[0])["DesiredFirstTrackNumberEnqueued"]
        for args, _ in soco.avTransport.AddURIToQueue.call_args_list
    ]
    first = CURRENT_TRACK + 1
    assert positions == [first, first + 10, first + 20]
    soco.play_from_queue.assert_called_once_with(first - 1)
    metadata = dict(soco.avTransport.AddURIToQueue.call_args_list[0].args[0])[
        "EnqueuedURIMetaData"
    ]
    assert "<dc:creator>Stromae &amp; &lt;Co&gt;</dc:creator>" in metadata


def test_find_playlists() -> None:
    """Test the Apple Music playlists in the favorites are found, radio left out."""
    playlists = find_playlists(load_text("sonos_favorites.xml"))

    assert [(item.kind, item.id, item.name) for item in playlists] == [
        (Kind.PLAYLIST, "pl.aaa", "Old account playlist"),
        (Kind.PLAYLIST, "pl.bbb", "Current account playlist"),
        (Kind.PLAYLIST, "pl.ccc", "Older account playlist"),
    ]


def test_find_playlist_artwork() -> None:
    """Test a playlist gets its title unescaped and larger artwork."""
    favorites = (
        '<DIDL-Lite><item id="FV:2/80"><dc:title>Lounge (Bar &amp; Café)</dc:title>'
        "<res>x-rincon-cpcontainer:1006206cplaylist%3Apl.c96a?sid=204&amp;flags=8300"
        "&amp;sn=28</res><upnp:albumArtURI>https://is1-ssl.mzstatic.com/image/thumb/"
        "abc/400x400bb.jpeg</upnp:albumArtURI></item></DIDL-Lite>"
    )

    assert find_playlists(favorites) == [
        CatalogItem(
            Kind.PLAYLIST,
            "pl.c96a",
            "Lounge (Bar & Café)",
            artwork_url="https://is1-ssl.mzstatic.com/image/thumb/abc/600x600bb.jpeg",
        )
    ]


def test_find_library_playlist() -> None:
    """Test a playlist of the user's own library is found too."""
    favorites = (
        '<DIDL-Lite><item id="FV:2/107"><dc:title>Dinner with Friends</dc:title>'
        "<res>x-rincon-cpcontainer:1006206clibraryplaylist%3Ap.0EMR6fVXaXKR?sid=204"
        "&amp;flags=8300&amp;sn=28</res></item></DIDL-Lite>"
    )

    (playlist,) = find_playlists(favorites)

    assert playlist == CatalogItem(
        Kind.PLAYLIST, "p.0EMR6fVXaXKR", "Dinner with Friends"
    )
    assert (
        playlist.url("be") == "https://music.apple.com/library/playlist/p.0EMR6fVXaXKR"
    )


@pytest.mark.parametrize(
    ("members", "speakers", "joined"),
    [
        ([SONOS_PLAYER], [SONOS_PLAYER, GROUPED_PLAYER], [GROUPED_PLAYER]),
        ([SONOS_PLAYER, GROUPED_PLAYER], [SONOS_PLAYER, GROUPED_PLAYER], None),
        ([LEADER, SONOS_PLAYER, GROUPED_PLAYER], [SONOS_PLAYER, GROUPED_PLAYER], None),
        (
            [LEADER, SONOS_PLAYER, GROUPED_PLAYER],
            [SONOS_PLAYER, GROUPED_PLAYER, STANDALONE],
            [GROUPED_PLAYER, STANDALONE],
        ),
    ],
)
async def test_join(
    hass: HomeAssistant,
    members: list[str],
    speakers: list[str],
    joined: list[str] | None,
) -> None:
    """Test speakers are grouped only when they play apart."""
    calls = async_mock_service(hass, "media_player", "join")
    hass.states.async_set(SONOS_PLAYER, "idle", {"group_members": members})

    await async_join(hass, speakers)

    if joined is None:
        assert not calls
    else:
        assert calls[0].data == {"entity_id": SONOS_PLAYER, "group_members": joined}
