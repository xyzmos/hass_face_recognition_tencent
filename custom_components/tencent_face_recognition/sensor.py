"""传感器实体。

- ``TencentFaceRecognitionStatusSensor``：诊断类状态传感器（连接状态 + 库信息）。
- ``TencentFaceRecognitionPersonSensor``：每个人员库成员一个传感器，随协调器数据动态增删。
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Dict, Optional

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_PERSON_GROUP_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_PERSON_GROUP_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    SENSOR_PERSON,
    SENSOR_STATUS,
    get_entry_value,
)

if TYPE_CHECKING:
    from . import TFRConfigEntry

_LOGGER = logging.getLogger(__name__)

_GENDER_MAP = {0: "女", 1: "男", 2: "未知", None: "未知"}


class TencentFaceCoordinator(DataUpdateCoordinator):
    """腾讯云人脸识别数据更新协调器。"""

    def __init__(self, hass: HomeAssistant, entry: TFRConfigEntry) -> None:
        scan_interval = int(
            get_entry_value(entry, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="Tencent Face Recognition",
            update_interval=timedelta(seconds=max(30, scan_interval)),
        )
        self.client = entry.runtime_data.client
        self.entry = entry
        self._entity_person_ids: set[str] = set()
        self._person_sensors: dict[str, TencentFaceRecognitionPersonSensor] = {}

    async def _async_update_data(self) -> Dict[str, Any]:
        group_id = get_entry_value(
            self.entry, CONF_PERSON_GROUP_ID, DEFAULT_PERSON_GROUP_ID
        )

        group_result = await self.hass.async_add_executor_job(
            self.client.get_group_info, group_id
        )
        group_info = group_result if group_result.get("success", False) else {}

        persons_result = await self.hass.async_add_executor_job(
            self.client.get_person_list_all, group_id
        )
        if not persons_result.get("success", False):
            raise UpdateFailed(
                f"获取人员列表失败: {persons_result.get('error_message', '未知错误')}"
            )
        persons = persons_result.get("persons", [])

        return {
            "group_info": group_info,
            "persons": persons,
            "person_count": len(persons),
            "face_model_version": persons_result.get(
                "face_model_version",
                group_info.get("face_model_version", ""),
            ),
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TFRConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置传感器实体。"""
    runtime = entry.runtime_data

    coordinator = TencentFaceCoordinator(hass, entry)
    runtime.coordinator = coordinator

    await coordinator.async_config_entry_first_refresh()

    entities: list[SensorEntity] = [
        TencentFaceRecognitionStatusSensor(coordinator, entry),
    ]

    current_persons = {
        p["person_id"]: p
        for p in (coordinator.data or {}).get("persons", [])
        if p.get("person_id")
    }
    for person in current_persons.values():
        entities.append(TencentFaceRecognitionPersonSensor(coordinator, entry, person))

    async_add_entities(entities)
    coordinator._entity_person_ids = set(current_persons.keys())

    @callback
    def _async_update_person_sensors() -> None:
        if coordinator.data is None:
            return
        new_persons = {
            p["person_id"]: p
            for p in coordinator.data.get("persons", [])
            if p.get("person_id")
        }

        to_add = [
            TencentFaceRecognitionPersonSensor(coordinator, entry, person)
            for pid, person in new_persons.items()
            if pid not in coordinator._entity_person_ids
        ]
        if to_add:
            for sensor in to_add:
                coordinator._entity_person_ids.add(sensor._person_id)
            async_add_entities(to_add)

        for pid in list(coordinator._entity_person_ids):
            if pid not in new_persons:
                sensor = coordinator._person_sensors.pop(pid, None)
                if sensor is not None:
                    hass.async_create_task(sensor.async_remove(force_remove=True))
                coordinator._entity_person_ids.discard(pid)

    entry.async_on_unload(
        coordinator.async_add_listener(_async_update_person_sensors)
    )


def _device_info(entry: TFRConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get(CONF_NAME, "腾讯云人脸识别"),
        manufacturer=MANUFACTURER,
        model="IAI 人脸识别",
    )


class TencentFaceRecognitionPersonSensor(CoordinatorEntity, SensorEntity):
    """人员传感器：状态为人员名称，属性含 face_ids 等。"""

    _attr_icon = "mdi:account"
    _attr_has_entity_name = True
    _attr_translation_key = "person_sensor"

    def __init__(
        self, coordinator: TencentFaceCoordinator, entry: TFRConfigEntry, person: Dict[str, Any]
    ) -> None:
        super().__init__(coordinator)
        self._person_id: Optional[str] = person.get("person_id")
        self._attr_name = person.get("person_name", "未知人员")
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_PERSON}_{self._person_id}"
        self._attr_device_info = _device_info(entry)
        coordinator._person_sensors[self._person_id] = self

    def _current_person(self) -> Optional[Dict[str, Any]]:
        if self.coordinator.data is None:
            return None
        for person in self.coordinator.data.get("persons", []):
            if person.get("person_id") == self._person_id:
                return person
        return None

    @property
    def native_value(self) -> str:
        person = self._current_person()
        return "已删除" if person is None else person.get("person_name", "未知")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        person = self._current_person()
        if person is None:
            return {"person_id": self._person_id, "status": "已删除"}
        face_ids = person.get("face_ids", []) or []
        return {
            "person_id": person.get("person_id"),
            "gender": _GENDER_MAP.get(person.get("gender"), "未知"),
            "face_ids": face_ids,
            "face_count": len(face_ids),
            "person_ex_descriptions": person.get("person_ex_descriptions", []),
            "creation_timestamp": person.get("creation_timestamp"),
        }

    @property
    def available(self) -> bool:
        return self._current_person() is not None


class TencentFaceRecognitionStatusSensor(CoordinatorEntity, SensorEntity):
    """状态传感器：连接状态与人员库信息。"""

    _attr_icon = "mdi:face-recognition"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_translation_key = "status_sensor"

    def __init__(self, coordinator: TencentFaceCoordinator, entry: TFRConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_STATUS}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> str:
        if self.coordinator.data is None:
            return "未连接"
        return "已连接" if self.coordinator.last_update_success else "连接错误"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        data = self.coordinator.data or {}
        group_info = (
            data.get("group_info", {})
            if isinstance(data.get("group_info"), dict)
            else {}
        )
        attrs: Dict[str, Any] = {
            "api_status": "正常" if self.coordinator.last_update_success else "错误",
            "person_count": data.get("person_count", 0),
            "face_model_version": data.get("face_model_version", "")
            or group_info.get("face_model_version", ""),
            "last_update_success": self.coordinator.last_update_success,
        }
        if self.coordinator.last_exception:
            attrs["last_exception"] = str(self.coordinator.last_exception)
        if group_info:
            attrs["group_id"] = group_info.get("group_id", "")
            attrs["group_name"] = group_info.get("group_name", "")
            attrs["group_tag"] = group_info.get("group_tag", "")
            attrs["creation_timestamp"] = group_info.get("creation_timestamp", 0)
        return attrs

    @property
    def available(self) -> bool:
        return True
