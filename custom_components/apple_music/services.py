"""Actions to search Apple Music and play it on Sonos speakers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import probatio
from homeassistant.components.media_player import (
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_CONTENT_TYPE,
    ATTR_MEDIA_ENQUEUE,
    SERVICE_PLAY_MEDIA,
    MediaPlayerEnqueue,
    MediaType,
)
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_extract_entity_ids

from .api import AppleMusicCatalog, AppleMusicError, CatalogItem, is_playable_url
from .const import (
    ATTR_KIND,
    ATTR_LIMIT,
    ATTR_QUERY,
    ATTR_URL,
    DOMAIN,
    SEARCHABLE_KINDS,
    SERVICE_PLAY,
    SERVICE_SEARCH,
    Kind,
)
from .helpers import get_catalog, is_sonos_player

if TYPE_CHECKING:
    from homeassistant.core import Context

_LIMIT = probatio.All(probatio.Coerce(int), probatio.Range(min=1, max=50))

PLAY_SCHEMA = probatio.All(
    cv.make_entity_service_schema(
        {
            probatio.Exclusive(ATTR_QUERY, "what"): cv.string,
            probatio.Exclusive(ATTR_URL, "what"): cv.string,
            probatio.Optional(ATTR_KIND, default=Kind.SONG): probatio.Coerce(Kind),
            probatio.Optional(ATTR_LIMIT, default=20): _LIMIT,
            probatio.Optional(
                ATTR_MEDIA_ENQUEUE, default=MediaPlayerEnqueue.REPLACE
            ): probatio.Coerce(MediaPlayerEnqueue),
        }
    ),
    cv.has_at_least_one_key(ATTR_QUERY, ATTR_URL),
)

SEARCH_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_QUERY): cv.string,
        probatio.Optional(ATTR_KIND, default=Kind.SONG): probatio.All(
            probatio.Coerce(Kind), probatio.In(SEARCHABLE_KINDS)
        ),
        probatio.Optional(ATTR_LIMIT, default=10): _LIMIT,
    }
)


def _catalog(hass: HomeAssistant) -> AppleMusicCatalog:
    """Return the catalog, or raise when Apple Music is not set up."""
    if (catalog := get_catalog(hass)) is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_loaded"
        )
    return catalog


async def _async_find(
    catalog: AppleMusicCatalog, query: str, kind: Kind, limit: int
) -> list[CatalogItem]:
    """Return the songs to play for a song, album or artist query."""
    if kind not in SEARCHABLE_KINDS:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="not_searchable",
            translation_placeholders={"media_type": kind},
        )
    try:
        found = (await catalog.search(query, kind, limit=1))[:1]
        if found and kind == Kind.ARTIST:
            found = await catalog.artist_songs(found[0].id, limit)
    except AppleMusicError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="request_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    if not found:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_results",
            translation_placeholders={"query": query},
        )
    return found


def _queue_steps(
    urls: list[str], enqueue: MediaPlayerEnqueue
) -> list[tuple[str, MediaPlayerEnqueue]]:
    """Return the play_media calls that queue urls in order.

    Sonos inserts "next" items right after the current one, so those go in reverse.
    Nothing changes the current item before the last step, so positions stay valid.
    """
    first, rest = urls[0], urls[1:]
    match enqueue:
        case MediaPlayerEnqueue.REPLACE:
            return [(first, enqueue), *((url, MediaPlayerEnqueue.ADD) for url in rest)]
        case MediaPlayerEnqueue.ADD:
            return [(url, enqueue) for url in urls]
        case MediaPlayerEnqueue.NEXT:
            return [(url, enqueue) for url in reversed(urls)]
        case _:
            return [
                *((url, MediaPlayerEnqueue.NEXT) for url in reversed(rest)),
                (first, MediaPlayerEnqueue.PLAY),
            ]


async def _async_play_urls(
    hass: HomeAssistant,
    entity_ids: list[str],
    urls: list[str],
    enqueue: MediaPlayerEnqueue,
    context: Context,
) -> None:
    """Play Apple Music links on Sonos speakers."""
    for url, step in _queue_steps(urls, enqueue):
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_PLAY_MEDIA,
            {
                ATTR_ENTITY_ID: entity_ids,
                ATTR_MEDIA_CONTENT_ID: url,
                ATTR_MEDIA_CONTENT_TYPE: MediaType.MUSIC,
                ATTR_MEDIA_ENQUEUE: step,
            },
            blocking=True,
            context=context,
        )


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the Apple Music actions."""

    async def async_play(call: ServiceCall) -> ServiceResponse:
        """Play a song, album, artist or Apple Music link on Sonos speakers."""
        catalog = _catalog(hass)
        players = sorted(
            entity_id
            for entity_id in await async_extract_entity_ids(call)
            if is_sonos_player(hass, entity_id)
        )
        if not players:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_sonos_players"
            )

        items: list[CatalogItem] = []
        if url := call.data.get(ATTR_URL):
            if not is_playable_url(url):
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_url",
                    translation_placeholders={"url": url},
                )
            urls = [url]
        else:
            items = await _async_find(
                catalog,
                call.data[ATTR_QUERY],
                call.data[ATTR_KIND],
                call.data[ATTR_LIMIT],
            )
            urls = [item.url(catalog.storefront) for item in items]

        await _async_play_urls(
            hass, players, urls, call.data[ATTR_MEDIA_ENQUEUE], call.context
        )
        if not call.return_response:
            return None
        return {"items": [item.as_dict(catalog.storefront) for item in items]}

    async def async_search(call: ServiceCall) -> ServiceResponse:
        """Search the Apple Music catalog."""
        catalog = _catalog(hass)
        try:
            items = await catalog.search(
                call.data[ATTR_QUERY], call.data[ATTR_KIND], call.data[ATTR_LIMIT]
            )
        except AppleMusicError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="request_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        return {"items": [item.as_dict(catalog.storefront) for item in items]}

    hass.services.async_register(
        DOMAIN,
        SERVICE_PLAY,
        async_play,
        schema=PLAY_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEARCH,
        async_search,
        schema=SEARCH_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
