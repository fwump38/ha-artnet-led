"""ARTNET LED"""
from __future__ import annotations

import asyncio
import logging

import pyartnet
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.typing import ConfigType
from pyartnet.base import BaseNode
from pyartnet.base.network import UnicastNetworkTarget

from custom_components.artnet_led.const import *

log = logging.getLogger(__name__)

PLATFORMS = [Platform.LIGHT]

type ArtNetConfigEntry = ConfigEntry[BaseNode]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ArtNetConfigEntry) -> bool:
    # pyartnet expects the created asyncio task to be the task running its wrapper.
    # Home Assistant's task factory can wrap tasks, which breaks pyartnet's assertions.
    pyartnet.base.background_task.CREATE_TASK = asyncio.create_task

    entry.runtime_data = await _create_node(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Reload when the node settings or any of its lights change.
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ArtNetConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    node = entry.runtime_data
    if entry.data.get(CONF_NODE_TYPE) == NODE_TYPE_CONTROLLER:
        node.stop()
    else:
        await node.__aexit__(None, None, None)
    return True


async def _async_reload(hass: HomeAssistant, entry: ArtNetConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def _create_node(hass: HomeAssistant, entry: ArtNetConfigEntry) -> BaseNode:
    data = entry.data
    client_type = data.get(CONF_NODE_TYPE, DEFAULT_NODE_TYPE)
    max_fps = data.get(CONF_NODE_MAX_FPS, DEFAULT_MAX_FPS)
    refresh_interval = data.get(CONF_NODE_REFRESH, DEFAULT_REFRESH)

    if client_type == NODE_TYPE_CONTROLLER:
        # Imported here as it needs netifaces, which the other protocols don't.
        from custom_components.artnet_led.bridge.artnet_controller import ArtNetController
        node = ArtNetController(hass, max_fps=max_fps, refresh_every=refresh_interval)
        node.start()
        return node

    real_host = data.get(CONF_NODE_HOST_OVERRIDE) or data[CONF_NODE_HOST]
    real_port = data.get(CONF_NODE_PORT)

    if client_type == "artnet-direct":
        target = UnicastNetworkTarget.create(real_host, real_port or ARTNET_DEFAULT_PORT)
        node = pyartnet.ArtNetNode(target, max_fps=max_fps, refresh_every=refresh_interval)
    elif client_type == "sacn":
        target = UnicastNetworkTarget.create(real_host, real_port or SACN_DEFAULT_PORT)
        node = pyartnet.SacnNode(target, max_fps=max_fps, refresh_every=refresh_interval,
                                 source_name="ha-artnet-led")
    elif client_type == "kinet":
        target = UnicastNetworkTarget.create(real_host, real_port or KINET_DEFAULT_PORT)
        node = pyartnet.KiNetNode(target, max_fps=max_fps, refresh_every=refresh_interval)
    else:
        raise ConfigEntryError(f"Unknown client type '{client_type}'")

    await node.__aenter__()
    if not refresh_interval:
        await node.stop_refresh()
    return node
