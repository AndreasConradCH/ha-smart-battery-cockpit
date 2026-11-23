"""Native Home Assistant WebSocket API for Smart Battery Cockpit."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


@callback
def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register WebSocket commands for Smart Battery Cockpit."""
    websocket_api.async_register_command(hass, ws_get_data)
    websocket_api.async_register_command(hass, ws_roundtrip)
    websocket_api.async_register_command(hass, ws_confirm_swap)
    websocket_api.async_register_command(hass, ws_dismiss_swap)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/get_data"})
@websocket_api.async_response
async def ws_get_data(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return current battery lifecycle database snapshot."""
    manager = hass.data.get(DOMAIN, {}).get("manager")
    if manager is None:
        connection.send_error(msg["id"], "not_ready", "Smart Battery Cockpit is not initialized.")
        return
    data = await manager.async_get_data()
    connection.send_result(msg["id"], data)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/roundtrip"})
@websocket_api.async_response
async def ws_roundtrip(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Run an on-demand round-trip across all battery sensors."""
    manager = hass.data.get(DOMAIN, {}).get("manager")
    if manager is None:
        connection.send_error(msg["id"], "not_ready", "Smart Battery Cockpit is not initialized.")
        return
    await manager.async_run_roundtrip()
    data = await manager.async_get_data()
    connection.send_result(msg["id"], data)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/confirm_swap",
        vol.Required("entity_id"): str,
        vol.Optional("old_pct"): vol.Coerce(float),
        vol.Optional("new_pct"): vol.Coerce(float),
        vol.Optional("notes", default="Confirmed battery replacement"): str,
    }
)
@websocket_api.async_response
async def ws_confirm_swap(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Confirm a battery replacement and persist it to SQLite."""
    manager = hass.data.get(DOMAIN, {}).get("manager")
    if manager is None:
        connection.send_error(msg["id"], "not_ready", "Smart Battery Cockpit is not initialized.")
        return
    await manager.async_confirm_swap(
        msg["entity_id"],
        old_val=msg.get("old_pct"),
        new_val=msg.get("new_pct"),
        notes=msg.get("notes", "Confirmed battery replacement"),
    )
    data = await manager.async_get_data()
    connection.send_result(msg["id"], data)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/dismiss_swap",
        vol.Required("entity_id"): str,
    }
)
@websocket_api.async_response
async def ws_dismiss_swap(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Dismiss a pending battery swap confirmation."""
    manager = hass.data.get(DOMAIN, {}).get("manager")
    if manager is None:
        connection.send_error(msg["id"], "not_ready", "Smart Battery Cockpit is not initialized.")
        return
    await manager.async_dismiss_swap(msg["entity_id"])
    data = await manager.async_get_data()
    connection.send_result(msg["id"], data)
