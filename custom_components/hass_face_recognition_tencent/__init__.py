"""腾讯云人脸识别 Home Assistant 集成"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from homeassistant.components import websocket_api
from homeassistant.components.camera import async_get_image
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

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

DATA_WS_REGISTERED = "ws_registered"

# hassfest 要求：实现了 async_setup 的集成需声明 CONFIG_SCHEMA（仅支持 UI 配置项）
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type TFRConfigEntry = ConfigEntry[TFRRuntimeData]


@dataclass
class TFRRuntimeData:
    """单个配置项的运行时数据。"""

    client: TencentCloudClient
    face_recognition: FaceRecognition
    secret_id: str
    region: str
    person_group_id: str
    coordinator: Optional[Any] = None


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """集成级初始化：注册服务与 WebSocket 命令（一次性，幂等）。"""
    await async_setup_services(hass)

    data = hass.data.setdefault(DOMAIN, {})
    if not data.get(DATA_WS_REGISTERED):
        websocket_api.async_register_command(hass, ws_list_persons)
        websocket_api.async_register_command(hass, ws_create_person)
        websocket_api.async_register_command(hass, ws_delete_person)
        data[DATA_WS_REGISTERED] = True

    return True


async def async_setup_entry(hass: HomeAssistant, entry: TFRConfigEntry) -> bool:
    """设置配置项。"""
    _LOGGER.info("设置腾讯云人脸识别集成: %s", entry.entry_id)

    secret_id = entry.data.get(CONF_SECRET_ID)
    secret_key = entry.data.get(CONF_SECRET_KEY)
    region = get_entry_value(entry, CONF_REGION, "ap-shanghai")
    person_group_id = get_entry_value(entry, CONF_PERSON_GROUP_ID, "Hass")

    # 1. 创建客户端
    try:
        client = TencentCloudClient(secret_id, secret_key, region)
    except AuthenticationError:
        raise
    except Exception as ex:  # noqa: BLE001
        raise ConfigEntryNotReady(f"创建腾讯云客户端失败: {ex}") from ex

    # 2. 验证凭据：认证失败触发 reauth，网络问题稍后重试
    try:
        await hass.async_add_executor_job(client.verify_credentials)
    except AuthenticationError as ex:
        await hass.async_add_executor_job(client.close)
        raise ConfigEntryAuthFailed(f"腾讯云凭据无效: {ex}") from ex
    except NetworkError as ex:
        await hass.async_add_executor_job(client.close)
        raise ConfigEntryNotReady(f"连接腾讯云失败: {ex}") from ex
    except Exception as ex:  # noqa: BLE001
        _LOGGER.warning("腾讯云凭据验证异常（继续加载）: %s", ex)

    # 3. 运行时数据存入 entry.runtime_data
    entry.runtime_data = TFRRuntimeData(
        client=client,
        face_recognition=FaceRecognition(hass, client),
        secret_id=secret_id,
        region=region,
        person_group_id=person_group_id,
    )

    # 4. 前向加载平台
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 5. 选项变更时自动重载
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _LOGGER.info("腾讯云人脸识别集成设置完成")
    return True


async def _async_update_listener(hass: HomeAssistant, entry: TFRConfigEntry) -> None:
    """选项变更时重载。"""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TFRConfigEntry) -> bool:
    """卸载配置项。"""
    _LOGGER.info("卸载腾讯云人脸识别集成: %s", entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    runtime = getattr(entry, "runtime_data", None)
    if runtime is not None and getattr(runtime, "client", None) is not None:
        try:
            await hass.async_add_executor_job(runtime.client.close)
        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning("关闭腾讯云客户端时出错: %s", ex)
        runtime.client = None

    # 全部配置项卸载后移除服务
    if not hass.config_entries.async_entries(DOMAIN):
        await async_unload_services(hass)

    return True


async def async_remove_entry(hass: HomeAssistant, entry: TFRConfigEntry) -> None:
    """移除配置项时的兜底清理。"""
    runtime = getattr(entry, "runtime_data", None)
    if runtime is not None and getattr(runtime, "client", None) is not None:
        try:
            await hass.async_add_executor_job(runtime.client.close)
        except Exception:  # noqa: BLE001
            pass


def _first_entry(hass: HomeAssistant) -> Optional[TFRConfigEntry]:
    """返回第一个已加载运行时数据的配置项。"""
    for e in hass.config_entries.async_entries(DOMAIN):
        if getattr(e, "runtime_data", None) is not None:
            return e
    return None


# --- WebSocket API ---------------------------------------------------------


@websocket_api.websocket_command({"type": f"{DOMAIN}/list_persons"})
@websocket_api.async_response
async def ws_list_persons(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: Dict[str, Any]
) -> None:
    entry = _first_entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_found", "未找到配置")
        return
    rt = entry.runtime_data
    try:
        result = await hass.async_add_executor_job(
            rt.client.get_person_list_all, rt.person_group_id
        )
        connection.send_result(msg["id"], result)
    except Exception as ex:
        _LOGGER.error("列出人员失败: %s", ex)
        connection.send_error(msg["id"], "api_error", str(ex))


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/create_person",
    "data": {"person_id": str, "person_name": str, "camera_entity_id": str},
})
@websocket_api.async_response
async def ws_create_person(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: Dict[str, Any]
) -> None:
    entry = _first_entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_found", "未找到配置")
        return
    rt = entry.runtime_data
    d = msg["data"]
    try:
        image = await async_get_image(hass, d["camera_entity_id"])
        image_base64 = base64.b64encode(image.content).decode("utf-8")
        result = await hass.async_add_executor_job(
            rt.client.create_person,
            d["person_id"], d["person_name"], rt.person_group_id,
            None, None, None, image_base64,
        )
        connection.send_result(msg["id"], result)
    except Exception as ex:
        _LOGGER.error("创建人员失败: %s", ex)
        connection.send_error(msg["id"], "api_error", str(ex))


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/delete_person",
    "data": {"person_id": str},
})
@websocket_api.async_response
async def ws_delete_person(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: Dict[str, Any]
) -> None:
    entry = _first_entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_found", "未找到配置")
        return
    rt = entry.runtime_data
    try:
        result = await hass.async_add_executor_job(
            rt.client.delete_person, msg["data"]["person_id"]
        )
        connection.send_result(msg["id"], result)
    except Exception as ex:
        _LOGGER.error("删除人员失败: %s", ex)
        connection.send_error(msg["id"], "api_error", str(ex))
