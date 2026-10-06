"""诊断信息导出（下载诊断）。"""

from __future__ import annotations

from typing import Any, Dict

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_SECRET_ID, CONF_SECRET_KEY

_REDACT_KEYS = {CONF_SECRET_ID, CONF_SECRET_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> Dict[str, Any]:
    """返回该配置项的诊断数据（凭据脱敏）。"""
    runtime = getattr(entry, "runtime_data", None)
    coordinator = getattr(runtime, "coordinator", None) if runtime else None
    coord_data = coordinator.data if coordinator is not None else {}

    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(entry.data, _REDACT_KEYS),
            "options": dict(entry.options),
        },
        "runtime": {
            "region": getattr(runtime, "region", None),
            "person_group_id": getattr(runtime, "person_group_id", None),
        },
        "coordinator": {
            "last_update_success": getattr(coordinator, "last_update_success", None),
            "person_count": coord_data.get("person_count"),
            "face_model_version": coord_data.get("face_model_version"),
        }
        if coordinator is not None
        else None,
    }
