"""服务定义"""

import logging
from typing import Dict, Any, List, Optional

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_FACE_SEARCH,
    SERVICE_DETECT_FACE,
    SERVICE_GET_FACE_ATTRIBUTES,
    SERVICE_CREATE_PERSON,
    SERVICE_DELETE_PERSON,
    SERVICE_CREATE_FACE,
    SERVICE_DELETE_FACE,
    ATTR_IMAGE_URL,
    ATTR_IMAGE_FILE,
    ATTR_IMAGE_PATH,
    ATTR_CAMERA_ENTITY_ID,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_GROUP_ID,
    ATTR_MAX_FACE_NUM,
    ATTR_MIN_FACE_SIZE,
    ATTR_MAX_USER_NUM,
    ATTR_QUALITY_CONTROL,
    ATTR_NEED_ROTATE_CHECK,
    ATTR_FACE_MATCH_THRESHOLD,
    ATTR_PERSON_ID,
    ATTR_PERSON_NAME,
    ATTR_GENDER,
    ATTR_FACE_ID,
    ATTR_PERSON_TAG,
    EVENT_FACE_DETECTED,
)

_LOGGER = logging.getLogger(__name__)

FACE_SEARCH_SCHEMA = vol.Schema({
    vol.Required(ATTR_GROUP_ID): cv.string,
    vol.Optional(ATTR_IMAGE_URL): cv.string,
    vol.Optional(ATTR_IMAGE_PATH): cv.string,
    vol.Optional(ATTR_IMAGE_FILE): cv.string,
    vol.Optional(ATTR_CAMERA_ENTITY_ID): cv.string,
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    vol.Optional(ATTR_MAX_FACE_NUM, default=1): cv.positive_int,
    vol.Optional(ATTR_MIN_FACE_SIZE, default=34): cv.positive_int,
    vol.Optional(ATTR_MAX_USER_NUM, default=5): cv.positive_int,
    vol.Optional(ATTR_QUALITY_CONTROL, default=1): vol.In([0, 1]),
    vol.Optional(ATTR_NEED_ROTATE_CHECK, default=1): vol.In([0, 1]),
    vol.Optional(ATTR_FACE_MATCH_THRESHOLD, default=60.0): vol.Range(min=0, max=100),
})

DETECT_FACE_SCHEMA = vol.Schema({
    vol.Optional(ATTR_IMAGE_URL): cv.string,
    vol.Optional(ATTR_IMAGE_PATH): cv.string,
    vol.Optional(ATTR_IMAGE_FILE): cv.string,
    vol.Optional(ATTR_CAMERA_ENTITY_ID): cv.string,
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    vol.Optional(ATTR_MAX_FACE_NUM, default=1): cv.positive_int,
    vol.Optional(ATTR_MIN_FACE_SIZE, default=34): cv.positive_int,
    vol.Optional(ATTR_NEED_ROTATE_CHECK, default=1): vol.In([0, 1]),
})

GET_FACE_ATTRIBUTES_SCHEMA = vol.Schema({
    vol.Optional(ATTR_IMAGE_URL): cv.string,
    vol.Optional(ATTR_IMAGE_PATH): cv.string,
    vol.Optional(ATTR_IMAGE_FILE): cv.string,
    vol.Optional(ATTR_CAMERA_ENTITY_ID): cv.string,
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    vol.Optional(ATTR_MAX_FACE_NUM, default=1): cv.positive_int,
    vol.Optional(ATTR_NEED_ROTATE_CHECK, default=1): vol.In([0, 1]),
})

CREATE_PERSON_SCHEMA = vol.Schema({
    vol.Required(ATTR_PERSON_ID): cv.string,
    vol.Required(ATTR_PERSON_NAME): cv.string,
    vol.Required(ATTR_GROUP_ID): cv.string,
    vol.Optional(ATTR_IMAGE_URL): cv.string,
    vol.Optional(ATTR_IMAGE_PATH): cv.string,
    vol.Optional(ATTR_IMAGE_FILE): cv.string,
    vol.Optional(ATTR_CAMERA_ENTITY_ID): cv.string,
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    vol.Optional(ATTR_GENDER): vol.In([0, 1]),
    vol.Optional(ATTR_PERSON_TAG): cv.string,
    vol.Optional(ATTR_QUALITY_CONTROL, default=1): vol.In([0, 1]),
    vol.Optional(ATTR_NEED_ROTATE_CHECK, default=1): vol.In([0, 1]),
})

DELETE_PERSON_SCHEMA = vol.Schema({
    vol.Required(ATTR_PERSON_ID): cv.string,
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
})

CREATE_FACE_SCHEMA = vol.Schema({
    vol.Required(ATTR_PERSON_ID): cv.string,
    vol.Optional(ATTR_IMAGE_URL): cv.string,
    vol.Optional(ATTR_IMAGE_PATH): cv.string,
    vol.Optional(ATTR_IMAGE_FILE): cv.string,
    vol.Optional(ATTR_CAMERA_ENTITY_ID): cv.string,
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    vol.Optional(ATTR_QUALITY_CONTROL, default=1): vol.In([0, 1]),
    vol.Optional(ATTR_NEED_ROTATE_CHECK, default=1): vol.In([0, 1]),
})

DELETE_FACE_SCHEMA = vol.Schema({
    vol.Required(ATTR_PERSON_ID): cv.string,
    vol.Required(ATTR_FACE_ID): cv.string,
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
})


async def async_setup_services(hass: HomeAssistant) -> None:
    """设置服务"""
    if hass.services.has_service(DOMAIN, SERVICE_FACE_SEARCH):
        return

    _LOGGER.info("设置腾讯云人脸识别服务")

    hass.services.async_register(
        DOMAIN,
        SERVICE_FACE_SEARCH,
        async_face_search_service,
        schema=FACE_SEARCH_SCHEMA,
        supports_response=True
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_DETECT_FACE,
        async_detect_face_service,
        schema=DETECT_FACE_SCHEMA,
        supports_response=True
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_FACE_ATTRIBUTES,
        async_get_face_attributes_service,
        schema=GET_FACE_ATTRIBUTES_SCHEMA,
        supports_response=True
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_PERSON,
        async_create_person_service,
        schema=CREATE_PERSON_SCHEMA,
        supports_response=True
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_PERSON,
        async_delete_person_service,
        schema=DELETE_PERSON_SCHEMA,
        supports_response=True
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_FACE,
        async_create_face_service,
        schema=CREATE_FACE_SCHEMA,
        supports_response=True
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_FACE,
        async_delete_face_service,
        schema=DELETE_FACE_SCHEMA,
        supports_response=True
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """卸载服务"""
    if any(hass.config_entries.async_entries(DOMAIN)):
        return

    _LOGGER.info("卸载腾讯云人脸识别服务")

    for service_name in [
        SERVICE_FACE_SEARCH,
        SERVICE_DETECT_FACE,
        SERVICE_GET_FACE_ATTRIBUTES,
        SERVICE_CREATE_PERSON,
        SERVICE_DELETE_PERSON,
        SERVICE_CREATE_FACE,
        SERVICE_DELETE_FACE,
    ]:
        hass.services.async_remove(DOMAIN, service_name)


def _get_entry_data(hass: HomeAssistant, config_entry_id: str = None):
    """获取配置项数据，支持多配置条目"""
    domain_data = hass.data.get(DOMAIN, {})
    if config_entry_id:
        data = domain_data.get(config_entry_id)
        if data and isinstance(data, dict) and "face_recognition" in data:
            return data
        return None

    for entry_id, data in domain_data.items():
        if isinstance(data, dict) and "face_recognition" in data:
            return data
    return None


async def async_face_search_service(call: ServiceCall) -> Dict[str, Any]:
    """人脸搜索服务"""
    hass = call.hass
    data = call.data

    entry_data = _get_entry_data(hass, data.get(ATTR_CONFIG_ENTRY_ID))
    if not entry_data:
        raise HomeAssistantError("未找到腾讯云人脸识别配置")

    face_recognition = entry_data.get("face_recognition")
    if not face_recognition:
        raise HomeAssistantError("腾讯云人脸识别插件未正确初始化")

    try:
        group_id = data.get(ATTR_GROUP_ID)
        image_url = data.get(ATTR_IMAGE_URL)
        image_path = data.get(ATTR_IMAGE_PATH)
        image_file = data.get(ATTR_IMAGE_FILE)
        camera_entity_id = data.get(ATTR_CAMERA_ENTITY_ID)
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
            camera_entity_id=camera_entity_id,
            group_ids=[group_id],
            max_face_num=max_face_num,
            min_face_size=min_face_size,
            max_user_num=max_user_num,
            quality_control=quality_control,
            need_rotate_check=need_rotate_check,
            face_match_threshold=face_match_threshold
        )

        if result.get("success", False):
            for face in result.get("faces", []):
                for candidate in face.get("candidates", []):
                    hass.bus.async_fire(EVENT_FACE_DETECTED, {
                        ATTR_PERSON_ID: candidate.get("person_id"),
                        ATTR_PERSON_NAME: candidate.get("person_name"),
                        "score": candidate.get("score"),
                        ATTR_PERSON_TAG: candidate.get("person_tag"),
                        ATTR_GROUP_ID: group_id,
                        ATTR_CAMERA_ENTITY_ID: camera_entity_id,
                    })

        return result

    except HomeAssistantError:
        raise
    except Exception as ex:
        _LOGGER.error("人脸搜索服务调用失败: %s", ex)
        raise HomeAssistantError(f"人脸搜索服务调用失败: {ex}")


async def async_detect_face_service(call: ServiceCall) -> Dict[str, Any]:
    """人脸检测服务"""
    hass = call.hass
    data = call.data

    entry_data = _get_entry_data(hass, data.get(ATTR_CONFIG_ENTRY_ID))
    if not entry_data:
        raise HomeAssistantError("未找到腾讯云人脸识别配置")

    face_recognition = entry_data.get("face_recognition")
    if not face_recognition:
        raise HomeAssistantError("腾讯云人脸识别插件未正确初始化")

    try:
        image_url = data.get(ATTR_IMAGE_URL)
        image_path = data.get(ATTR_IMAGE_PATH)
        image_file = data.get(ATTR_IMAGE_FILE)
        camera_entity_id = data.get(ATTR_CAMERA_ENTITY_ID)
        max_face_num = data.get(ATTR_MAX_FACE_NUM, 1)
        min_face_size = data.get(ATTR_MIN_FACE_SIZE, 34)
        need_rotate_check = data.get(ATTR_NEED_ROTATE_CHECK, 1)

        result = await face_recognition.async_detect_faces(
            image_url=image_url,
            image_path=image_path,
            image_file=image_file,
            camera_entity_id=camera_entity_id,
            max_face_num=max_face_num,
            min_face_size=min_face_size,
            need_rotate_check=need_rotate_check
        )

        if not result.get("success", False):
            error_msg = result.get("error_message", result.get("error", "未知错误"))
            raise HomeAssistantError(f"人脸检测失败: {error_msg}")

        return result

    except HomeAssistantError:
        raise
    except Exception as ex:
        _LOGGER.error("人脸检测服务调用失败: %s", ex)
        raise HomeAssistantError(f"人脸检测服务调用失败: {ex}")


async def async_get_face_attributes_service(call: ServiceCall) -> Dict[str, Any]:
    """获取人脸属性服务"""
    hass = call.hass
    data = call.data

    entry_data = _get_entry_data(hass, data.get(ATTR_CONFIG_ENTRY_ID))
    if not entry_data:
        raise HomeAssistantError("未找到腾讯云人脸识别配置")

    face_recognition = entry_data.get("face_recognition")
    if not face_recognition:
        raise HomeAssistantError("腾讯云人脸识别插件未正确初始化")

    try:
        image_url = data.get(ATTR_IMAGE_URL)
        image_path = data.get(ATTR_IMAGE_PATH)
        image_file = data.get(ATTR_IMAGE_FILE)
        camera_entity_id = data.get(ATTR_CAMERA_ENTITY_ID)
        max_face_num = data.get(ATTR_MAX_FACE_NUM, 1)
        need_rotate_check = data.get(ATTR_NEED_ROTATE_CHECK, 1)

        result = await face_recognition.async_get_face_attributes(
            image_url=image_url,
            image_path=image_path,
            image_file=image_file,
            camera_entity_id=camera_entity_id,
            max_face_num=max_face_num,
            need_rotate_check=need_rotate_check
        )

        if not result.get("success", False):
            error_msg = result.get("error_message", result.get("error", "未知错误"))
            raise HomeAssistantError(f"获取人脸属性失败: {error_msg}")

        return result

    except HomeAssistantError:
        raise
    except Exception as ex:
        _LOGGER.error("获取人脸属性服务调用失败: %s", ex)
        raise HomeAssistantError(f"获取人脸属性服务调用失败: {ex}")


async def async_create_person_service(call: ServiceCall) -> Dict[str, Any]:
    """创建人员服务"""
    hass = call.hass
    data = call.data

    entry_data = _get_entry_data(hass, data.get(ATTR_CONFIG_ENTRY_ID))
    if not entry_data:
        raise HomeAssistantError("未找到腾讯云人脸识别配置")

    face_recognition = entry_data.get("face_recognition")
    if not face_recognition:
        raise HomeAssistantError("腾讯云人脸识别插件未正确初始化")

    try:
        result = await face_recognition.async_create_person(
            person_id=data.get(ATTR_PERSON_ID),
            person_name=data.get(ATTR_PERSON_NAME),
            group_id=data.get(ATTR_GROUP_ID),
            image_url=data.get(ATTR_IMAGE_URL),
            image_path=data.get(ATTR_IMAGE_PATH),
            image_file=data.get(ATTR_IMAGE_FILE),
            camera_entity_id=data.get(ATTR_CAMERA_ENTITY_ID),
            gender=data.get(ATTR_GENDER),
            person_tag=data.get(ATTR_PERSON_TAG),
            quality_control=data.get(ATTR_QUALITY_CONTROL, 1),
            need_rotate_check=data.get(ATTR_NEED_ROTATE_CHECK, 1),
        )

        if not result.get("success", False):
            error_msg = result.get("error_message", result.get("error", "未知错误"))
            raise HomeAssistantError(f"创建人员失败: {error_msg}")

        return result

    except HomeAssistantError:
        raise
    except Exception as ex:
        _LOGGER.error("创建人员服务调用失败: %s", ex)
        raise HomeAssistantError(f"创建人员服务调用失败: {ex}")


async def async_delete_person_service(call: ServiceCall) -> Dict[str, Any]:
    """删除人员服务"""
    hass = call.hass
    data = call.data

    entry_data = _get_entry_data(hass, data.get(ATTR_CONFIG_ENTRY_ID))
    if not entry_data:
        raise HomeAssistantError("未找到腾讯云人脸识别配置")

    face_recognition = entry_data.get("face_recognition")
    if not face_recognition:
        raise HomeAssistantError("腾讯云人脸识别插件未正确初始化")

    try:
        result = await face_recognition.async_delete_person(
            person_id=data.get(ATTR_PERSON_ID),
        )

        if not result.get("success", False):
            error_msg = result.get("error_message", result.get("error", "未知错误"))
            raise HomeAssistantError(f"删除人员失败: {error_msg}")

        return result

    except HomeAssistantError:
        raise
    except Exception as ex:
        _LOGGER.error("删除人员服务调用失败: %s", ex)
        raise HomeAssistantError(f"删除人员服务调用失败: {ex}")


async def async_create_face_service(call: ServiceCall) -> Dict[str, Any]:
    """注册人脸服务"""
    hass = call.hass
    data = call.data

    entry_data = _get_entry_data(hass, data.get(ATTR_CONFIG_ENTRY_ID))
    if not entry_data:
        raise HomeAssistantError("未找到腾讯云人脸识别配置")

    face_recognition = entry_data.get("face_recognition")
    if not face_recognition:
        raise HomeAssistantError("腾讯云人脸识别插件未正确初始化")

    try:
        result = await face_recognition.async_create_face(
            person_id=data.get(ATTR_PERSON_ID),
            image_url=data.get(ATTR_IMAGE_URL),
            image_path=data.get(ATTR_IMAGE_PATH),
            image_file=data.get(ATTR_IMAGE_FILE),
            camera_entity_id=data.get(ATTR_CAMERA_ENTITY_ID),
            quality_control=data.get(ATTR_QUALITY_CONTROL, 1),
            need_rotate_check=data.get(ATTR_NEED_ROTATE_CHECK, 1),
        )

        if not result.get("success", False):
            error_msg = result.get("error_message", result.get("error", "未知错误"))
            raise HomeAssistantError(f"注册人脸失败: {error_msg}")

        return result

    except HomeAssistantError:
        raise
    except Exception as ex:
        _LOGGER.error("注册人脸服务调用失败: %s", ex)
        raise HomeAssistantError(f"注册人脸服务调用失败: {ex}")


async def async_delete_face_service(call: ServiceCall) -> Dict[str, Any]:
    """删除人脸服务"""
    hass = call.hass
    data = call.data

    entry_data = _get_entry_data(hass, data.get(ATTR_CONFIG_ENTRY_ID))
    if not entry_data:
        raise HomeAssistantError("未找到腾讯云人脸识别配置")

    face_recognition = entry_data.get("face_recognition")
    if not face_recognition:
        raise HomeAssistantError("腾讯云人脸识别插件未正确初始化")

    try:
        result = await face_recognition.async_delete_face(
            person_id=data.get(ATTR_PERSON_ID),
            face_id=data.get(ATTR_FACE_ID),
        )

        if not result.get("success", False):
            error_msg = result.get("error_message", result.get("error", "未知错误"))
            raise HomeAssistantError(f"删除人脸失败: {error_msg}")

        return result

    except HomeAssistantError:
        raise
    except Exception as ex:
        _LOGGER.error("删除人脸服务调用失败: %s", ex)
        raise HomeAssistantError(f"删除人脸服务调用失败: {ex}")
