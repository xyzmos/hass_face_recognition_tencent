"""传感器实体"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DOMAIN,
    CONF_PERSON_GROUP_ID,
    DEFAULT_PERSON_GROUP_ID,
    get_entry_value,
)

_LOGGER = logging.getLogger(__name__)
_LOGGER_POLLING = _LOGGER.getChild("polling")


class TencentFaceCoordinator(DataUpdateCoordinator):
    """腾讯云人脸识别数据更新协调器"""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client):
        super().__init__(
            hass,
            _LOGGER_POLLING,
            name="Tencent Face Recognition",
            update_interval=timedelta(minutes=5),
        )
        self.client = client
        self.entry = entry

    async def _async_update_data(self):
        """获取最新数据"""
        try:
            group_id = get_entry_value(
                self.entry, CONF_PERSON_GROUP_ID, DEFAULT_PERSON_GROUP_ID
            )

            group_info = await self.hass.async_add_executor_job(
                self.client.get_group_info, group_id
            )

            persons = await self.hass.async_add_executor_job(
                self.client.get_person_list_all, group_id
            )

            return {
                "group_info": group_info,
                "persons": persons,
                "person_count": len(persons),
            }
        except Exception as ex:
            _LOGGER_POLLING.debug("数据更新失败: %s", ex)
            raise UpdateFailed(f"数据更新失败: {ex}") from ex


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """设置传感器实体"""
    _LOGGER.debug("设置腾讯云人脸识别传感器实体")

    client = hass.data[DOMAIN][entry.entry_id]["client"]
    name = entry.data.get(CONF_NAME, "腾讯云人脸识别")

    coordinator = TencentFaceCoordinator(hass, entry, client)

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    entities = [
        TencentFaceRecognitionStatusSensor(coordinator, entry, name),
    ]

    for person in coordinator.data.get("persons", []):
        entities.append(
            TencentFaceRecognitionPersonSensor(coordinator, entry, person)
        )

    async_add_entities(entities)


class TencentFaceRecognitionPersonSensor(CoordinatorEntity, SensorEntity):
    """腾讯云人脸识别人员传感器"""

    _attr_icon = "mdi:account"
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, person: Dict[str, Any]):
        """初始化传感器"""
        super().__init__(coordinator)
        self._entry = entry
        self._person_id = person.get("person_id")
        person_name = person.get("person_name", "未知人员")
        self._attr_name = person_name
        self._attr_unique_id = f"{entry.entry_id}_{self._person_id}"
        self._attr_translation_key = "person_sensor"

    @property
    def state(self) -> str:
        """返回传感器状态"""
        if self.coordinator.data is None:
            return "未知"
        for person in self.coordinator.data.get("persons", []):
            if person.get("person_id") == self._person_id:
                return person.get("person_name", "未知")
        return "已删除"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """返回传感器属性"""
        if self.coordinator.data is None:
            return {"person_id": self._person_id}

        for person in self.coordinator.data.get("persons", []):
            if person.get("person_id") == self._person_id:
                return {
                    "person_id": person.get("person_id"),
                    "gender": "男" if person.get("gender") == 1 else "女",
                    "face_ids": person.get("face_ids"),
                    "face_count": len(person.get("face_ids", [])),
                }

        return {"person_id": self._person_id, "status": "已删除"}

    @property
    def available(self) -> bool:
        """传感器是否可用"""
        if self.coordinator.data is None:
            return False
        for person in self.coordinator.data.get("persons", []):
            if person.get("person_id") == self._person_id:
                return True
        return False


class TencentFaceRecognitionStatusSensor(CoordinatorEntity, SensorEntity):
    """腾讯云人脸识别状态传感器"""

    _attr_icon = "mdi:face-recognition"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_translation_key = "status_sensor"

    def __init__(self, coordinator, entry: ConfigEntry, name: str):
        """初始化传感器"""
        super().__init__(coordinator)
        self._entry = entry
        self._name = name
        self._attr_name = f"{name} 状态"
        self._attr_unique_id = f"{entry.entry_id}_status"

    @property
    def state(self) -> str:
        """返回传感器状态"""
        if self.coordinator.data is None:
            return "未连接"
        if self.coordinator.last_update_success:
            return "已连接"
        return "连接错误"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """返回传感器属性"""
        attrs = {
            "last_updated": (
                self.coordinator.data.get("last_updated")
                if self.coordinator.data
                else None
            ),
            "api_status": "正常" if self.coordinator.last_update_success else "错误",
            "person_count": (
                self.coordinator.data.get("person_count", 0)
                if self.coordinator.data
                else 0
            ),
            "last_error": None,
        }

        if self.coordinator.data and self.coordinator.data.get("group_info"):
            group_info = self.coordinator.data["group_info"]
            attrs["group_name"] = group_info.get("group_name", "")
            attrs["face_model_version"] = group_info.get("face_model_version", "")

        return attrs

    @property
    def available(self) -> bool:
        """状态传感器始终可用"""
        return True
