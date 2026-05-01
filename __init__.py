"""
腾讯云人脸识别Home Assistant插件
"""
import logging
from typing import Dict, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_SECRET_ID,
    CONF_SECRET_KEY,
    CONF_REGION,
    CONF_PERSON_GROUP_ID,
    get_entry_value,
)
from .tencent_cloud_client import TencentCloudClient
from .face_recognition import FaceRecognition
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置配置项"""
    _LOGGER.info("设置腾讯云人脸识别插件")

    secret_id = entry.data.get(CONF_SECRET_ID)
    secret_key = entry.data.get(CONF_SECRET_KEY)
    region = get_entry_value(entry, CONF_REGION, "ap-shanghai")
    person_group_id = get_entry_value(entry, CONF_PERSON_GROUP_ID, "Hass")

    try:
        client = TencentCloudClient(secret_id, secret_key, region)
    except Exception as ex:
        _LOGGER.error("创建腾讯云客户端失败")
        raise ConfigEntryNotReady(f"创建腾讯云客户端失败: {ex}")

    face_recognition = FaceRecognition(hass, client)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "entry": entry,
        "client": client,
        "face_recognition": face_recognition,
        "secret_id": secret_id,
        "secret_key": secret_key,
        "region": region,
        "person_group_id": person_group_id
    }

    await async_setup_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载配置项"""
    _LOGGER.info("卸载腾讯云人脸识别插件")

    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")

    if unload_ok:
        await async_unload_services(hass)

        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """移除配置项"""
    _LOGGER.info("移除腾讯云人脸识别插件配置")
