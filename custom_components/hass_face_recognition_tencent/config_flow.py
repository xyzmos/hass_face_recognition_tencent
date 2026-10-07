"""腾讯云人脸识别集成配置流程"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.camera import async_get_image
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_PERSON_GROUP_ID,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_SECRET_ID,
    CONF_SECRET_KEY,
    DEFAULT_PERSON_GROUP_ID,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    get_entry_value,
)
from .errors import AuthenticationError, NetworkError, RateLimitError
from .tencent_cloud_client import TencentCloudClient

_LOGGER = logging.getLogger(__name__)

AVAILABLE_REGIONS = [
    "ap-beijing", "ap-shanghai", "ap-guangzhou", "ap-chengdu",
    "ap-chongqing", "ap-nanjing",
]

SECRET_ID_REGEX = re.compile(r"^AKID[a-zA-Z0-9\-]{30,}$")
SECRET_KEY_REGEX = re.compile(r"^[a-zA-Z0-9+/]{16,}$")
PERSON_GROUP_ID_REGEX = re.compile(r"^[a-zA-Z0-9\-_]{1,64}$")
PERSON_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.:]{1,64}$")

DEFAULT_TITLE = "腾讯云人脸识别"


def _region_selector() -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[{"label": r, "value": r} for r in AVAILABLE_REGIONS],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _validate_common(user_input: Dict[str, Any], errors: Dict[str, str]) -> None:
    """校验 secret_id/secret_key/region/person_group_id 输入格式。"""
    if not SECRET_ID_REGEX.match(user_input.get(CONF_SECRET_ID, "")):
        errors[CONF_SECRET_ID] = "invalid_secret_id"
    if not SECRET_KEY_REGEX.match(user_input.get(CONF_SECRET_KEY, "")):
        errors[CONF_SECRET_KEY] = "invalid_secret_key"
    if user_input.get(CONF_REGION, DEFAULT_REGION) not in AVAILABLE_REGIONS:
        errors[CONF_REGION] = "invalid_region"
    pgid = user_input.get(CONF_PERSON_GROUP_ID, DEFAULT_PERSON_GROUP_ID)
    if not PERSON_GROUP_ID_REGEX.match(pgid):
        errors[CONF_PERSON_GROUP_ID] = "invalid_person_group_id"


async def _verify(hass, secret_id: str, secret_key: str, region: str) -> Optional[str]:
    """验证凭据，返回错误 key 或 None。"""
    client = None
    try:
        client = TencentCloudClient(secret_id, secret_key, region)
        await hass.async_add_executor_job(client.verify_credentials)
        return None
    except AuthenticationError as ex:
        _LOGGER.error("腾讯云认证失败: %s", ex)
        return "invalid_auth"
    except NetworkError as ex:
        _LOGGER.error("腾讯云网络错误: %s", ex)
        return "cannot_connect"
    except RateLimitError as ex:
        _LOGGER.error("腾讯云限流: %s", ex)
        return "rate_limited"
    except Exception as ex:  # noqa: BLE001
        _LOGGER.error("凭据验证失败: %s", ex)
        return "unknown"
    finally:
        if client is not None:
            await hass.async_add_executor_job(client.close)


class TencentFaceRecognitionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """配置流程。"""

    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> config_entries.ConfigFlowResult:
        errors: Dict[str, str] = {}
        if user_input is not None:
            _validate_common(user_input, errors)
            if not errors:
                await self.async_set_unique_id(
                    f"{DOMAIN}_{user_input[CONF_SECRET_ID]}"
                )
                self._abort_if_unique_id_configured()
                err = await _verify(
                    self.hass,
                    user_input[CONF_SECRET_ID],
                    user_input[CONF_SECRET_KEY],
                    user_input.get(CONF_REGION, DEFAULT_REGION),
                )
                if err is None:
                    return self.async_create_entry(
                        title=user_input.get(CONF_NAME, DEFAULT_TITLE),
                        data={
                            CONF_SECRET_ID: user_input[CONF_SECRET_ID],
                            CONF_SECRET_KEY: user_input[CONF_SECRET_KEY],
                            CONF_REGION: user_input.get(CONF_REGION, DEFAULT_REGION),
                            CONF_PERSON_GROUP_ID: user_input.get(
                                CONF_PERSON_GROUP_ID, DEFAULT_PERSON_GROUP_ID
                            ),
                            CONF_NAME: user_input.get(CONF_NAME, DEFAULT_TITLE),
                        },
                        options={
                            CONF_SCAN_INTERVAL: user_input.get(
                                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                            ),
                        },
                    )
                errors["base"] = err

        return self.async_show_form(
            step_id="user",
            data_schema=self._user_schema(user_input),
            errors=errors,
        )

    def _user_schema(self, user_input: Optional[Dict[str, Any]]) -> vol.Schema:
        d = user_input or {}
        return vol.Schema({
            vol.Required(CONF_SECRET_ID, default=d.get(CONF_SECRET_ID, "")): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Required(CONF_SECRET_KEY, default=d.get(CONF_SECRET_KEY, "")): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Optional(CONF_REGION, default=d.get(CONF_REGION, DEFAULT_REGION)):
                _region_selector(),
            vol.Optional(CONF_PERSON_GROUP_ID, default=d.get(CONF_PERSON_GROUP_ID, DEFAULT_PERSON_GROUP_ID)): str,
            vol.Optional(CONF_NAME, default=d.get(CONF_NAME, DEFAULT_TITLE)): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=d.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)):
                NumberSelector(NumberSelectorConfig(
                    min=30, max=86400, step=10, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="秒",
                )),
        })

    # --- Reauth -----------------------------------------------------------

    async def async_step_reauth(self, entry_data: Dict[str, Any]) -> config_entries.ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> config_entries.ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: Dict[str, str] = {}
        if user_input is not None:
            _validate_common({**entry.data, **user_input}, errors)
            if not errors:
                err = await _verify(
                    self.hass,
                    user_input[CONF_SECRET_ID],
                    user_input[CONF_SECRET_KEY],
                    get_entry_value(entry, CONF_REGION, DEFAULT_REGION),
                )
                if err is None:
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={
                            CONF_SECRET_ID: user_input[CONF_SECRET_ID],
                            CONF_SECRET_KEY: user_input[CONF_SECRET_KEY],
                        },
                    )
                errors["base"] = err

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({
                vol.Required(CONF_SECRET_ID, default=entry.data.get(CONF_SECRET_ID, "")): str,
                vol.Required(CONF_SECRET_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }),
            errors=errors,
            description_placeholders={
                "secret_id_hint": (entry.data.get(CONF_SECRET_ID, "")[:8] or "") + "***",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return TencentFaceRecognitionOptionsFlow()


class TencentFaceRecognitionOptionsFlow(config_entries.OptionsFlow):
    """选项流程。"""

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> config_entries.ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["settings", "test_connection", "manage"],
        )

    # --- 基础设置 ---------------------------------------------------------

    async def async_step_settings(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> config_entries.ConfigFlowResult:
        entry = self.config_entry
        errors: Dict[str, str] = {}
        if user_input is not None:
            pgid = user_input.get(CONF_PERSON_GROUP_ID, "")
            if pgid and not PERSON_GROUP_ID_REGEX.match(pgid):
                errors[CONF_PERSON_GROUP_ID] = "invalid_person_group_id"
            if not errors:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_REGION: user_input[CONF_REGION],
                        CONF_PERSON_GROUP_ID: pgid or get_entry_value(
                            entry, CONF_PERSON_GROUP_ID, DEFAULT_PERSON_GROUP_ID
                        ),
                        CONF_SCAN_INTERVAL: int(
                            user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                        ),
                    },
                )

        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_REGION,
                    default=get_entry_value(entry, CONF_REGION, DEFAULT_REGION),
                ): _region_selector(),
                vol.Optional(
                    CONF_PERSON_GROUP_ID,
                    default=get_entry_value(entry, CONF_PERSON_GROUP_ID, DEFAULT_PERSON_GROUP_ID),
                ): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=int(get_entry_value(entry, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
                ): NumberSelector(NumberSelectorConfig(
                    min=30, max=86400, step=10, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="秒",
                )),
            }),
            errors=errors,
        )

    # --- 测试连接 ---------------------------------------------------------

    async def async_step_test_connection(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return await self.async_step_init()
        entry = self.config_entry
        errors: Dict[str, str] = {}
        status = "成功"
        err = await _verify(
            self.hass,
            entry.data.get(CONF_SECRET_ID, ""),
            entry.data.get(CONF_SECRET_KEY, ""),
            get_entry_value(entry, CONF_REGION, DEFAULT_REGION),
        )
        if err is not None:
            status = "失败"
            errors["base"] = err
        return self.async_show_form(
            step_id="test_connection",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"connection_status": status},
        )

    # --- 人员管理 ---------------------------------------------------------

    async def async_step_manage(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> config_entries.ConfigFlowResult:
        entry = self.config_entry
        errors: Dict[str, str] = {}
        client = None
        try:
            client = TencentCloudClient(
                entry.data.get(CONF_SECRET_ID, ""),
                entry.data.get(CONF_SECRET_KEY, ""),
                get_entry_value(entry, CONF_REGION, DEFAULT_REGION),
            )
            group_id = get_entry_value(entry, CONF_PERSON_GROUP_ID, DEFAULT_PERSON_GROUP_ID)
            result = await self.hass.async_add_executor_job(
                client.get_person_list_all, group_id
            )
            persons = result.get("persons", []) if result.get("success") else []
            if not result.get("success"):
                errors["base"] = "cannot_connect"

            if user_input is not None:
                action = user_input.get("person_action")
                if action == "create":
                    return await self.async_step_create_person()
                if action == "delete":
                    selected = user_input.get("selected_person")
                    if selected:
                        await self.hass.async_add_executor_job(client.delete_person, selected)
                        _LOGGER.info("人员已删除: %s", selected)
                        return await self.async_step_manage()
                    errors["selected_person"] = "select_person_required"

            person_options = [
                {"label": f"{p.get('person_name', '未知')} ({p.get('person_id', '')})",
                 "value": p.get("person_id", "")}
                for p in persons
            ]

            schema: Dict[Any, Any] = {
                vol.Required("person_action"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"label": "刷新列表", "value": "refresh"},
                            {"label": "创建人员", "value": "create"},
                            {"label": "删除选中人员", "value": "delete"},
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
            if person_options:
                schema[vol.Optional("selected_person")] = SelectSelector(
                    SelectSelectorConfig(options=person_options, mode=SelectSelectorMode.DROPDOWN)
                )

            return self.async_show_form(
                step_id="manage",
                data_schema=vol.Schema(schema),
                errors=errors,
                description_placeholders={
                    "person_count": str(len(persons)),
                    "group_id": group_id,
                },
            )
        except Exception as ex:  # noqa: BLE001
            _LOGGER.error("人员管理加载失败: %s", ex)
            return self.async_show_form(
                step_id="manage",
                data_schema=vol.Schema({}),
                errors={"base": "unknown"},
            )
        finally:
            if client is not None:
                await self.hass.async_add_executor_job(client.close)

    async def async_step_create_person(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> config_entries.ConfigFlowResult:
        entry = self.config_entry
        errors: Dict[str, str] = {}
        if user_input is not None:
            pid = user_input["person_id"]
            if not PERSON_ID_REGEX.match(pid):
                errors["person_id"] = "invalid_person_id"
            if not errors:
                client = None
                try:
                    client = TencentCloudClient(
                        entry.data.get(CONF_SECRET_ID, ""),
                        entry.data.get(CONF_SECRET_KEY, ""),
                        get_entry_value(entry, CONF_REGION, DEFAULT_REGION),
                    )
                    image = await async_get_image(self.hass, user_input["camera_entity"])
                    image_base64 = base64.b64encode(image.content).decode("utf-8")
                    result = await self.hass.async_add_executor_job(
                        client.create_person,
                        pid,
                        user_input["person_name"],
                        get_entry_value(entry, CONF_PERSON_GROUP_ID, DEFAULT_PERSON_GROUP_ID),
                        None, None, None, image_base64,
                    )
                    if result.get("success"):
                        _LOGGER.info("人员创建成功: %s", pid)
                        return await self.async_step_manage()
                    errors["base"] = "create_failed"
                except Exception as ex:  # noqa: BLE001
                    _LOGGER.error("创建人员失败: %s", ex)
                    errors["base"] = "create_failed"
                finally:
                    if client is not None:
                        await self.hass.async_add_executor_job(client.close)

        return self.async_show_form(
            step_id="create_person",
            data_schema=vol.Schema({
                vol.Required("person_id"): str,
                vol.Required("person_name"): str,
                vol.Required("camera_entity"): EntitySelector(
                    EntitySelectorConfig(domain="camera")
                ),
            }),
            errors=errors,
        )
