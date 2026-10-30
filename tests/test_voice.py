"""Tests for playing Apple Music on Sonos speakers by voice."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from homeassistant.components import conversation
from homeassistant.components.homeassistant.exposed_entities import (
    async_expose_entity,
)
from homeassistant.core import Context
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.apple_music.const import SEARCH_URL
from custom_components.apple_music.voice import async_get_targets

from .conftest import GROUPED_PLAYER, SONOS_PLAYER

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

SANTE = "x-sonos-http:song%3a1589216089.mp4?sid=204&flags=8232&sn=28"
YELLOW = "x-sonos-http:song%3a1122782283.mp4?sid=204&flags=8232&sn=28"
PARACHUTES = "x-rincon-cpcontainer:1004206calbum%3a1122782080?sid=204&flags=8300&sn=28"
CURRENT_PLAYLIST = (
    "x-rincon-cpcontainer:1006206cplaylist%3apl.bbb?sid=204&flags=8300&sn=28"
)


async def _settle(hass: HomeAssistant) -> None:
    """Let the voice commands follow a change of speakers or areas."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
    await hass.async_block_till_done()


async def _say(hass: HomeAssistant, text: str, language: str = "nl") -> str:
    """Say a sentence to Assist and return its answer."""
    result = await conversation.async_converse(
        hass, text, None, Context(), language=language
    )
    speech: str = result.response.speech["plain"]["speech"]
    return speech


def _queued(soco: MagicMock) -> list[str]:
    """Return the URIs added to the Sonos queue."""
    return [
        dict(args[0])["EnqueuedURI"]
        for args, _ in soco.avTransport.AddURIToQueue.call_args_list
    ]


@pytest.mark.usefixtures("voice")
def test_targets(hass: HomeAssistant) -> None:
    """Test the speakers are called by their own names and their area's names."""
    targets = async_get_targets(hass, "conversation")

    assert [(t.name, t.area, t.entity_ids, t.names) for t in targets] == [
        ("Keuken", False, (SONOS_PLAYER,), ("Keuken",)),
        ("Leefruimte", True, (GROUPED_PLAYER,), ("Leefruimte", "Living")),
        ("Woonkamer", False, (GROUPED_PLAYER,), ("Woonkamer",)),
    ]


@pytest.mark.usefixtures("voice")
@pytest.mark.parametrize(
    ("sentence", "answer", "first"),
    [
        (
            "speel Stromae op de keuken",
            "Ik speel nummers van Stromae op Keuken.",
            SANTE,
        ),
        (
            "speel parachutes in de leefruimte",
            "Ik speel Parachutes van Coldplay in Leefruimte.",
            PARACHUTES,
        ),
        (
            "speel yellow van coldplay in living",
            "Ik speel Yellow van Coldplay in Leefruimte.",
            YELLOW,
        ),
        (
            "speel het nummer yellow af op keuken",
            "Ik speel Yellow van Coldplay op Keuken.",
            YELLOW,
        ),
        (
            "speel de afspeellijst current account op keuken",
            "Ik speel de afspeellijst Current account playlist op Keuken.",
            CURRENT_PLAYLIST,
        ),
        (
            "speel muziek van stromae in de leefruimte af",
            "Ik speel nummers van Stromae in Leefruimte.",
            SANTE,
        ),
    ],
)
async def test_play(
    hass: HomeAssistant, soco: MagicMock, sentence: str, answer: str, first: str
) -> None:
    """Test a sentence plays the best match, replacing the queue."""
    assert await _say(hass, sentence) == answer

    soco.clear_queue.assert_called_once()
    assert _queued(soco)[0] == first
    soco.play_from_queue.assert_called_once_with(0)


@pytest.mark.usefixtures("voice")
async def test_play_in_english(hass: HomeAssistant, soco: MagicMock) -> None:
    """Test the English sentences and answers."""
    answer = await _say(hass, "play stromae on the keuken", language="en")

    assert answer == "Playing songs by Stromae on Keuken."
    assert _queued(soco)[0] == SANTE


@pytest.mark.usefixtures("voice")
async def test_nothing_found(
    hass: HomeAssistant, soco: MagicMock, mock_catalog: AiohttpClientMocker
) -> None:
    """Test Assist says so when Apple Music has nothing."""
    mock_catalog.clear_requests()
    mock_catalog.get(SEARCH_URL, json={"resultCount": 0, "results": []})

    answer = await _say(hass, "speel qwxz in de keuken")

    assert answer == "Ik vond niets op Apple Music voor qwxz."
    soco.clear_queue.assert_not_called()


@pytest.mark.usefixtures("voice")
async def test_sonos_error(hass: HomeAssistant, soco: MagicMock) -> None:
    """Test Assist says so when the speaker cannot play."""
    soco.avTransport.AddURIToQueue.side_effect = OSError("UPnP Error 800")

    answer = await _say(hass, "speel stromae in de keuken")

    assert answer.startswith("Dat lukte niet: ")


@pytest.mark.usefixtures("voice")
async def test_hidden_speaker(hass: HomeAssistant, soco: MagicMock) -> None:
    """Test speakers hidden from Assist are left to Home Assistant's sentences."""
    async_expose_entity(hass, "conversation", SONOS_PLAYER, should_expose=False)
    await _settle(hass)

    answer = await _say(hass, "speel stromae op de keuken")

    assert not answer.startswith("Ik speel")
    soco.clear_queue.assert_not_called()


async def test_area_plays_together(
    hass: HomeAssistant, soco: MagicMock, voice: ar.AreaEntry
) -> None:
    """Test the speakers of an area are grouped before they play."""
    calls = async_mock_service(hass, "media_player", "join")
    er.async_get(hass).async_update_entity(SONOS_PLAYER, area_id=voice.id)
    await _settle(hass)

    answer = await _say(hass, "speel stromae in de leefruimte")

    assert answer == "Ik speel nummers van Stromae in Leefruimte."
    assert calls[0].data == {
        "entity_id": SONOS_PLAYER,
        "group_members": [GROUPED_PLAYER],
    }
    assert _queued(soco)[0] == SANTE


async def test_unload(
    hass: HomeAssistant,
    soco: MagicMock,
    voice: ar.AreaEntry,
    config_entry: MockConfigEntry,
) -> None:
    """Test the sentences stop working when Apple Music is unloaded."""
    assert voice
    await hass.config_entries.async_unload(config_entry.entry_id)

    await _say(hass, "speel stromae op de keuken")

    soco.clear_queue.assert_not_called()
