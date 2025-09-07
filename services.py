"""服务定义"""

import logging
from typing import Dict, Any, List, Optional

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_FACE_SEARCH,
    SERVICE_DETECT_FACE,
    SERVICE_GET_FACE_ATTRIBUTES,
    ATTR_IMAGE_URL,
    ATTR_IMAGE_FILE,
    ATTR_IMAGE_PATH,
    ATTR_MAX_FACE_NUM,
    ATTR_MIN_FACE_SIZE,
    ATTR_MAX_USER_NUM,
    ATTR_QUALITY_CONTROL,
    ATTR_NEED_ROTATE_CHECK,
    ATTR_FACE_MATCH_THRESHOLD,
)

_LOGGER = logging.getLogger(__name__)

# 人脸搜索服务参数
FACE_SEARCH_SCHEMA = vol.Schema({
    vol.Required('group_id'): cv.string,
    vol.Optional(ATTR_IMAGE_URL): cv.string,
    vol.Optional(ATTR_IMAGE_PATH): cv.string,
    vol.Optional(ATTR_IMAGE_FILE): cv.string,
    vol.Optional(ATTR_MAX_FACE_NUM, default=1): cv.positive_int,
    vol.Optional(ATTR_MIN_FACE_SIZE, default=34): cv.positive_int,
    vol.Optional(ATTR_MAX_USER_NUM, default=5): cv.positive_int,
    vol.Optional(ATTR_QUALITY_CONTROL, default=1): vol.In([0, 1]),
    vol.Optional(ATTR_NEED_ROTATE_CHECK, default=1): vol.In([0, 1]),
    vol.Optional(ATTR_FACE_MATCH_THRESHOLD, default=60.0): vol.Range(min=0, max=100),
})

# 人脸检测服务参数
DETECT_FACE_SCHEMA = vol.Schema({
    vol.Optional(ATTR_IMAGE_URL): cv.string,
    vol.Optional(ATTR_IMAGE_PATH): cv.string,
    vol.Optional(ATTR_IMAGE_FILE): cv.string,
    vol.Optional(ATTR_MAX_FACE_NUM, default=1): cv.positive_int,
    vol.Optional(ATTR_MIN_FACE_SIZE, default=34): cv.positive_int,
    vol.Optional(ATTR_NEED_ROTATE_CHECK, default=1): vol.In([0, 1]),
})

# 获取人脸属性服务参数
GET_FACE_ATTRIBUTES_SCHEMA = vol.Schema({
    vol.Optional(ATTR_IMAGE_URL): cv.string,
    vol.Optional(ATTR_IMAGE_PATH): cv.string,
    vol.Optional(ATTR_IMAGE_FILE): cv.string,
    vol.Optional(ATTR_MAX_FACE_NUM, default=1): cv.positive_int,
    vol.Optional(ATTR_NEED_ROTATE_CHECK, default=1): vol.In([0, 1]),
})


async def async_setup_services(hass: HomeAssistant) -> None:
    """设置服务"""
    _LOGGER.info("设置腾讯云人脸识别服务")

    # 注册人脸搜索服务
    hass.services.async_register(
        DOMAIN,
        SERVICE_FACE_SEARCH,
        async_face_search_service,
        schema=FACE_SEARCH_SCHEMA,
        supports_response=True
    )

    # 注册人脸检测服务
    hass.services.async_register(
        DOMAIN,
        SERVICE_DETECT_FACE,
        async_detect_face_service,
        schema=DETECT_FACE_SCHEMA
    )

    # 注册获取人脸属性服务
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_FACE_ATTRIBUTES,
        async_get_face_attributes_service,
        schema=GET_FACE_ATTRIBUTES_SCHEMA
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """卸载服务"""
    _LOGGER.info("卸载腾讯云人脸识别服务")

    # 注销所有服务
    hass.services.async_remove(DOMAIN, SERVICE_FACE_SEARCH)
    hass.services.async_remove(DOMAIN, SERVICE_DETECT_FACE)
    hass.services.async_remove(DOMAIN, SERVICE_GET_FACE_ATTRIBUTES)


async def async_face_search_service(call: ServiceCall) -> Dict[str, Any]:
    """人脸搜索服务"""
    from homeassistant.exceptions import HomeAssistantError

    hass = call.hass
    data = call.data

    # 获取配置项
    config_entry = _get_config_entry(hass)
    if not config_entry:
        raise HomeAssistantError("未找到腾讯云人脸识别配置")

    # 获取插件实例
    entry_data = _get_entry_data(hass)
    if not entry_data:
        raise HomeAssistantError("腾讯云人脸识别插件未正确初始化")
    
    face_recognition = entry_data.get("face_recognition")
    if not face_recognition:
        raise HomeAssistantError("腾讯云人脸识别插件未正确初始化")

    # 调用人脸搜索功能
    try:
        group_id = data.get('group_id')
        image_url = data.get(ATTR_IMAGE_URL)
        image_path = data.get(ATTR_IMAGE_PATH)
        image_file = data.get(ATTR_IMAGE_FILE)
        max_face_num = data.get(ATTR_MAX_FACE_NUM, 1)
        min_face_size = data.get(ATTR_MIN_FACE_SIZE, 34)
        max_user_num = data.get(ATTR_MAX_USER_NUM, 5)
        quality_control = data.get(ATTR_QUALITY_CONTROL, 1)
        need_rotate_check = data.get(ATTR_NEED_ROTATE_CHECK, 1)
        face_match_threshold = data.get(ATTR_FACE_MATCH_THRESHOLD, 60.0)

        result = await face_recognition.async_search_faces(
            image_url=image_url,
            image_path=image_path,
            image_file=image_file,
            group_ids=[group_id],
            max_face_num=max_face_num,
            min_face_size=min_face_size,
            max_user_num=max_user_num,
            quality_control=quality_control,
            need_rotate_check=need_rotate_check,
            face_match_threshold=face_match_threshold
        )

        # 直接返回结果，包含状态和错误信息
        return result

    except Exception as ex:
        _LOGGER.error("人脸搜索服务调用失败: %s", ex)
        # 返回错误信息，而不是抛出异常
        return {
            "success": False,
            "faces": [],
            "error": str(ex),
            "error_code": "service_error",
            "error_message": str(ex)
        }


async def async_detect_face_service(call: ServiceCall) -> Dict[str, Any]:
    """人脸检测服务"""
    from homeassistant.exceptions import HomeAssistantError

    hass = call.hass
    data = call.data

    # 获取配置项
    config_entry = _get_config_entry(hass)
    if not config_entry:
        raise HomeAssistantError("未找到腾讯云人脸识别配置")

    # 获取插件实例
    entry_data = _get_entry_data(hass)
    if not entry_data:
        raise HomeAssistantError("腾讯云人脸识别插件未正确初始化")
    
    face_recognition = entry_data.get("face_recognition")
    if not face_recognition:
        raise HomeAssistantError("腾讯云人脸识别插件未正确初始化")

    # 调用人脸检测功能
    try:
        image_url = data.get(ATTR_IMAGE_URL)
        image_path = data.get(ATTR_IMAGE_PATH)
        image_file = data.get(ATTR_IMAGE_FILE)
        max_face_num = data.get(ATTR_MAX_FACE_NUM, 1)
        min_face_size = data.get(ATTR_MIN_FACE_SIZE, 34)
        need_rotate_check = data.get(ATTR_NEED_ROTATE_CHECK, 1)

        result = await face_recognition.async_detect_faces(
            image_url=image_url,
            image_path=image_path,
            image_file=image_file,
            max_face_num=max_face_num,
            min_face_size=min_face_size,
            need_rotate_check=need_rotate_check
        )

        # 直接返回结果，包含状态和错误信息
        return result

    except Exception as ex:
        _LOGGER.error("人脸检测服务调用失败: %s", ex)
        # 返回错误信息，而不是抛出异常
        return {
            "success": False,
            "faces": [],
            "error": str(ex),
            "error_code": "service_error",
            "error_message": str(ex)
        }


async def async_get_face_attributes_service(call: ServiceCall) -> Dict[str, Any]:
    """获取人脸属性服务"""
    from homeassistant.exceptions import HomeAssistantError

    hass = call.hass
    data = call.data

    # 获取配置项
    config_entry = _get_config_entry(hass)
    if not config_entry:
        raise HomeAssistantError("未找到腾讯云人脸识别配置")

    # 获取插件实例
    entry_data = _get_entry_data(hass)
    if not entry_data:
        raise HomeAssistantError("腾讯云人脸识别插件未正确初始化")
    
    face_recognition = entry_data.get("face_recognition")
    if not face_recognition:
        raise HomeAssistantError("腾讯云人脸识别插件未正确初始化")

    # 调用获取人脸属性功能
    try:
        image_url = data.get(ATTR_IMAGE_URL)
        image_path = data.get(ATTR_IMAGE_PATH)
        image_file = data.get(ATTR_IMAGE_FILE)
        max_face_num = data.get(ATTR_MAX_FACE_NUM, 1)
        need_rotate_check = data.get(ATTR_NEED_ROTATE_CHECK, 1)

        result = await face_recognition.async_get_face_attributes(
            image_url=image_url,
            image_path=image_path,
            image_file=image_file,
            max_face_num=max_face_num,
            need_rotate_check=need_rotate_check
        )

        # 直接返回结果，包含状态和错误信息
        return result

    except Exception as ex:
        _LOGGER.error("获取人脸属性服务调用失败: %s", ex)
        # 返回错误信息，而不是抛出异常
        return {
            "success": False,
            "faces": [],
            "error": str(ex),
            "error_code": "service_error",
            "error_message": str(ex)
        }


def _get_config_entry(hass: HomeAssistant):
    """获取配置项"""
    for entry in hass.config_entries.async_entries(DOMAIN):
        return entry
    return None

def _get_entry_data(hass: HomeAssistant):
    """获取配置项数据"""
    for entry_id, data in hass.data.get(DOMAIN, {}).items():
        if isinstance(data, dict) and "face_recognition" in data:
            return data
    return None