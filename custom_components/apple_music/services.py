"""Actions to search Apple Music and play it on Sonos speakers."""

from __future__ import annotations

from contextlib import suppress

import probatio
from homeassistant.components.media_player import (
    ATTR_MEDIA_ENQUEUE,
    MediaPlayerEnqueue,
)
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

from . import sonos
from .api import AppleMusicCatalog, AppleMusicError, CatalogItem, parse_url
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


async def _async_from_url(catalog: AppleMusicCatalog, url: str) -> CatalogItem:
    """Return the song, album or playlist an Apple Music link points to."""
    if (parsed := parse_url(url)) is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_url",
            translation_placeholders={"url": url},
        )
    kind, item_id = parsed
    if kind == Kind.SONG:
        # The title, artist and album show in the Sonos queue, but are not required.
        with suppress(AppleMusicError):
            if song := await catalog.song(item_id):
                return song
    return CatalogItem(kind=kind, id=item_id, name="")


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

        if url := call.data.get(ATTR_URL):
            items = [await _async_from_url(catalog, url)]
        else:
            items = await _async_find(
                catalog,
                call.data[ATTR_QUERY],
                call.data[ATTR_KIND],
                call.data[ATTR_LIMIT],
            )

        await sonos.async_play(hass, players, items, call.data[ATTR_MEDIA_ENQUEUE])
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
