"""传感器实体。

提供两类传感器：
- ``TencentFaceRecognitionStatusSensor``：诊断类状态传感器，反映连接状态与库信息。
- ``TencentFaceRecognitionPersonSensor``：每个人员库成员一个传感器。

人员传感器基于 ``DataUpdateCoordinator`` 的数据动态创建/移除：当人员从
人员库中删除后，对应传感器在下次刷新时被标记为不可用并移除。
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, Optional

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
    CONF_PERSON_GROUP_ID,
    DEFAULT_PERSON_GROUP_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SENSOR_PERSON,
    SENSOR_STATUS,
    get_entry_value,
)

_LOGGER = logging.getLogger(__name__)
_LOGGER_POLLING = _LOGGER.getChild("polling")

# 性别枚举（与腾讯云 SDK 一致：0=女, 1=男）
_GENDER_MAP = {0: "女", 1: "男", None: "未知"}


class TencentFaceCoordinator(DataUpdateCoordinator):
    """腾讯云人脸识别数据更新协调器。"""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client) -> None:
        super().__init__(
            hass,
            _LOGGER_POLLING,
            name="Tencent Face Recognition",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self.entry = entry
        # 动态传感器跟踪集合
        self._entity_person_ids: set[str] = set()
        self._person_sensors: dict[str, TencentFaceRecognitionPersonSensor] = {}

    async def _async_update_data(self) -> Dict[str, Any]:
        """获取最新的人员库与成员数据。"""
        try:
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
        except UpdateFailed:
            raise
        except Exception as ex:  # noqa: BLE001
            _LOGGER_POLLING.warning("数据更新失败: %s", ex)
            raise UpdateFailed(f"数据更新失败: {ex}") from ex


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """设置传感器实体。"""
    _LOGGER.debug("设置腾讯云人脸识别传感器实体")

    client = hass.data[DOMAIN][entry.entry_id]["client"]
    name = entry.data.get(CONF_NAME, "腾讯云人脸识别")

    coordinator = TencentFaceCoordinator(hass, entry, client)
    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    await coordinator.async_config_entry_first_refresh()

    entities: list[SensorEntity] = [
        TencentFaceRecognitionStatusSensor(coordinator, entry, name),
    ]

    current_persons = {p["person_id"]: p for p in coordinator.data.get("persons", []) if p.get("person_id")}
    for person in current_persons.values():
        entities.append(TencentFaceRecognitionPersonSensor(coordinator, entry, person))

    async_add_entities(entities)

    # 注册协调器更新监听，动态增减人员传感器
    @callback
    def _async_update_person_sensors() -> None:
        """根据协调器数据动态添加/移除人员传感器。"""
        if coordinator.data is None:
            return

        new_persons = {
            p["person_id"]: p
            for p in coordinator.data.get("persons", [])
            if p.get("person_id")
        }

        # 新增的人员 -> 创建传感器
        to_add = [
            TencentFaceRecognitionPersonSensor(coordinator, entry, person)
            for pid, person in new_persons.items()
            if pid not in coordinator._entity_person_ids
        ]
        if to_add:
            async_add_entities(to_add)
            for sensor in to_add:
                coordinator._entity_person_ids.add(sensor._person_id)
                # _person_sensors 已在传感器 __init__ 中注册

        # 已删除的人员 -> 移除对应传感器
        for pid in list(coordinator._entity_person_ids):
            if pid not in new_persons:
                sensor = coordinator._person_sensors.get(pid)
                if sensor is not None:
                    sensor.async_remove()
                coordinator._entity_person_ids.discard(pid)
                coordinator._person_sensors.pop(pid, None)

    # 补录初始已知人员 ID 集合（_person_sensors 已在传感器 __init__ 中填充）
    coordinator._entity_person_ids = set(current_persons.keys())

    entry.async_on_unload(coordinator.async_add_listener(_async_update_person_sensors))


class TencentFaceRecognitionPersonSensor(CoordinatorEntity, SensorEntity):
    """腾讯云人脸识别人员传感器。

    状态为人员名称；当人员从库中被删除后，传感器变为不可用并自动移除。
    """

    _attr_icon = "mdi:account"
    _attr_has_entity_name = True
    _attr_translation_key = "person_sensor"

    def __init__(self, coordinator, entry: ConfigEntry, person: Dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._person_id: Optional[str] = person.get("person_id")
        self._attr_name = person.get("person_name", "未知人员")
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_PERSON}_{self._person_id}"
        # 注册到协调器的传感器映射，供动态删除使用
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
        """返回传感器状态（人员名称）。"""
        person = self._current_person()
        if person is None:
            return "已删除"
        return person.get("person_name", "未知")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """返回传感器属性。"""
        person = self._current_person()
        if person is None:
            return {"person_id": self._person_id, "status": "已删除"}
        face_ids = person.get("face_ids", []) or []
        return {
            "person_id": person.get("person_id"),
            "gender": _GENDER_MAP.get(person.get("gender"), "未知"),
            "face_ids": face_ids,
            "face_count": len(face_ids),
            "creation_timestamp": person.get("creation_timestamp"),
        }

    @property
    def available(self) -> bool:
        """人员存在时才可用。"""
        return self._current_person() is not None


class TencentFaceRecognitionStatusSensor(CoordinatorEntity, SensorEntity):
    """腾讯云人脸识别状态传感器。"""

    _attr_icon = "mdi:face-recognition"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_translation_key = "status_sensor"

    def __init__(self, coordinator, entry: ConfigEntry, name: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._name = name
        self._attr_name = f"{name} 状态"
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_STATUS}"

    @property
    def native_value(self) -> str:
        """返回连接状态。"""
        if self.coordinator.data is None:
            return "未连接"
        if self.coordinator.last_update_success:
            return "已连接"
        return "连接错误"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """返回状态传感器属性。"""
        data = self.coordinator.data or {}
        group_info = data.get("group_info", {}) if isinstance(data.get("group_info"), dict) else {}

        attrs: Dict[str, Any] = {
            "api_status": "正常" if self.coordinator.last_update_success else "错误",
            "person_count": data.get("person_count", 0),
            "face_model_version": data.get("face_model_version", "")
            or group_info.get("face_model_version", ""),
            "last_exception": str(self.coordinator.last_exception) if self.coordinator.last_exception else None,
            "last_update_success": self.coordinator.last_update_success,
        }

        if group_info:
            attrs["group_id"] = group_info.get("group_id", "")
            attrs["group_name"] = group_info.get("group_name", "")
            attrs["group_tag"] = group_info.get("group_tag", "")
            attrs["creation_timestamp"] = group_info.get("creation_timestamp", 0)

        return attrs

    @property
    def available(self) -> bool:
        """状态传感器始终可用。"""
        return True
