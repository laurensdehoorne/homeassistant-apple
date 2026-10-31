"""WebSocket commands the Apple Music card browses the catalog with."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import probatio
from homeassistant.components import websocket_api
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from . import music_assistant, sonos
from .api import AppleMusicCatalog, AppleMusicError, CatalogItem
from .const import CHART_KINDS, Kind
from .helpers import get_catalog, is_sonos_player

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from homeassistant.core import HomeAssistant

SEARCH_LIMIT = 12

type _Fetch = Callable[[AppleMusicCatalog], Awaitable[dict[str, list[CatalogItem]]]]


@callback
def async_register_commands(hass: HomeAssistant) -> None:
    """Register the WebSocket commands of the Apple Music card."""
    for command in (ws_charts, ws_album, ws_artist, ws_search, ws_playlists):
        websocket_api.async_register_command(hass, command)


async def _async_send(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    fetch: _Fetch,
) -> None:
    """Send the catalog items fetch returns, grouped like it returns them."""
    if (catalog := get_catalog(hass)) is None:
        connection.send_error(msg["id"], "not_loaded", "Apple Music is not set up")
        return
    try:
        groups = await fetch(catalog)
    except AppleMusicError as err:
        connection.send_error(msg["id"], "request_failed", str(err))
        return
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "sonos_error", str(err))
        return
    connection.send_result(
        msg["id"],
        {
            group: [item.as_dict(catalog.storefront) for item in items]
            for group, items in groups.items()
        },
    )


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "apple_music/charts",
        probatio.Required("media_type"): probatio.All(
            probatio.Coerce(Kind), probatio.In(CHART_KINDS)
        ),
    }
)
@websocket_api.async_response
async def ws_charts(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send the most played songs or albums of the storefront."""

    async def fetch(catalog: AppleMusicCatalog) -> dict[str, list[CatalogItem]]:
        return {"items": await catalog.chart(msg["media_type"])}

    await _async_send(hass, connection, msg, fetch)


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "apple_music/album",
        probatio.Required("album_id"): str,
    }
)
@websocket_api.async_response
async def ws_album(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send the songs on an album."""

    async def fetch(catalog: AppleMusicCatalog) -> dict[str, list[CatalogItem]]:
        return {"songs": await catalog.album_songs(msg["album_id"])}

    await _async_send(hass, connection, msg, fetch)


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "apple_music/artist",
        probatio.Required("artist_id"): str,
    }
)
@websocket_api.async_response
async def ws_artist(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send the top songs and the albums of an artist."""

    async def fetch(catalog: AppleMusicCatalog) -> dict[str, list[CatalogItem]]:
        songs, albums = await asyncio.gather(
            catalog.artist_songs(msg["artist_id"], 10),
            catalog.artist_albums(msg["artist_id"]),
        )
        return {"songs": songs, "albums": albums}

    await _async_send(hass, connection, msg, fetch)


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "apple_music/search",
        probatio.Required("query"): str,
    }
)
@websocket_api.async_response
async def ws_search(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send the songs, albums, artists and playlists matching a search.

    The playlists come from Music Assistant, none without it.
    """

    async def fetch(catalog: AppleMusicCatalog) -> dict[str, list[CatalogItem]]:
        songs, albums, artists, playlists = await asyncio.gather(
            *(
                catalog.search(msg["query"], kind, SEARCH_LIMIT)
                for kind in (Kind.SONG, Kind.ALBUM, Kind.ARTIST)
            ),
            music_assistant.async_search_playlists(hass, msg["query"], SEARCH_LIMIT),
        )
        return {
            "songs": songs,
            "albums": albums,
            "artists": artists,
            "playlists": playlists,
        }

    await _async_send(hass, connection, msg, fetch)


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "apple_music/playlists",
        probatio.Required("entity_id"): cv.entity_id,
    }
)
@websocket_api.async_response
async def ws_playlists(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send the Apple Music playlists in the Sonos favorites of a speaker."""
    if not is_sonos_player(hass, msg["entity_id"]):
        connection.send_error(
            msg["id"], "not_sonos", f"{msg['entity_id']} is not a Sonos speaker"
        )
        return

    async def fetch(_catalog: AppleMusicCatalog) -> dict[str, list[CatalogItem]]:
        return {"items": await sonos.async_playlists(hass, msg["entity_id"])}

    await _async_send(hass, connection, msg, fetch)
