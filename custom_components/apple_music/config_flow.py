"""Config flow for the Apple Music integration."""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import CountrySelector

from .api import AppleMusicCatalog, AppleMusicError
from .const import CONF_STOREFRONT, DOMAIN, Kind


class AppleMusicConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up Apple Music for a storefront."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the storefront, the country of the Apple Music account."""
        errors: dict[str, str] = {}
        if user_input is not None:
            storefront = user_input[CONF_STOREFRONT].lower()
            catalog = AppleMusicCatalog(async_get_clientsession(self.hass), storefront)
            try:
                await catalog.search("a", Kind.SONG, limit=1)
            except AppleMusicError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Apple Music ({storefront.upper()})",
                    data={CONF_STOREFRONT: storefront},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        CONF_STOREFRONT, default=self.hass.config.country or "US"
                    ): CountrySelector(),
                }
            ),
            errors=errors,
        )
