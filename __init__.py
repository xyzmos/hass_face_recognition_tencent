"""
腾讯云人脸识别Home Assistant插件
"""
import logging
from typing import Dict, Any

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_SECRET_ID,
    CONF_SECRET_KEY,
    CONF_REGION,
    CONF_PERSON_GROUP_ID
)
from .tencent_cloud_client import TencentCloudClient
from .face_recognition import FaceRecognition
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

# 添加传感器平台
PLATFORMS.append("sensor")

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置配置项"""
    _LOGGER.info("设置腾讯云人脸识别插件")
    
    # 获取配置
    secret_id = entry.data.get(CONF_SECRET_ID)
    secret_key = entry.data.get(CONF_SECRET_KEY)
    region = entry.data.get(CONF_REGION, "ap-shanghai")
    person_group_id = entry.data.get(CONF_PERSON_GROUP_ID, "Hass")
    
    # 创建腾讯云客户端
    try:
        client = TencentCloudClient(secret_id, secret_key, region)
    except Exception as ex:
        _LOGGER.error("创建腾讯云客户端失败: %s", ex)
        raise ConfigEntryNotReady(f"创建腾讯云客户端失败: {ex}")
    
    # 创建人脸识别实例
    face_recognition = FaceRecognition(hass, client)
    
    # 存储配置和实例
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "entry": entry,
        "client": client,
        "face_recognition": face_recognition,
        "secret_id": secret_id,
        "secret_key": secret_key,
        "region": region,
        "person_group_id": person_group_id
    }
    
    # 设置服务
    await async_setup_services(hass)
    
    # 设置平台
    # 转发配置项到平台
    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setups(entry, [platform])
        )
    
    # 不再注册前端面板，改为使用配置流管理
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载配置项"""
    _LOGGER.info("卸载腾讯云人脸识别插件")
    
    # 注销自定义面板
    # 注意：在新版本的 Home Assistant 中，面板注册方式已更改
    # 不需要手动注销面板，系统会自动处理
    
    # 卸载平台
    unload_ok = True
    for platform in PLATFORMS:
        result = await hass.config_entries.async_forward_entry_unload(entry, platform)
        unload_ok = unload_ok and result
    
    if unload_ok:
        # 卸载服务
        await async_unload_services(hass)
        
        # 移除数据
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """移除配置项"""
    _LOGGER.info("移除腾讯云人脸识别插件配置")