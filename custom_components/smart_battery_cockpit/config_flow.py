"""Config flow and options flow for Smart Battery Cockpit."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_EXCLUDE_RECHARGEABLE,
    CONF_JUMP_THRESHOLD,
    CONF_NOTIFY_SERVICE,
    CONF_ROUNDTRIP_HOUR,
    CONF_SHOW_SIDEBAR,
    DEFAULT_EXCLUDE_RECHARGEABLE,
    DEFAULT_JUMP_THRESHOLD,
    DEFAULT_NOTIFY_SERVICE,
    DEFAULT_ROUNDTRIP_HOUR,
    DEFAULT_SHOW_SIDEBAR,
    DOMAIN,
)


def _get_notify_options(hass) -> list[selector.SelectOptionDict]:
    """Discover mobile_app and other notify services for the dropdown."""
    options: list[selector.SelectOptionDict] = [
        selector.SelectOptionDict(value="", label="(None / HA Persistent Notification only)")
    ]
    notify_services = hass.services.async_services().get("notify", {})
    for svc_name in sorted(notify_services.keys()):
        if svc_name in ("notify", "persistent_notification", "send_message"):
            continue
        full = f"notify.{svc_name}"
        options.append(selector.SelectOptionDict(value=full, label=full))
    return options


def _build_schema(hass, defaults: dict[str, Any]) -> vol.Schema:
    notify_opts = _get_notify_options(hass)
    return vol.Schema(
        {
            vol.Optional(
                CONF_NOTIFY_SERVICE,
                default=defaults.get(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=notify_opts,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
            vol.Required(
                CONF_ROUNDTRIP_HOUR,
                default=defaults.get(CONF_ROUNDTRIP_HOUR, DEFAULT_ROUNDTRIP_HOUR),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=23,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_JUMP_THRESHOLD,
                default=defaults.get(CONF_JUMP_THRESHOLD, DEFAULT_JUMP_THRESHOLD),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=10,
                    max=60,
                    step=5,
                    unit_of_measurement="%",
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(
                CONF_EXCLUDE_RECHARGEABLE,
                default=defaults.get(CONF_EXCLUDE_RECHARGEABLE, DEFAULT_EXCLUDE_RECHARGEABLE),
            ): bool,
            vol.Required(
                CONF_SHOW_SIDEBAR,
                default=defaults.get(CONF_SHOW_SIDEBAR, DEFAULT_SHOW_SIDEBAR),
            ): bool,
        }
    )


class SmartBatteryCockpitConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Battery Cockpit."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title="Smart Battery Cockpit",
                data={},
                options={
                    CONF_NOTIFY_SERVICE: user_input.get(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE),
                    CONF_ROUNDTRIP_HOUR: int(user_input.get(CONF_ROUNDTRIP_HOUR, DEFAULT_ROUNDTRIP_HOUR)),
                    CONF_JUMP_THRESHOLD: int(user_input.get(CONF_JUMP_THRESHOLD, DEFAULT_JUMP_THRESHOLD)),
                    CONF_EXCLUDE_RECHARGEABLE: bool(
                        user_input.get(CONF_EXCLUDE_RECHARGEABLE, DEFAULT_EXCLUDE_RECHARGEABLE)
                    ),
                    CONF_SHOW_SIDEBAR: bool(user_input.get(CONF_SHOW_SIDEBAR, DEFAULT_SHOW_SIDEBAR)),
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(self.hass, {}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SmartBatteryCockpitOptionsFlow:
        """Get the options flow for this handler."""
        return SmartBatteryCockpitOptionsFlow()


class SmartBatteryCockpitOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Smart Battery Cockpit."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_NOTIFY_SERVICE: user_input.get(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE),
                    CONF_ROUNDTRIP_HOUR: int(user_input.get(CONF_ROUNDTRIP_HOUR, DEFAULT_ROUNDTRIP_HOUR)),
                    CONF_JUMP_THRESHOLD: int(user_input.get(CONF_JUMP_THRESHOLD, DEFAULT_JUMP_THRESHOLD)),
                    CONF_EXCLUDE_RECHARGEABLE: bool(
                        user_input.get(CONF_EXCLUDE_RECHARGEABLE, DEFAULT_EXCLUDE_RECHARGEABLE)
                    ),
                    CONF_SHOW_SIDEBAR: bool(user_input.get(CONF_SHOW_SIDEBAR, DEFAULT_SHOW_SIDEBAR)),
                },
            )

        defaults = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(self.hass, defaults),
        )
