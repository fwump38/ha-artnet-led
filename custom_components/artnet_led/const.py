"""Constants for the Art-Net LED integration."""
from __future__ import annotations

import pyartnet
from homeassistant.components.light import ATTR_TRANSITION
from homeassistant.const import CONF_DEVICES, CONF_HOST as CONF_NODE_HOST
from homeassistant.const import CONF_NAME as CONF_DEVICE_NAME
from homeassistant.const import CONF_PORT as CONF_NODE_PORT
from homeassistant.const import CONF_TYPE as CONF_DEVICE_TYPE

DOMAIN = "artnet_led"

# Prefix of entity unique IDs; kept from the YAML days so existing entities keep their identity.
UNIQUE_ID_PREFIX = "dmx"

SUBENTRY_TYPE_LIGHT = "light"

ARTNET_DEFAULT_PORT = 6454
SACN_DEFAULT_PORT = 5568
KINET_DEFAULT_PORT = 6038

CONF_NODE_HOST_OVERRIDE = "host_override"
CONF_NODE_PORT_OVERRIDE = "port_override"
CONF_NODE_TYPE = "node_type"
CONF_NODE_MAX_FPS = "max_fps"
CONF_NODE_REFRESH = "refresh_every"
CONF_NODE_UNIVERSES = "universes"
CONF_SEND_PARTIAL_UNIVERSE = "send_partial_universe"

CONF_DEVICE_UNIVERSE = "universe"
CONF_DEVICE_CHANNEL = "channel"
CONF_DEVICE_TRANSITION = ATTR_TRANSITION
CONF_OUTPUT_CORRECTION = "output_correction"
CONF_CHANNEL_SIZE = "channel_size"
CONF_BYTE_ORDER = "byte_order"
CONF_DEVICE_MIN_TEMP = "min_temp"
CONF_DEVICE_MAX_TEMP = "max_temp"
CONF_CHANNEL_SETUP = "channel_setup"

NODE_TYPES = ["artnet-direct", "artnet-controller", "sacn", "kinet"]
NODE_TYPE_CONTROLLER = "artnet-controller"
DEFAULT_NODE_TYPE = "artnet-direct"
DEFAULT_MAX_FPS = 25
DEFAULT_REFRESH = 120

DEFAULT_MIN_TEMP = "2700K"
DEFAULT_MAX_TEMP = "6500K"

DEVICE_TYPES = ["dimmer", "rgb", "color_temp", "rgbw", "rgbww", "binary", "fixed", "xy"]
TEMPERATURE_DEVICE_TYPES = ["color_temp", "rgbww"]

AVAILABLE_CORRECTIONS = {"linear": pyartnet.output_correction.linear, "quadratic": pyartnet.output_correction.quadratic,
                         "cubic": pyartnet.output_correction.cubic, "quadruple": pyartnet.output_correction.quadruple}

type LogicalChannelSize = int
type LogicalChannelNumBytes = int
type ChannelSize = tuple[LogicalChannelSize, LogicalChannelNumBytes]

CHANNEL_SIZE: dict[str, ChannelSize] = {
    "8bit": (1, 1),
    "16bit": (2, 256),
    "24bit": (3, 256 ** 2),
    "32bit": (4, 256 ** 3),
}
