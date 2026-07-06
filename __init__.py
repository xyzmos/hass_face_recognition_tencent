"""
腾讯云人脸识别 Home Assistant 插件
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError

from homeassistant.components import websocket_api
from homeassistant.components.camera import async_get_image

from .const import (
    CONF_PERSON_GROUP_ID,
    CONF_REGION,
    CONF_SECRET_ID,
    CONF_SECRET_KEY,
    DOMAIN,
    PLATFORMS,
    get_entry_value,
)
from .errors import AuthenticationError, NetworkError
from .face_recognition import FaceRecognition
from .services import async_setup_services, async_unload_services
from .tencent_cloud_client import TencentCloudClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置配置项。"""
    _LOGGER.info("设置腾讯云人脸识别插件: %s", entry.entry_id)

    secret_id = entry.data.get(CONF_SECRET_ID)
    secret_key = entry.data.get(CONF_SECRET_KEY)
    region = get_entry_value(entry, CONF_REGION, "ap-shanghai")
    person_group_id = get_entry_value(entry, CONF_PERSON_GROUP_ID, "Hass")

    # 1. 创建客户端
    try:
        client = TencentCloudClient(secret_id, secret_key, region)
    except Exception as ex:  # noqa: BLE001
        _LOGGER.error("创建腾讯云客户端失败: %s", ex)
        raise ConfigEntryNotReady(f"创建腾讯云客户端失败: {ex}") from ex

    # 2. 验证凭据（失败则让 HA 稍后重试 setup）
    try:
        await hass.async_add_executor_job(client.verify_credentials)
    except (AuthenticationError, NetworkError) as ex:
        _LOGGER.error("腾讯云凭据验证失败: %s", ex)
        await hass.async_add_executor_job(client.close)
        raise ConfigEntryNotReady(f"腾讯云凭据验证失败: {ex}") from ex
    except Exception as ex:  # noqa: BLE001
        _LOGGER.warning("腾讯云凭据验证异常（将继续加载）: %s", ex)

    # 3. 构建核心功能与存储
    face_recognition = FaceRecognition(hass, client)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "entry": entry,
        "client": client,
        "face_recognition": face_recognition,
        "secret_id": secret_id,
        "region": region,
        "person_group_id": person_group_id,
    }

    # 4. 注册服务
    await async_setup_services(hass)

    # 5. 注册 WebSocket API 命令
    websocket_api.async_register_command(hass, ws_list_persons)
    websocket_api.async_register_command(hass, ws_create_person)
    websocket_api.async_register_command(hass, ws_delete_person)

    # 6. 前向设置平台（sensor）
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 6. 配置项更新时自动重新加载平台
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _LOGGER.info("腾讯云人脸识别插件设置完成")
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """配置项选项变更时重新加载。"""
    _LOGGER.debug("配置项变更，重新加载: %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载配置项。"""
    _LOGGER.info("卸载腾讯云人脸识别插件: %s", entry.entry_id)

    # 使用统一的卸载 API（兼容新版 HA）
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    entry_data: Dict[str, Any] = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    if entry_data and "client" in entry_data:
        client: TencentCloudClient = entry_data["client"]
        try:
            await hass.async_add_executor_job(client.close)
        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning("关闭腾讯云客户端时出错: %s", ex)

    # 若已无该域的配置项，则卸载服务
    if not hass.data.get(DOMAIN):
        await async_unload_services(hass)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """移除配置项。"""
    _LOGGER.info("移除腾讯云人脸识别插件配置: %s", entry.entry_id)
    # 客户端资源已在 unload 时释放；这里仅做兜底清理
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data and "client" in data:
        try:
            await hass.async_add_executor_job(data["client"].close)
        except Exception:  # noqa: BLE001
            pass


# --- WebSocket API ---------------------------------------------------------


@websocket_api.websocket_command({
    "type": "tencent_face_recognition/list_persons",
})
@websocket_api.async_response
async def ws_list_persons(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: Dict[str, Any]
) -> None:
    """列出所有人员。"""
    entry_data = None
    for data in hass.data.get(DOMAIN, {}).values():
        if isinstance(data, dict) and "client" in data:
            entry_data = data
            break
    if not entry_data:
        connection.send_error(msg["id"], "not_found", "未找到配置")
        return

    client: TencentCloudClient = entry_data["client"]
    group_id = entry_data.get("person_group_id", "Hass")
    try:
        result = await hass.async_add_executor_job(client.get_person_list_all, group_id)
        connection.send_result(msg["id"], result)
    except Exception as ex:
        _LOGGER.error("列出人员失败: %s", ex)
        connection.send_error(msg["id"], "api_error", str(ex))


@websocket_api.websocket_command({
    "type": "tencent_face_recognition/create_person",
    "data": {
        "person_id": str,
        "person_name": str,
        "camera_entity_id": str,
    },
})
@websocket_api.async_response
async def ws_create_person(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: Dict[str, Any]
) -> None:
    """通过摄像头创建人员。"""
    entry_data = None
    for data in hass.data.get(DOMAIN, {}).values():
        if isinstance(data, dict) and "client" in data:
            entry_data = data
            break
    if not entry_data:
        connection.send_error(msg["id"], "not_found", "未找到配置")
        return

    client: TencentCloudClient = entry_data["client"]
    group_id = entry_data.get("person_group_id", "Hass")
    person_id = msg["data"]["person_id"]
    person_name = msg["data"]["person_name"]
    camera_entity_id = msg["data"]["camera_entity_id"]

    try:
        image = await async_get_image(hass, camera_entity_id)
        image_base64 = base64.b64encode(image.content).decode("utf-8")
        result = await hass.async_add_executor_job(
            client.create_person,
            person_id, person_name, group_id,
            None, None, None, image_base64,
        )
        connection.send_result(msg["id"], result)
    except Exception as ex:
        _LOGGER.error("创建人员失败: %s", ex)
        connection.send_error(msg["id"], "api_error", str(ex))


@websocket_api.websocket_command({
    "type": "tencent_face_recognition/delete_person",
    "data": {"person_id": str},
})
@websocket_api.async_response
async def ws_delete_person(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: Dict[str, Any]
) -> None:
    """删除人员。"""
    entry_data = None
    for data in hass.data.get(DOMAIN, {}).values():
        if isinstance(data, dict) and "client" in data:
            entry_data = data
            break
    if not entry_data:
        connection.send_error(msg["id"], "not_found", "未找到配置")
        return

    client: TencentCloudClient = entry_data["client"]
    person_id = msg["data"]["person_id"]
    try:
        result = await hass.async_add_executor_job(client.delete_person, person_id)
        connection.send_result(msg["id"], result)
    except Exception as ex:
        _LOGGER.error("删除人员失败: %s", ex)
        connection.send_error(msg["id"], "api_error", str(ex))
