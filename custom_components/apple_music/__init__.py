"""Search Apple Music and play it on Sonos speakers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AppleMusicCatalog
from .card import async_register_card
from .const import CONF_STOREFRONT, DOMAIN
from .services import async_setup_services
from .websocket import async_register_commands

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

type AppleMusicConfigEntry = ConfigEntry[AppleMusicCatalog]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:  # noqa: ARG001 # pylint: disable=unused-argument
    """Register the Apple Music actions and the dashboard card."""
    async_setup_services(hass)
    async_register_commands(hass)
    # The frontend is set up first when it is used, the card is of no use without it.
    if "frontend" in hass.config.components:
        await async_register_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AppleMusicConfigEntry) -> bool:
    """Set up Apple Music from a config entry."""
    entry.runtime_data = AppleMusicCatalog(
        async_get_clientsession(hass), entry.data[CONF_STOREFRONT]
    )
    return True


async def async_unload_entry(  # pylint: disable=unused-argument
    hass: HomeAssistant,  # noqa: ARG001
    entry: AppleMusicConfigEntry,  # noqa: ARG001
) -> bool:
    """Unload a config entry."""
    return True
