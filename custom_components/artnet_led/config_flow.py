"""Config flow: one config entry per node, one `light` subentry per DMX light."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from custom_components.artnet_led.const import *
from custom_components.artnet_led.light import parse_channel_setup
from custom_components.artnet_led.util.channel_switch import IllegalChannelSetup, validate


def _select(options: list[str], key: str) -> selector.SelectSelector:
    return selector.SelectSelector(selector.SelectSelectorConfig(
        options=options, mode=selector.SelectSelectorMode.DROPDOWN, translation_key=key))


def _number(**kwargs) -> selector.NumberSelector:
    return selector.NumberSelector(selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX, **kwargs))


def _node_schema(defaults: dict[str, Any], with_type: bool) -> vol.Schema:
    schema: dict[Any, Any] = {}
    if with_type:
        schema[vol.Required(CONF_NODE_TYPE, default=defaults.get(CONF_NODE_TYPE, DEFAULT_NODE_TYPE))] = \
            _select(NODE_TYPES, CONF_NODE_TYPE)
    schema.update({
        vol.Optional(CONF_NODE_HOST, description={"suggested_value": defaults.get(CONF_NODE_HOST)}): str,
        vol.Optional(CONF_NODE_PORT, description={"suggested_value": defaults.get(CONF_NODE_PORT)}):
            _number(min=1, max=65535),
        vol.Optional(CONF_NODE_HOST_OVERRIDE, description={"suggested_value": defaults.get(CONF_NODE_HOST_OVERRIDE)}):
            str,
        vol.Required(CONF_NODE_MAX_FPS, default=defaults.get(CONF_NODE_MAX_FPS, DEFAULT_MAX_FPS)):
            _number(min=1, max=50),
        vol.Required(CONF_NODE_REFRESH, default=defaults.get(CONF_NODE_REFRESH, DEFAULT_REFRESH)):
            _number(min=0, max=9999, unit_of_measurement="s"),
        vol.Required(CONF_SEND_PARTIAL_UNIVERSE, default=defaults.get(CONF_SEND_PARTIAL_UNIVERSE, True)):
            selector.BooleanSelector(),
    })
    return vol.Schema(schema)


def _clean_node_input(user_input: dict[str, Any]) -> dict[str, Any]:
    data = dict(user_input)
    data[CONF_NODE_HOST] = (data.get(CONF_NODE_HOST) or "").strip()
    data[CONF_NODE_MAX_FPS] = int(data[CONF_NODE_MAX_FPS])
    data[CONF_NODE_REFRESH] = float(data[CONF_NODE_REFRESH])
    if data.get(CONF_NODE_PORT) is not None:
        data[CONF_NODE_PORT] = int(data[CONF_NODE_PORT])
    for key in (CONF_NODE_PORT, CONF_NODE_HOST_OVERRIDE):
        if data.get(key) in (None, ""):
            data.pop(key, None)
    return data


def _validate_node(data: dict[str, Any]) -> dict[str, str]:
    if data[CONF_NODE_TYPE] != NODE_TYPE_CONTROLLER and not data[CONF_NODE_HOST]:
        return {CONF_NODE_HOST: "host_required"}
    return {}


def _node_unique_id(data: dict[str, Any]) -> str:
    if data[CONF_NODE_TYPE] == NODE_TYPE_CONTROLLER:
        return NODE_TYPE_CONTROLLER
    return f"{data[CONF_NODE_TYPE]}:{data[CONF_NODE_HOST]}"


def _node_title(data: dict[str, Any]) -> str:
    return "Art-Net controller" if data[CONF_NODE_TYPE] == NODE_TYPE_CONTROLLER else data[CONF_NODE_HOST]


def _stringify_channel_setup(raw: Any) -> str | None:
    if isinstance(raw, list):
        return ",".join(str(c) for c in raw)
    return raw


class ArtNetConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_TYPE_LIGHT: LightSubentryFlow}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _clean_node_input(user_input)
            errors = _validate_node(data)
            if not errors:
                await self.async_set_unique_id(_node_unique_id(data))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=_node_title(data), data=data)

        return self.async_show_form(
            step_id="user", data_schema=_node_schema(user_input or {}, with_type=True), errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **_clean_node_input(user_input)}
            for key in (CONF_NODE_PORT, CONF_NODE_HOST_OVERRIDE):
                if key not in user_input:
                    data.pop(key, None)
            errors = _validate_node(data)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reconfigure", data_schema=_node_schema(user_input or dict(entry.data), with_type=False),
            errors=errors)

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Convert a legacy YAML platform block into a config entry with one subentry per light."""
        data = {
            CONF_NODE_TYPE: import_data.get(CONF_NODE_TYPE) or DEFAULT_NODE_TYPE,
            CONF_NODE_HOST: import_data[CONF_NODE_HOST],
            CONF_NODE_MAX_FPS: import_data.get(CONF_NODE_MAX_FPS, DEFAULT_MAX_FPS),
            CONF_NODE_REFRESH: import_data.get(CONF_NODE_REFRESH, DEFAULT_REFRESH),
        }
        if import_data.get(CONF_NODE_HOST_OVERRIDE):
            data[CONF_NODE_HOST_OVERRIDE] = import_data[CONF_NODE_HOST_OVERRIDE]
        port = import_data.get(CONF_NODE_PORT_OVERRIDE) or import_data.get(CONF_NODE_PORT)
        if port:
            data[CONF_NODE_PORT] = port

        await self.async_set_unique_id(_node_unique_id(data))
        self._abort_if_unique_id_configured()

        subentries = []
        send_partial = True
        for universe_nr, universe in import_data[CONF_NODE_UNIVERSES].items():
            send_partial = send_partial and universe.get(CONF_SEND_PARTIAL_UNIVERSE, True)
            for device in universe[CONF_DEVICES]:
                sub = {
                    CONF_DEVICE_UNIVERSE: int(universe_nr),
                    CONF_DEVICE_CHANNEL: device[CONF_DEVICE_CHANNEL],
                    CONF_DEVICE_NAME: device[CONF_DEVICE_NAME],
                    CONF_DEVICE_TYPE: device[CONF_DEVICE_TYPE],
                    CONF_DEVICE_TRANSITION: device.get(CONF_DEVICE_TRANSITION) or 0,
                    # Universe-level correction is the fallback for lights without their own.
                    CONF_OUTPUT_CORRECTION: device.get(CONF_OUTPUT_CORRECTION) or universe.get(CONF_OUTPUT_CORRECTION),
                    CONF_CHANNEL_SIZE: device.get(CONF_CHANNEL_SIZE) or "8bit",
                    CONF_BYTE_ORDER: device.get(CONF_BYTE_ORDER) or "big",
                    CONF_DEVICE_MIN_TEMP: device.get(CONF_DEVICE_MIN_TEMP) or DEFAULT_MIN_TEMP,
                    CONF_DEVICE_MAX_TEMP: device.get(CONF_DEVICE_MAX_TEMP) or DEFAULT_MAX_TEMP,
                    CONF_CHANNEL_SETUP: _stringify_channel_setup(device.get(CONF_CHANNEL_SETUP)),
                }
                subentries.append({
                    "subentry_type": SUBENTRY_TYPE_LIGHT,
                    "title": sub[CONF_DEVICE_NAME],
                    "unique_id": f"{universe_nr}/{sub[CONF_DEVICE_CHANNEL]}",
                    "data": {k: v for k, v in sub.items() if v is not None},
                })
        data[CONF_SEND_PARTIAL_UNIVERSE] = send_partial

        return self.async_create_entry(title=_node_title(data), data=data, subentries=subentries)


class LightSubentryFlow(ConfigSubentryFlow):
    """Add or edit one DMX light. Two steps: where it lives, then its details."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self._step_location("user", user_input, {})

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        current = dict(self._get_reconfigure_subentry().data)
        return await self._step_location("reconfigure", user_input, current)

    async def _step_location(self, step_id: str, user_input: dict[str, Any] | None,
                             current: dict[str, Any]) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        defaults = current
        if user_input is not None:
            self._data = {**current, **user_input}
            self._data[CONF_DEVICE_UNIVERSE] = int(self._data[CONF_DEVICE_UNIVERSE])
            self._data[CONF_DEVICE_CHANNEL] = int(self._data[CONF_DEVICE_CHANNEL])
            if self._is_taken(self._data[CONF_DEVICE_UNIVERSE], self._data[CONF_DEVICE_CHANNEL]):
                errors["base"] = "channel_in_use"
                defaults = user_input
            else:
                return await self.async_step_details()

        schema = vol.Schema({
            vol.Required(CONF_DEVICE_NAME, default=defaults.get(CONF_DEVICE_NAME, vol.UNDEFINED)): str,
            vol.Required(CONF_DEVICE_TYPE, default=defaults.get(CONF_DEVICE_TYPE, "dimmer")):
                _select(DEVICE_TYPES, CONF_DEVICE_TYPE),
            vol.Required(CONF_DEVICE_UNIVERSE, default=defaults.get(CONF_DEVICE_UNIVERSE, 0)):
                _number(min=0, max=32767),
            vol.Required(CONF_DEVICE_CHANNEL, default=defaults.get(CONF_DEVICE_CHANNEL, vol.UNDEFINED)):
                _number(min=1, max=512),
        })
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)

    def _is_taken(self, universe: int, channel: int) -> bool:
        """Only exact start-channel clashes are caught; overlapping widths are the user's call."""
        own_id = self._get_reconfigure_subentry().subentry_id if self.source == "reconfigure" else None
        return any(
            s.subentry_id != own_id
            and s.data.get(CONF_DEVICE_UNIVERSE) == universe and s.data.get(CONF_DEVICE_CHANNEL) == channel
            for s in self._get_entry().subentries.values()
        )

    async def async_step_details(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        device_type = self._data[CONF_DEVICE_TYPE]
        has_temp = device_type in TEMPERATURE_DEVICE_TYPES
        current = self._data

        if user_input is not None:
            data = {**self._data, **user_input}
            data[CONF_DEVICE_TRANSITION] = float(data[CONF_DEVICE_TRANSITION])
            if has_temp:
                data[CONF_DEVICE_MIN_TEMP] = f"{int(data[CONF_DEVICE_MIN_TEMP])}K"
                data[CONF_DEVICE_MAX_TEMP] = f"{int(data[CONF_DEVICE_MAX_TEMP])}K"
            else:
                data.pop(CONF_DEVICE_MIN_TEMP, None)
                data.pop(CONF_DEVICE_MAX_TEMP, None)
            for key in (CONF_OUTPUT_CORRECTION, CONF_CHANNEL_SETUP):
                if not data.get(key):
                    data.pop(key, None)

            setup = parse_channel_setup(data.get(CONF_CHANNEL_SETUP))
            if setup:
                try:
                    if device_type != "fixed":
                        validate(setup, device_type)
                except IllegalChannelSetup:
                    errors[CONF_CHANNEL_SETUP] = "invalid_channel_setup"

            if not errors:
                title = data[CONF_DEVICE_NAME]
                if self.source == "reconfigure":
                    return self.async_update_and_abort(
                        self._get_entry(), self._get_reconfigure_subentry(), title=title, data=data)
                return self.async_create_entry(
                    title=title, data=data, unique_id=f"{data[CONF_DEVICE_UNIVERSE]}/{data[CONF_DEVICE_CHANNEL]}")
            current = {**self._data, **user_input}

        def kelvin_default(key: str, fallback: str) -> int:
            return int(str(current.get(key, fallback)).rstrip("kK"))

        schema: dict[Any, Any] = {
            vol.Required(CONF_DEVICE_TRANSITION, default=current.get(CONF_DEVICE_TRANSITION, 0)):
                _number(min=0, max=999, step="any", unit_of_measurement="s"),
            vol.Optional(CONF_OUTPUT_CORRECTION, description={"suggested_value": current.get(CONF_OUTPUT_CORRECTION)}):
                _select(list(AVAILABLE_CORRECTIONS), CONF_OUTPUT_CORRECTION),
            vol.Required(CONF_CHANNEL_SIZE, default=current.get(CONF_CHANNEL_SIZE, "8bit")):
                _select(list(CHANNEL_SIZE), CONF_CHANNEL_SIZE),
            vol.Required(CONF_BYTE_ORDER, default=current.get(CONF_BYTE_ORDER, "big")):
                _select(["big", "little"], CONF_BYTE_ORDER),
        }
        if has_temp:
            temp = _number(min=1000, max=10000, unit_of_measurement="K")
            schema[vol.Required(CONF_DEVICE_MIN_TEMP, default=kelvin_default(CONF_DEVICE_MIN_TEMP, DEFAULT_MIN_TEMP))] = temp
            schema[vol.Required(CONF_DEVICE_MAX_TEMP, default=kelvin_default(CONF_DEVICE_MAX_TEMP, DEFAULT_MAX_TEMP))] = temp
        if device_type != "binary":
            schema[vol.Optional(CONF_CHANNEL_SETUP, description={"suggested_value": current.get(CONF_CHANNEL_SETUP)})] = str

        return self.async_show_form(step_id="details", data_schema=vol.Schema(schema), errors=errors)
