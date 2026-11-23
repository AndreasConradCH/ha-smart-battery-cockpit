"""Smart Battery Cockpit integration for Home Assistant."""

from __future__ import annotations

import logging
import os
from typing import Any

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_STATE_CHANGED, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change

from .const import (
    CONF_EXCLUDE_RECHARGEABLE,
    CONF_JUMP_THRESHOLD,
    CONF_NOTIFY_SERVICE,
    CONF_ROUNDTRIP_HOUR,
    CONF_SHOW_SIDEBAR,
    DB_FILENAME,
    DEFAULT_EXCLUDE_RECHARGEABLE,
    DEFAULT_JUMP_THRESHOLD,
    DEFAULT_MIN_NEW_LEVEL,
    DEFAULT_NOTIFY_SERVICE,
    DEFAULT_ROUNDTRIP_HOUR,
    DEFAULT_SHOW_SIDEBAR,
    DOMAIN,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL_PATH,
    SIGNAL_DATA_UPDATED,
    STATIC_URL_PATH,
)
from .database import (
    BatteryDatabase,
    infer_battery_type,
    is_rechargeable_device,
    parse_float,
)
from .websocket_api import async_register_websocket_api

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]


class SmartBatteryManager:
    """Coordinates Home Assistant state collection, SQLite persistence, and notifications."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        db_path = hass.config.path(DB_FILENAME)
        self.db = BatteryDatabase(db_path)
        self._unsubs: list[Any] = []

    @property
    def notify_service(self) -> str:
        return self.entry.options.get(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE)

    @property
    def roundtrip_hour(self) -> int:
        return int(self.entry.options.get(CONF_ROUNDTRIP_HOUR, DEFAULT_ROUNDTRIP_HOUR))

    @property
    def jump_threshold(self) -> float:
        return float(self.entry.options.get(CONF_JUMP_THRESHOLD, DEFAULT_JUMP_THRESHOLD))

    @property
    def exclude_rechargeable(self) -> bool:
        return bool(
            self.entry.options.get(CONF_EXCLUDE_RECHARGEABLE, DEFAULT_EXCLUDE_RECHARGEABLE)
        )

    def _collect_snapshots(self) -> list[dict[str, Any]]:
        """Collect all battery percentage sensors and matching voltage/area/device metadata."""
        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)
        area_reg = ar.async_get(self.hass)

        # Index voltage and battery-type entities by device_id
        volt_by_dev: dict[str, str] = {}
        type_by_dev: dict[str, str] = {}
        for entity_entry in ent_reg.entities.values():
            if not entity_entry.device_id or entity_entry.disabled:
                continue
            eid = entity_entry.entity_id
            if not eid.startswith("sensor."):
                continue
            low_eid = eid.lower()
            if "voltage" in low_eid or "spannung" in low_eid:
                volt_by_dev[entity_entry.device_id] = eid
            elif "battery_type" in low_eid or "batterietyp" in low_eid:
                type_by_dev[entity_entry.device_id] = eid

        snapshots: list[dict[str, Any]] = []
        for state in self.hass.states.async_all("sensor"):
            eid = state.entity_id
            attrs = state.attributes
            dc = attrs.get("device_class")
            unit = attrs.get("unit_of_measurement")
            if not (
                dc == "battery"
                or (unit == "%" and ("battery" in eid or "batterie" in eid))
            ):
                continue

            e_entry = ent_reg.async_get(eid)
            dev_id = e_entry.device_id if e_entry else None
            dev = dev_reg.async_get(dev_id) if dev_id else None
            platform = e_entry.platform if e_entry else ""

            raw_fn = attrs.get("friendly_name", eid)
            clean_fn = (
                raw_fn.replace(" Batterie", "")
                .replace(" Battery", "")
                .replace(" battery", "")
                .replace(" batterie", "")
                .strip()
            )
            dev_name = (dev.name_by_user or dev.name) if dev else clean_fn
            mfg = (dev.manufacturer or "") if dev else ""
            model = (dev.model or "") if dev else ""

            if self.exclude_rechargeable and is_rechargeable_device(
                eid, dev_name, mfg, model, platform
            ):
                continue

            area_id = (e_entry.area_id if e_entry else None) or (
                dev.area_id if dev else None
            )
            area = area_reg.async_get_area(area_id) if area_id else None
            room = area.name if area else "Home"

            volt_eid = volt_by_dev.get(dev_id) if dev_id else None
            volt_mv = None
            if volt_eid:
                v_state = self.hass.states.get(volt_eid)
                if v_state:
                    v_raw = parse_float(v_state.state)
                    v_unit = v_state.attributes.get("unit_of_measurement", "mV")
                    if v_raw is not None:
                        volt_mv = v_raw * 1000.0 if v_unit == "V" else v_raw

            explicit_type = None
            type_eid = type_by_dev.get(dev_id) if dev_id else None
            if type_eid:
                t_state = self.hass.states.get(type_eid)
                if t_state:
                    explicit_type = t_state.state

            btype = infer_battery_type(eid, model, mfg, explicit_type)
            pct = parse_float(state.state)

            snapshots.append(
                {
                    "entity_id": eid,
                    "friendly_name": dev_name,
                    "room": room,
                    "manufacturer": mfg,
                    "model": model,
                    "battery_type": btype,
                    "voltage_entity_id": volt_eid,
                    "battery_pct": pct,
                    "voltage_mv": volt_mv,
                }
            )

        return snapshots

    async def async_run_roundtrip(self, _now: Any = None) -> None:
        """Run daily round-trip snapshot and notify on newly detected jumps."""
        snapshots = self._collect_snapshots()
        jumps = await self.hass.async_add_executor_job(
            self.db.sync_devices_and_roundtrip,
            snapshots,
            self.jump_threshold,
            True,
        )
        for jump in jumps:
            await self.async_send_swap_question(jump)
        async_dispatcher_send(self.hass, SIGNAL_DATA_UPDATED)

    async def async_get_data(self) -> dict[str, Any]:
        """Return full dashboard data from SQLite."""
        return await self.hass.async_add_executor_job(self.db.get_dashboard_data)

    async def async_confirm_swap(
        self,
        entity_id: str,
        old_val: float | None = None,
        new_val: float | None = None,
        notes: str = "Confirmed battery replacement",
    ) -> None:
        """Confirm swap, dismiss notifications, and refresh sensor."""
        await self.hass.async_add_executor_job(
            self.db.confirm_swap, entity_id, old_val, new_val, notes
        )
        await self._dismiss_persistent_notification(entity_id)
        async_dispatcher_send(self.hass, SIGNAL_DATA_UPDATED)

    async def async_dismiss_swap(self, entity_id: str) -> None:
        """Dismiss swap question and clear notification."""
        await self.hass.async_add_executor_job(self.db.dismiss_swap, entity_id)
        await self._dismiss_persistent_notification(entity_id)
        async_dispatcher_send(self.hass, SIGNAL_DATA_UPDATED)

    async def async_send_swap_question(self, info: dict[str, Any]) -> None:
        """Send persistent notification and optional actionable mobile push."""
        eid = info["entity_id"]
        fn = info["friendly_name"]
        btype = info["battery_type"]
        old_pct = round(info["old_pct"])
        new_pct = round(info["new_pct"])
        notif_id = f"sbc_swap_{eid.replace('sensor.', '')}"
        title = f"🔋 Battery swap detected: {fn}"

        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "notification_id": notif_id,
                "title": title,
                "message": (
                    f"**{fn}** (`{eid}`, *{btype}*) jumped from **{old_pct}%** to **{new_pct}%**.\n\n"
                    f"Open **[Battery Cockpit](/{PANEL_URL_PATH})** to confirm or dismiss."
                ),
            },
            blocking=False,
        )

        if self.notify_service and "." in self.notify_service:
            domain, service = self.notify_service.split(".", 1)
            try:
                await self.hass.services.async_call(
                    domain,
                    service,
                    {
                        "title": title,
                        "message": f"Level jumped from {old_pct}% to {new_pct}% ({btype}). Did you replace the battery?",
                        "data": {
                            "tag": notif_id,
                            "actions": [
                                {
                                    "action": f"SBC_CONFIRM|{eid}|{old_pct}|{new_pct}",
                                    "title": "✅ Yes, replaced",
                                },
                                {
                                    "action": f"SBC_DISMISS|{eid}",
                                    "title": "❌ No, false alarm",
                                },
                            ],
                        },
                    },
                    blocking=False,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Could not send mobile notification via %s: %s", self.notify_service, err)

    async def _dismiss_persistent_notification(self, entity_id: str) -> None:
        notif_id = f"sbc_swap_{entity_id.replace('sensor.', '')}"
        await self.hass.services.async_call(
            "persistent_notification",
            "dismiss",
            {"notification_id": notif_id},
            blocking=False,
        )

    @callback
    def _handle_state_changed(self, event: Event) -> None:
        """Detect rapid upward jumps on battery sensors in real time."""
        eid: str = event.data.get("entity_id", "")
        if not eid.startswith("sensor."):
            return
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None or old_state is None:
            return
        if new_state.attributes.get("device_class") != "battery":
            return

        old_val = parse_float(old_state.state)
        new_val = parse_float(new_state.state)
        if old_val is None or new_val is None:
            return

        if (
            0 <= old_val < 75.0
            and new_val >= DEFAULT_MIN_NEW_LEVEL
            and (new_val - old_val) >= self.jump_threshold
        ):
            self.hass.async_create_task(self._process_jump(eid, old_val, new_val))

    async def _process_jump(self, entity_id: str, old_val: float, new_val: float) -> None:
        jump = await self.hass.async_add_executor_job(
            self.db.check_and_flag_jump, entity_id, old_val, new_val
        )
        if jump:
            await self.async_send_swap_question(jump)
            async_dispatcher_send(self.hass, SIGNAL_DATA_UPDATED)

    @callback
    def _handle_mobile_action(self, event: Event) -> None:
        """Process [Yes, replaced] / [No, false alarm] taps from mobile app notifications."""
        action: str = event.data.get("action", "")
        if not (action.startswith("SBC_CONFIRM|") or action.startswith("SBC_DISMISS|")):
            return
        parts = action.split("|")
        cmd = parts[0]
        eid = parts[1] if len(parts) > 1 else ""
        if not eid:
            return
        if cmd == "SBC_CONFIRM":
            old_pct = parse_float(parts[2]) if len(parts) > 2 else None
            new_pct = parse_float(parts[3]) if len(parts) > 3 else 100.0
            self.hass.async_create_task(
                self.async_confirm_swap(eid, old_val=old_pct, new_val=new_pct)
            )
        elif cmd == "SBC_DISMISS":
            self.hass.async_create_task(self.async_dismiss_swap(eid))

    async def async_start(self) -> None:
        """Start listeners and daily scheduler."""
        self._unsubs.append(
            async_track_time_change(
                self.hass,
                self.async_run_roundtrip,
                hour=self.roundtrip_hour,
                minute=0,
                second=0,
            )
        )
        self._unsubs.append(
            self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._handle_state_changed)
        )
        self._unsubs.append(
            self.hass.bus.async_listen(
                "mobile_app_notification_action", self._handle_mobile_action
            )
        )
        # Initial sync on startup
        await self.async_run_roundtrip()

    def stop(self) -> None:
        """Unsubscribe all listeners."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart Battery Cockpit from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    manager = SmartBatteryManager(hass, entry)
    hass.data[DOMAIN]["manager"] = manager

    async_register_websocket_api(hass)

    # Register static frontend bundle once
    if not hass.data[DOMAIN].get("static_registered"):
        frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL_PATH, frontend_dir, cache_headers=False)]
        )
        hass.data[DOMAIN]["static_registered"] = True

    # Register native sidebar panel if enabled
    show_sidebar = entry.options.get(CONF_SHOW_SIDEBAR, DEFAULT_SHOW_SIDEBAR)
    if show_sidebar:
        await panel_custom.async_register_panel(
            hass,
            webcomponent_name="smart-battery-cockpit-panel",
            frontend_url_path=PANEL_URL_PATH,
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            module_url=f"{STATIC_URL_PATH}/smart-battery-cockpit-panel.js",
            embed_iframe=False,
            require_admin=False,
        )

    await manager.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    manager: SmartBatteryManager | None = hass.data.get(DOMAIN, {}).pop("manager", None)
    if manager:
        manager.stop()
    frontend.async_remove_panel(hass, PANEL_URL_PATH)
    return unload_ok
