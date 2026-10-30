"""Tests for queueing Apple Music on Sonos speakers."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from homeassistant.components.media_player import MediaPlayerEnqueue

from custom_components.apple_music.api import CatalogItem
from custom_components.apple_music.const import Kind
from custom_components.apple_music.sonos import (
    AppleMusicAccount,
    async_play,
    find_account,
    item_uri,
)

from . import load_text
from .conftest import CURRENT_TRACK, SONOS_PLAYER

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant

ACCOUNT = AppleMusicAccount(serial="28", token="1a2b3c4d")


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
