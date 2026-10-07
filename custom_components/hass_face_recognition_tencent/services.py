"""服务定义"""

from __future__ import annotations

import logging
from typing import Any, Dict

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import SupportsResponse

from .errors import FaceNotDetectedError

from .const import (
    ATTR_CAMERA_ENTITY_ID,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_FACE_ID,
    ATTR_FACE_MATCH_THRESHOLD,
    ATTR_GENDER,
    ATTR_GROUP_ID,
    ATTR_IMAGE_FILE,
    ATTR_IMAGE_PATH,
    ATTR_IMAGE_URL,
    ATTR_MAX_FACE_NUM,
    ATTR_MAX_USER_NUM,
    ATTR_MIN_FACE_SIZE,
    ATTR_NEED_ROTATE_CHECK,
    ATTR_PERSON_ID,
    ATTR_PERSON_NAME,
    ATTR_PERSON_TAG,
    ATTR_QUALITY_CONTROL,
    CONF_PERSON_GROUP_ID,
    DEFAULT_PERSON_GROUP_ID,
    DOMAIN,
    EVENT_FACE_DETECTED,
    EVENT_FACE_DETECTED_LEGACY,
    SERVICE_CREATE_FACE,
    SERVICE_CREATE_PERSON,
    SERVICE_DELETE_FACE,
    SERVICE_DELETE_PERSON,
    SERVICE_DETECT_FACE,
    SERVICE_FACE_SEARCH,
    SERVICE_GET_FACE_ATTRIBUTES,
    get_entry_value,
)

_LOGGER = logging.getLogger(__name__)

_IMAGE_FIELDS = {
    vol.Optional(ATTR_IMAGE_URL): cv.string,
    vol.Optional(ATTR_IMAGE_PATH): cv.string,
    vol.Optional(ATTR_IMAGE_FILE): cv.string,
    vol.Optional(ATTR_CAMERA_ENTITY_ID): cv.entity_id,
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
}

FACE_SEARCH_SCHEMA = vol.Schema({
    vol.Optional(ATTR_GROUP_ID): cv.string,
    **_IMAGE_FIELDS,
    vol.Optional(ATTR_MAX_FACE_NUM, default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
    vol.Optional(ATTR_MIN_FACE_SIZE, default=34): vol.All(vol.Coerce(int), vol.Range(min=20, max=4096)),
    vol.Optional(ATTR_MAX_USER_NUM, default=5): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
    vol.Optional(ATTR_QUALITY_CONTROL, default=1): vol.All(vol.Coerce(int), vol.Range(min=0, max=4)),
    vol.Optional(ATTR_NEED_ROTATE_CHECK, default=1): vol.All(vol.Coerce(int), vol.In([0, 1])),
    vol.Optional(ATTR_FACE_MATCH_THRESHOLD, default=60.0): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
})

DETECT_FACE_SCHEMA = vol.Schema({
    **_IMAGE_FIELDS,
    vol.Optional(ATTR_MAX_FACE_NUM, default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=120)),
    vol.Optional(ATTR_MIN_FACE_SIZE, default=34): vol.All(vol.Coerce(int), vol.Range(min=20, max=4096)),
    vol.Optional(ATTR_NEED_ROTATE_CHECK, default=1): vol.All(vol.Coerce(int), vol.In([0, 1])),
})

GET_FACE_ATTRIBUTES_SCHEMA = vol.Schema({
    **_IMAGE_FIELDS,
    vol.Optional(ATTR_MAX_FACE_NUM, default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=120)),
    vol.Optional(ATTR_NEED_ROTATE_CHECK, default=1): vol.All(vol.Coerce(int), vol.In([0, 1])),
})

CREATE_PERSON_SCHEMA = vol.Schema({
    vol.Required(ATTR_PERSON_ID): cv.string,
    vol.Required(ATTR_PERSON_NAME): cv.string,
    vol.Optional(ATTR_GROUP_ID): cv.string,
    **_IMAGE_FIELDS,
    vol.Optional(ATTR_GENDER): vol.All(vol.Coerce(int), vol.In([0, 1, 2])),
    vol.Optional(ATTR_PERSON_TAG): cv.string,
    vol.Optional(ATTR_QUALITY_CONTROL, default=1): vol.All(vol.Coerce(int), vol.Range(min=0, max=4)),
    vol.Optional(ATTR_NEED_ROTATE_CHECK, default=1): vol.All(vol.Coerce(int), vol.In([0, 1])),
    vol.Optional("unique_person_control"): vol.All(vol.Coerce(int), vol.In([0, 1, 2, 3, 4])),
})

DELETE_PERSON_SCHEMA = vol.Schema({
    vol.Required(ATTR_PERSON_ID): cv.string,
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
})

CREATE_FACE_SCHEMA = vol.Schema({
    vol.Required(ATTR_PERSON_ID): cv.string,
    **_IMAGE_FIELDS,
    vol.Optional(ATTR_QUALITY_CONTROL, default=1): vol.All(vol.Coerce(int), vol.Range(min=0, max=4)),
    vol.Optional(ATTR_NEED_ROTATE_CHECK, default=1): vol.All(vol.Coerce(int), vol.In([0, 1])),
    vol.Optional(ATTR_FACE_MATCH_THRESHOLD): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
})

DELETE_FACE_SCHEMA = vol.Schema({
    vol.Required(ATTR_PERSON_ID): cv.string,
    vol.Required(ATTR_FACE_ID): cv.string,
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
})

SERVICES = (
    SERVICE_FACE_SEARCH,
    SERVICE_DETECT_FACE,
    SERVICE_GET_FACE_ATTRIBUTES,
    SERVICE_CREATE_PERSON,
    SERVICE_DELETE_PERSON,
    SERVICE_CREATE_FACE,
    SERVICE_DELETE_FACE,
)


async def async_setup_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_FACE_SEARCH):
        return

    _LOGGER.info("注册腾讯云人脸识别服务")

    for name, handler, schema in (
        (SERVICE_FACE_SEARCH, async_face_search_service, FACE_SEARCH_SCHEMA),
        (SERVICE_DETECT_FACE, async_detect_face_service, DETECT_FACE_SCHEMA),
        (SERVICE_GET_FACE_ATTRIBUTES, async_get_face_attributes_service, GET_FACE_ATTRIBUTES_SCHEMA),
        (SERVICE_CREATE_PERSON, async_create_person_service, CREATE_PERSON_SCHEMA),
        (SERVICE_DELETE_PERSON, async_delete_person_service, DELETE_PERSON_SCHEMA),
        (SERVICE_CREATE_FACE, async_create_face_service, CREATE_FACE_SCHEMA),
        (SERVICE_DELETE_FACE, async_delete_face_service, DELETE_FACE_SCHEMA),
    ):
        hass.services.async_register(
            DOMAIN, name, handler, schema=schema,
            supports_response=SupportsResponse.OPTIONAL,
        )


async def async_unload_services(hass: HomeAssistant) -> None:
    if hass.config_entries.async_entries(DOMAIN):
        return
    _LOGGER.info("卸载腾讯云人脸识别服务")
    for name in SERVICES:
        hass.services.async_remove(DOMAIN, name)


def _get_entry(call: ServiceCall, config_entry_id: str | None):
    """按 config_entry_id 取配置项；缺省取第一个已加载的。"""
    hass = call.hass
    if config_entry_id:
        entry = hass.config_entries.async_get_entry(config_entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(f"无效的配置项ID: {config_entry_id}")
        if getattr(entry, "runtime_data", None) is None:
            raise ServiceValidationError(f"配置项未加载: {config_entry_id}")
        return entry
    for e in hass.config_entries.async_entries(DOMAIN):
        if getattr(e, "runtime_data", None) is not None:
            return e
    raise ServiceValidationError("未找到已加载的腾讯云人脸识别配置项")


def _group_id(call: ServiceCall, entry) -> str:
    """group_id 缺省回退到该配置项的默认人员库。"""
    return call.data.get(ATTR_GROUP_ID) or get_entry_value(
        entry, CONF_PERSON_GROUP_ID, DEFAULT_PERSON_GROUP_ID
    )


def _image_kwargs(data) -> Dict[str, Any]:
    return {
        "image_url": data.get(ATTR_IMAGE_URL),
        "image_path": data.get(ATTR_IMAGE_PATH),
        "image_file": data.get(ATTR_IMAGE_FILE),
        "camera_entity_id": data.get(ATTR_CAMERA_ENTITY_ID),
    }


def _check(result: Dict[str, Any], op: str) -> Dict[str, Any]:
    if not result.get("success", False):
        raise HomeAssistantError(
            f"{op}失败: {result.get('error_message', result.get('error', '未知错误'))}"
        )
    return result


def _fire_detected(hass: HomeAssistant, payload: Dict[str, Any]) -> None:
    """同时派发命名空间事件与兼容旧事件名。"""
    hass.bus.async_fire(EVENT_FACE_DETECTED, payload)
    hass.bus.async_fire(EVENT_FACE_DETECTED_LEGACY, payload)


def _empty_faces_result(op: str, ex: Exception) -> Dict[str, Any]:
    """「图片中无人脸」属于正常结果而非异常：返回空结果，避免中断自动化。"""
    _LOGGER.info("%s: 图片中未检测到人脸（%s）", op, ex)
    return {
        "success": True,
        "faces": [],
        "face_count": 0,
        "face_model_version": "",
        "no_face": True,
        "error_code": "NoFaceInPhoto",
        "error": None,
        "error_message": None,
    }


async def _invoke(
    call: ServiceCall, op: str, method: str, **kwargs
) -> ServiceResponse:
    entry = _get_entry(call, call.data.get(ATTR_CONFIG_ENTRY_ID))
    try:
        result = await getattr(entry.runtime_data.face_recognition, method)(**kwargs)
        return _check(result, op)
    except FaceNotDetectedError as ex:
        return _empty_faces_result(op, ex)
    except (HomeAssistantError, ServiceValidationError):
        raise
    except Exception as ex:
        _LOGGER.error("%s服务调用失败: %s", op, ex)
        raise HomeAssistantError(f"{op}服务调用失败: {ex}") from ex


async def async_face_search_service(call: ServiceCall) -> ServiceResponse:
    entry = _get_entry(call, call.data.get(ATTR_CONFIG_ENTRY_ID))
    data = call.data
    group_id = _group_id(call, entry)
    try:
        result = await entry.runtime_data.face_recognition.async_search_faces(
            **_image_kwargs(data),
            group_ids=[group_id],
            max_face_num=data[ATTR_MAX_FACE_NUM],
            min_face_size=data[ATTR_MIN_FACE_SIZE],
            max_user_num=data[ATTR_MAX_USER_NUM],
            quality_control=data[ATTR_QUALITY_CONTROL],
            need_rotate_check=data[ATTR_NEED_ROTATE_CHECK],
            face_match_threshold=data[ATTR_FACE_MATCH_THRESHOLD],
        )
    except FaceNotDetectedError as ex:
        return _empty_faces_result("人脸搜索", ex)
    except (HomeAssistantError, ServiceValidationError):
        raise
    except Exception as ex:
        _LOGGER.error("人脸搜索服务调用失败: %s", ex)
        raise HomeAssistantError(f"人脸搜索服务调用失败: {ex}") from ex

    if result.get("success", False):
        camera = data.get(ATTR_CAMERA_ENTITY_ID)
        for face in result.get("faces", []):
            for c in face.get("candidates", []):
                _fire_detected(call.hass, {
                    ATTR_PERSON_ID: c.get("person_id"),
                    ATTR_PERSON_NAME: c.get("person_name"),
                    "score": c.get("score"),
                    ATTR_FACE_ID: c.get("face_id"),
                    "gender": c.get("gender"),
                    ATTR_GROUP_ID: group_id,
                    ATTR_CAMERA_ENTITY_ID: camera,
                })
    return result


async def async_detect_face_service(call: ServiceCall) -> ServiceResponse:
    d = call.data
    return await _invoke(
        call, "人脸检测", "async_detect_faces",
        **_image_kwargs(d),
        max_face_num=d[ATTR_MAX_FACE_NUM],
        min_face_size=d[ATTR_MIN_FACE_SIZE],
        need_rotate_check=d[ATTR_NEED_ROTATE_CHECK],
    )


async def async_get_face_attributes_service(call: ServiceCall) -> ServiceResponse:
    d = call.data
    return await _invoke(
        call, "获取人脸属性", "async_get_face_attributes",
        **_image_kwargs(d),
        max_face_num=d[ATTR_MAX_FACE_NUM],
        need_rotate_check=d[ATTR_NEED_ROTATE_CHECK],
    )


async def async_create_person_service(call: ServiceCall) -> ServiceResponse:
    d = call.data
    entry = _get_entry(call, d.get(ATTR_CONFIG_ENTRY_ID))
    return await _invoke(
        call, "创建人员", "async_create_person",
        person_id=d[ATTR_PERSON_ID],
        person_name=d[ATTR_PERSON_NAME],
        group_id=_group_id(call, entry),
        **_image_kwargs(d),
        gender=d.get(ATTR_GENDER),
        person_tag=d.get(ATTR_PERSON_TAG),
        quality_control=d[ATTR_QUALITY_CONTROL],
        need_rotate_check=d[ATTR_NEED_ROTATE_CHECK],
        unique_person_control=d.get("unique_person_control"),
    )


async def async_delete_person_service(call: ServiceCall) -> ServiceResponse:
    return await _invoke(
        call, "删除人员", "async_delete_person",
        person_id=call.data[ATTR_PERSON_ID],
    )


async def async_create_face_service(call: ServiceCall) -> ServiceResponse:
    d = call.data
    return await _invoke(
        call, "注册人脸", "async_create_face",
        person_id=d[ATTR_PERSON_ID],
        **_image_kwargs(d),
        quality_control=d[ATTR_QUALITY_CONTROL],
        need_rotate_check=d[ATTR_NEED_ROTATE_CHECK],
        face_match_threshold=d.get(ATTR_FACE_MATCH_THRESHOLD),
    )


async def async_delete_face_service(call: ServiceCall) -> ServiceResponse:
    return await _invoke(
        call, "删除人脸", "async_delete_face",
        person_id=call.data[ATTR_PERSON_ID],
        face_id=call.data[ATTR_FACE_ID],
    )
