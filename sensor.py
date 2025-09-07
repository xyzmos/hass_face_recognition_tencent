"""传感器实体"""

import logging
import base64
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """设置传感器实体"""
    _LOGGER.debug("设置腾讯云人脸识别传感器实体")
    
    # 获取配置项
    name = entry.data.get(CONF_NAME, "腾讯云人脸识别")
    
    # 创建传感器实体
    async_add_entities(
        [
            TencentFaceRecognitionStatusSensor(hass, entry, name),
        ]
    )

    # 获取人员列表并创建实体
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    person_group_id = entry.data.get("person_group_id", "Hass")
    
    try:
        persons = await hass.async_add_executor_job(
            client.get_person_list, person_group_id
        )
        
        for person in persons:
            async_add_entities(
                [
                    TencentFaceRecognitionPersonSensor(hass, entry, person),
                ]
            )
    except Exception as ex:
        _LOGGER.error("获取人员列表失败: %s", ex)


class TencentFaceRecognitionPersonSensor(SensorEntity):
    """腾讯云人脸识别人员传感器"""

    _attr_icon = "mdi:account"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, person: Dict[str, Any]):
        """初始化传感器"""
        self.hass = hass
        self._entry = entry
        self._person = person
        self._attr_name = person.get("person_name", "未知人员")
        self._attr_unique_id = f"{entry.entry_id}_{person.get('person_id')}"
        self._state = "未知"
        self._extra_state_attributes = {
            "person_id": person.get("person_id"),
            "gender": "男" if person.get("gender") == 1 else "女",
            "face_ids": person.get("face_ids"),
        }

    @property
    def state(self) -> str:
        """返回传感器状态"""
        return self._state

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """返回传感器属性"""
        return self._extra_state_attributes


class TencentFaceRecognitionStatusSensor(SensorEntity):
    """腾讯云人脸识别状态传感器"""

    _attr_icon = "mdi:face-recognition"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, name: str):
        """初始化传感器"""
        self.hass = hass
        self._entry = entry
        self._name = name
        self._attr_name = f"{name} 状态"
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._state = "未连接"
        self._extra_state_attributes = {
            "last_updated": None,
            "api_status": "未知",
            "client_status": "未知",
            "last_test_time": None,
            "error_count": 0,
            "success_count": 0,
            "last_error": None
        }
        self._client = None
        self._last_successful_test = None

    @property
    def state(self) -> str:
        """返回传感器状态"""
        return self._state

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """返回传感器属性"""
        return self._extra_state_attributes

    async def async_added_to_hass(self) -> None:
        """当实体添加到Home Assistant时调用"""
        # 设置定期更新
        async_track_time_interval(
            self.hass,
            self._async_update,
            timedelta(minutes=5)  # 每5分钟更新一次
        )
        
        # 立即执行一次更新
        await self._async_update(None)

    async def _async_update(self, _) -> None:
        """更新传感器状态"""
        await self.async_update()

    async def async_update(self) -> None:
        """更新传感器状态"""
        try:
            # 获取插件实例
            entry_data = self.hass.data[DOMAIN].get(self._entry.entry_id)
            if not entry_data:
                self._state = "未初始化"
                self._extra_state_attributes["api_status"] = "插件未正确初始化"
                self._extra_state_attributes["client_status"] = "未初始化"
                return
            
            # 获取客户端实例
            client = entry_data.get("client")
            face_recognition = entry_data.get("face_recognition")
            
            if not client or not face_recognition:
                self._state = "未初始化"
                self._extra_state_attributes["api_status"] = "客户端未正确初始化"
                self._extra_state_attributes["client_status"] = "未初始化"
                return
            
            # 更新客户端状态
            self._client = client
            self._extra_state_attributes["client_status"] = "已初始化"
            
            # 使用内置的测试图片进行连接测试
            await self._test_api_connection(face_recognition)
            
        except Exception as ex:
            _LOGGER.error("更新腾讯云人脸识别状态传感器失败: %s", ex, exc_info=True)
            self._state = "连接错误"
            self._extra_state_attributes["api_status"] = f"错误: {str(ex)}"
            self._extra_state_attributes["last_error"] = str(ex)
            self._extra_state_attributes["error_count"] = self._extra_state_attributes.get("error_count", 0) + 1
        
        # 更新最后更新时间
        self._extra_state_attributes["last_updated"] = datetime.now().isoformat()

    async def _test_api_connection(self, face_recognition) -> None:
        """测试API连接"""
        try:
            group_id = self._entry.data.get("person_group_id", "Hass")
            
            # 使用 GetGroupInfo 测试连接
            group_info = await self.hass.async_add_executor_job(
                self._client.get_group_info,
                group_id
            )
            
            if group_info:
                self._state = "已连接"
                self._extra_state_attributes["api_status"] = "正常"
                self._extra_state_attributes["success_count"] = self._extra_state_attributes.get("success_count", 0) + 1
                self._last_successful_test = datetime.now()
                self._extra_state_attributes["last_test_time"] = self._last_successful_test.isoformat()
                
                if "last_error" in self._extra_state_attributes:
                    self._extra_state_attributes["last_error"] = None
            else:
                self._state = "连接错误"
                self._extra_state_attributes["api_status"] = "获取人员库信息失败"
                
        except Exception as ex:
            error_msg = str(ex)
            self._state = "连接错误"
            self._extra_state_attributes["api_status"] = f"连接失败: {error_msg}"
            self._extra_state_attributes["last_error"] = error_msg
            self._extra_state_attributes["error_count"] = self._extra_state_attributes.get("error_count", 0) + 1
            _LOGGER.debug("API连接测试失败: %s", error_msg)