"""LLM tool that plays Apple Music on Sonos speakers, for AI conversation agents.

The sentence triggers of the voice module only understand set sentences. An AI
agent with this tool also plays music for sentences in other words.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

import probatio
from homeassistant.components.llm import LLMTools
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.llm import (
    LLM_API_ASSIST,
    LLMContext,
    Tool,
    ToolAnnotations,
    ToolInput,
    ToolResult,
)

from .const import DOMAIN, Kind
from .helpers import get_catalog
from .voice import (
    NothingFoundError,
    Target,
    async_find_music,
    async_get_targets,
    async_play_music,
)

if TYPE_CHECKING:
    from .api import AppleMusicCatalog


class PlayMusicTool(Tool):
    """Play a song, an album, an artist or a playlist on Sonos speakers."""

    name = f"{DOMAIN}__play"
    title = "Play Apple Music"
    annotations = ToolAnnotations(idempotent=True)
    integration = DOMAIN

    def __init__(self, catalog: AppleMusicCatalog, targets: list[Target]) -> None:
        """Initialize the tool for the Sonos speakers exposed to the assistant."""
        self._catalog = catalog
        self._targets = targets
        names = ", ".join(sorted({name for t in targets for name in t.names}))
        self.description = (
            "Plays music from Apple Music on Sonos speakers, replacing what plays: "
            "a song, an album, the most popular songs of an artist, or a playlist "
            "from the Sonos favorites. Use it whenever music should play. "
            f"The speakers and areas to play in are: {names}."
        )
        self.parameters = probatio.Schema(
            {
                probatio.Required(
                    "query",
                    description=(
                        "What to play: a song, album, artist or playlist name. "
                        "Add the artist to a song or album, like 'Yellow Coldplay'."
                    ),
                ): cv.string,
                probatio.Optional(
                    "media_type",
                    description="song, album, artist or playlist. Leave it out "
                    "to play the best match.",
                ): probatio.In([kind.value for kind in Kind]),
                probatio.Optional(
                    "player",
                    description="The speaker or area to play in. Leave it out to "
                    "play in the area of the device the user speaks to.",
                ): cv.string,
            }
        )

    @callback
    def _async_target(
        self, hass: HomeAssistant, player: str | None, device_id: str | None
    ) -> Target:
        """Return the target named player, or of the area of the device."""
        if (
            player is None
            and device_id
            and (device := dr.async_get(hass).async_get(device_id))
        ):
            area_id = dr.async_get_effective_area_id(hass, device)
            if area_id and (area := ar.async_get(hass).async_get_area(area_id)):
                player = area.name
        if player is not None:
            if target := next((t for t in self._targets if t.matches(player)), None):
                return target
            msg = f"There is no Sonos speaker or area called {player}."
        else:
            msg = "Say which speaker or area to play in."
        raise HomeAssistantError(msg)

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> ToolResult:
        """Play the best match for the query."""
        args: dict[str, Any] = self.parameters(tool_input.tool_args)
        target = self._async_target(hass, args.get("player"), llm_context.device_id)
        kind = Kind(args["media_type"]) if "media_type" in args else None
        try:
            music = await async_find_music(
                hass, self._catalog, args["query"], target.entity_ids[0], kind
            )
        except NothingFoundError as err:
            msg = f"Nothing found on Apple Music for {args['query']}."
            raise HomeAssistantError(msg) from err
        await async_play_music(hass, target, music)
        return ToolResult(
            data={
                "playing": music.describe("en"),
                "media_type": music.kind.value,
                "in": target.name,
            }
        )


@callback
def async_get_tools(
    hass: HomeAssistant, llm_context: LLMContext, api_id: str
) -> LLMTools | None:
    """Return the play tool when Sonos speakers are exposed to the assistant."""
    if (
        api_id != LLM_API_ASSIST
        or not llm_context.assistant
        or (catalog := get_catalog(hass)) is None
    ):
        return None
    if not (targets := async_get_targets(hass, llm_context.assistant)):
        return None
    return LLMTools(tools=[PlayMusicTool(catalog, targets)])
