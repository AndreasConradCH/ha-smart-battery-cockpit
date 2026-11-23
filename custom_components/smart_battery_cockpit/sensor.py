"""Status sensor for Smart Battery Cockpit."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DATA_UPDATED


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Smart Battery Cockpit status sensor."""
    manager = hass.data[DOMAIN]["manager"]
    async_add_entities([SmartBatteryCockpitStatusSensor(manager, entry.entry_id)], True)


class SmartBatteryCockpitStatusSensor(SensorEntity):
    """Summary sensor showing tracked devices, low batteries, pending swaps & anomalies."""

    _attr_has_entity_name = True
    _attr_name = "Status"
    _attr_icon = "mdi:battery-sync"

    def __init__(self, manager, entry_id: str) -> None:
        self._manager = manager
        self._attr_unique_id = f"{entry_id}_status"
        self._data: dict[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        """Register dispatcher listener for live updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_DATA_UPDATED, self._handle_update
            )
        )
        await self.async_update()

    @callback
    def _handle_update(self) -> None:
        """Schedule sensor refresh when DB updates."""
        self.async_schedule_update_ha_state(True)

    async def async_update(self) -> None:
        """Fetch latest summary from the manager."""
        self._data = await self._manager.async_get_data()

    @property
    def native_value(self) -> str:
        """Return concise summary string."""
        if not self._data:
            return "Initializing"
        total = self._data.get("total_devices", 0)
        low = self._data.get("low_battery_count", 0)
        pend = self._data.get("pending_confirmations_count", 0)
        return f"{total} devices ({low} low, {pend} pending)"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return rich telemetry attributes."""
        if not self._data:
            return {}
        low_devs = [
            f"{d['friendly_name']} ({round(d['last_level'])}%)"
            for d in self._data.get("devices", [])
            if d.get("last_level") is not None and d["last_level"] <= 20
        ]
        anom_devs = [
            f"{d['friendly_name']} (Ø {d.get('avg_7d_drain', 0):.1f}%/d)"
            for d in self._data.get("anomalies", [])
        ]
        return {
            "total_devices": self._data.get("total_devices", 0),
            "low_battery_count": self._data.get("low_battery_count", 0),
            "pending_confirmations_count": self._data.get("pending_confirmations_count", 0),
            "anomaly_count": self._data.get("anomaly_count", 0),
            "last_roundtrip": self._data.get("generated_at"),
            "low_devices": low_devs,
            "anomalies": anom_devs,
        }
