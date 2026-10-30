"""Tests for serving the Apple Music card."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from homeassistant.setup import async_setup_component

from custom_components.apple_music.card import CARD_URL
from custom_components.apple_music.const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.typing import ClientSessionGenerator


async def test_card(hass: HomeAssistant, hass_client: ClientSessionGenerator) -> None:
    """Test the card is served and added to the frontend."""
    hass.config.components.add("frontend")
    with patch("custom_components.apple_music.card.add_extra_js_url") as add_js:
        assert await async_setup_component(hass, DOMAIN, {})

    url = add_js.call_args.args[1]
    assert url.startswith(f"{CARD_URL}?v=")
    response = await (await hass_client()).get(url)
    assert response.status == 200
    assert 'customElements.define("apple-music-card"' in await response.text()


async def test_no_card_without_frontend(hass: HomeAssistant) -> None:
    """Test the card is left out when the frontend is not used."""
    with patch("custom_components.apple_music.card.add_extra_js_url") as add_js:
        assert await async_setup_component(hass, DOMAIN, {})

    add_js.assert_not_called()
