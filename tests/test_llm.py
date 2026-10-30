"""Tests for the tool that lets AI conversation agents play Apple Music."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.llm import (
    LLM_API_ASSIST,
    LLMContext,
    Tool,
    ToolInput,
    ToolResult,
)

from custom_components.apple_music.llm import async_get_tools

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import area_registry as ar
    from pytest_homeassistant_custom_component.common import MockConfigEntry

PARACHUTES = "x-rincon-cpcontainer:1004206calbum%3a1122782080?sid=204&flags=8300&sn=28"

pytestmark = pytest.mark.usefixtures("voice")


def _context(
    device_id: str | None = None, assistant: str = "conversation"
) -> LLMContext:
    """Return the context of a request to an AI agent."""
    return LLMContext(
        platform="openai_conversation",
        context=Context(),
        language="nl",
        assistant=assistant,
        device_id=device_id,
    )


def _tool(hass: HomeAssistant, context: LLMContext) -> Tool:
    """Return the play tool."""
    tools = async_get_tools(hass, context, LLM_API_ASSIST)
    assert tools is not None
    return tools.tools[0]


async def test_play(hass: HomeAssistant, soco: MagicMock) -> None:
    """Test the agent plays the best match in an area."""
    context = _context()
    tool = _tool(hass, context)

    result = await tool.async_call(
        hass,
        ToolInput(tool.name, {"query": "Parachutes", "player": "living"}),
        context,
    )

    assert isinstance(result, ToolResult)
    assert tool.name == "apple_music__play"
    assert "Keuken, Leefruimte, Living, Woonkamer" in (tool.description or "")
    assert result.data == {
        "playing": "Parachutes by Coldplay",
        "media_type": "album",
        "in": "Leefruimte",
    }
    assert dict(soco.avTransport.AddURIToQueue.call_args.args[0])["EnqueuedURI"] == (
        PARACHUTES
    )


async def test_play_where_spoken(
    hass: HomeAssistant,
    soco: MagicMock,
    voice: ar.AreaEntry,
    config_entry: MockConfigEntry,
) -> None:
    """Test the agent plays in the area of the voice satellite."""
    satellite = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={("test", "satellite")}
    )
    dr.async_get(hass).async_update_device(satellite.id, area_id=voice.id)
    context = _context(satellite.id)
    tool = _tool(hass, context)

    result = await tool.async_call(
        hass,
        ToolInput(tool.name, {"query": "Stromae", "media_type": "artist"}),
        context,
    )

    assert isinstance(result, ToolResult)
    assert result.data["in"] == "Leefruimte"
    soco.play_from_queue.assert_called_once_with(0)


@pytest.mark.parametrize(
    ("args", "error"),
    [
        ({"query": "Stromae", "player": "zolder"}, "no Sonos speaker or area"),
        ({"query": "Stromae"}, "Say which speaker"),
    ],
)
async def test_no_speaker(
    hass: HomeAssistant, soco: MagicMock, args: dict[str, str], error: str
) -> None:
    """Test the agent hears which speakers and areas there are."""
    context = _context()
    tool = _tool(hass, context)

    with pytest.raises(HomeAssistantError, match=error):
        await tool.async_call(hass, ToolInput(tool.name, args), context)
    soco.clear_queue.assert_not_called()


def test_no_tool_without_speakers(hass: HomeAssistant) -> None:
    """Test there is no tool for an assistant without Sonos speakers."""
    assert async_get_tools(hass, _context(assistant="cloud.alexa"), "assist") is None
    assert async_get_tools(hass, _context(), "other_api") is None
