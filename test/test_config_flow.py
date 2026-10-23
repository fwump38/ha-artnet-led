"""Config flow, YAML import and entry setup/unload."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from pyartnet.errors import UniverseNotFoundError

from custom_components.artnet_led.const import DOMAIN

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def _enable(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def fake_node():
    """Never open a real socket: the entry gets a fake node whose universes hand out mock channels."""
    node = MagicMock()
    node.__aexit__ = AsyncMock()
    node.get_universe.side_effect = UniverseNotFoundError
    channel = node.add_universe.return_value.add_channel.return_value
    channel._start, channel._width, channel.get_values.return_value = 1, 1, [0]
    with patch("custom_components.artnet_led._create_node", AsyncMock(return_value=node)):
        yield node


NODE = {"node_type": "artnet-direct", "host": "192.168.1.10", "max_fps": 25, "refresh_every": 120,
        "send_partial_universe": True}


async def test_user_flow_creates_entry(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], NODE)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == "192.168.1.10"

    again = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    again = await hass.config_entries.flow.async_configure(again["flow_id"], NODE)
    assert again["type"] is FlowResultType.ABORT


async def test_host_required_unless_controller(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**NODE, "host": ""})
    assert result["errors"] == {"host": "host_required"}


YAML = {
    "host": "192.168.1.10", "node_type": "artnet-direct", "max_fps": 25, "refresh_every": 120,
    "universes": {0: {"send_partial_universe": True, "output_correction": "quadratic", "devices": [
        {"channel": 1, "name": "Desk", "type": "dimmer", "transition": 1, "output_correction": None,
         "channel_size": "8bit", "byte_order": "big", "min_temp": "2700K", "max_temp": "6500K",
         "channel_setup": None},
        {"channel": 50, "name": "Fixed", "type": "fixed", "transition": 0, "output_correction": "cubic",
         "channel_size": "8bit", "byte_order": "big", "min_temp": "2700K", "max_temp": "6500K",
         "channel_setup": [255, 10]},
    ]}},
}


async def test_yaml_import(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data=YAML)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    lights = {s.data["name"]: s.data for s in entry.subentries.values()}
    assert lights["Desk"]["output_correction"] == "quadratic"  # inherited from the universe
    assert lights["Fixed"]["output_correction"] == "cubic"
    assert lights["Fixed"]["channel_setup"] == "255,10"


async def test_entry_creates_lights_and_unloads(hass, fake_node):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data=YAML)
    entry = result["result"]
    await hass.async_block_till_done()

    assert hass.states.get("light.desk") is not None
    assert hass.states.get("light.fixed") is not None

    universe = fake_node.add_universe.return_value
    assert universe.add_channel.call_count == 2

    assert await hass.config_entries.async_unload(entry.entry_id)
    fake_node.__aexit__.assert_awaited_once()
    await hass.async_block_till_done()


async def test_reconfigure_clears_optional_fields(hass):
    """Emptying channel_setup/output_correction while reconfiguring must remove the stored value."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data=YAML)
    entry = result["result"]
    await hass.async_block_till_done()
    desk = next(s for s in entry.subentries.values() if s.data["name"] == "Desk")
    hass.config_entries.async_update_subentry(
        entry, desk, data={**desk.data, "type": "rgbw", "channel_setup": "uUd", "output_correction": "cubic"})
    await hass.async_block_till_done()

    flow = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "light"), context={"source": "reconfigure", "subentry_id": desk.subentry_id})
    flow = await hass.config_entries.subentries.async_configure(
        flow["flow_id"], {"name": "Desk", "type": "rgbw", "universe": 0, "channel": 1})
    assert flow["step_id"] == "details"
    flow = await hass.config_entries.subentries.async_configure(
        flow["flow_id"], {"transition": 0, "channel_size": "8bit", "byte_order": "big"})
    assert flow["type"] is FlowResultType.ABORT

    data = entry.subentries[desk.subentry_id].data
    assert "channel_setup" not in data
    assert "output_correction" not in data
