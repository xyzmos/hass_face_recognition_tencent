"""服务定义"""

import logging
from typing import Dict, Any

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


def _get_face_recognition(hass: HomeAssistant, config_entry_id: str = None):
    entry_data = _get_entry_data(hass, config_entry_id)
    if not entry_data:
        raise HomeAssistantError("未找到腾讯云人脸识别配置")
    face_recognition = entry_data.get("face_recognition")
    if not face_recognition:
        raise HomeAssistantError("腾讯云人脸识别插件未正确初始化")
    return face_recognition


def _check_result(result: Dict[str, Any], operation_name: str) -> Dict[str, Any]:
    if not result.get("success", False):
        error_msg = result.get("error_message", result.get("error", "未知错误"))
        raise HomeAssistantError(f"{operation_name}失败: {error_msg}")
    return result


async def _call_service(
    call: ServiceCall,
    operation_name: str,
    method_name: str,
    **kwargs,
) -> Dict[str, Any]:
    face_recognition = _get_face_recognition(call.hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    try:
        method = getattr(face_recognition, method_name)
        result = await method(**kwargs)
        return _check_result(result, operation_name)
    except HomeAssistantError:
        raise
    except Exception as ex:
        _LOGGER.error("%s服务调用失败: %s", operation_name, ex)
        raise HomeAssistantError(f"{operation_name}服务调用失败: {ex}")


async def async_face_search_service(call: ServiceCall) -> Dict[str, Any]:
    data = call.data
    hass = call.hass

    face_recognition = _get_face_recognition(hass, data.get(ATTR_CONFIG_ENTRY_ID))
    group_id = data.get(ATTR_GROUP_ID)
    camera_entity_id = data.get(ATTR_CAMERA_ENTITY_ID)

    try:
        result = await face_recognition.async_search_faces(
            image_url=data.get(ATTR_IMAGE_URL),
            image_path=data.get(ATTR_IMAGE_PATH),
            image_file=data.get(ATTR_IMAGE_FILE),
            camera_entity_id=camera_entity_id,
            group_ids=[group_id],
            max_face_num=data.get(ATTR_MAX_FACE_NUM, 1),
            min_face_size=data.get(ATTR_MIN_FACE_SIZE, 34),
            max_user_num=data.get(ATTR_MAX_USER_NUM, 5),
            quality_control=data.get(ATTR_QUALITY_CONTROL, 1),
            need_rotate_check=data.get(ATTR_NEED_ROTATE_CHECK, 1),
            face_match_threshold=data.get(ATTR_FACE_MATCH_THRESHOLD, 60.0),
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
    data = call.data
    return await _call_service(
        call,
        "人脸检测",
        "async_detect_faces",
        image_url=data.get(ATTR_IMAGE_URL),
        image_path=data.get(ATTR_IMAGE_PATH),
        image_file=data.get(ATTR_IMAGE_FILE),
        camera_entity_id=data.get(ATTR_CAMERA_ENTITY_ID),
        max_face_num=data.get(ATTR_MAX_FACE_NUM, 1),
        min_face_size=data.get(ATTR_MIN_FACE_SIZE, 34),
        need_rotate_check=data.get(ATTR_NEED_ROTATE_CHECK, 1),
    )


async def async_get_face_attributes_service(call: ServiceCall) -> Dict[str, Any]:
    data = call.data
    return await _call_service(
        call,
        "获取人脸属性",
        "async_get_face_attributes",
        image_url=data.get(ATTR_IMAGE_URL),
        image_path=data.get(ATTR_IMAGE_PATH),
        image_file=data.get(ATTR_IMAGE_FILE),
        camera_entity_id=data.get(ATTR_CAMERA_ENTITY_ID),
        max_face_num=data.get(ATTR_MAX_FACE_NUM, 1),
        need_rotate_check=data.get(ATTR_NEED_ROTATE_CHECK, 1),
    )


async def async_create_person_service(call: ServiceCall) -> Dict[str, Any]:
    data = call.data
    return await _call_service(
        call,
        "创建人员",
        "async_create_person",
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


async def async_delete_person_service(call: ServiceCall) -> Dict[str, Any]:
    data = call.data
    return await _call_service(
        call,
        "删除人员",
        "async_delete_person",
        person_id=data.get(ATTR_PERSON_ID),
    )


async def async_create_face_service(call: ServiceCall) -> Dict[str, Any]:
    data = call.data
    return await _call_service(
        call,
        "注册人脸",
        "async_create_face",
        person_id=data.get(ATTR_PERSON_ID),
        image_url=data.get(ATTR_IMAGE_URL),
        image_path=data.get(ATTR_IMAGE_PATH),
        image_file=data.get(ATTR_IMAGE_FILE),
        camera_entity_id=data.get(ATTR_CAMERA_ENTITY_ID),
        quality_control=data.get(ATTR_QUALITY_CONTROL, 1),
        need_rotate_check=data.get(ATTR_NEED_ROTATE_CHECK, 1),
    )


async def async_delete_face_service(call: ServiceCall) -> Dict[str, Any]:
    data = call.data
    return await _call_service(
        call,
        "删除人脸",
        "async_delete_face",
        person_id=data.get(ATTR_PERSON_ID),
        face_id=data.get(ATTR_FACE_ID),
    )
