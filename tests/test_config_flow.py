"""Tests for the Apple Music config flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.apple_music.const import CONF_STOREFRONT, DOMAIN, SEARCH_URL

from . import load_json

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )


async def test_user_flow(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test setting up Apple Music for a storefront."""
    hass.config.country = "BE"
    aioclient_mock.get(SEARCH_URL, json=load_json("search_song.json"))

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["data_schema"] is not None
    assert result["data_schema"]({})[CONF_STOREFRONT] == "BE"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_STOREFRONT: "BE"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Apple Music (BE)"
    assert result["data"] == {CONF_STOREFRONT: "be"}
    assert aioclient_mock.mock_calls[0][1].query["country"] == "be"


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the form shows an error when Apple Music cannot be reached."""
    aioclient_mock.get(SEARCH_URL, status=503)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_STOREFRONT: "NL"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(SEARCH_URL, json=load_json("search_song.json"))
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_STOREFRONT: "NL"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_STOREFRONT: "nl"}


async def test_single_instance(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Test Apple Music can only be set up once."""
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
