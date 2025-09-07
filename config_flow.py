"""腾讯云人脸识别插件配置流程"""

import logging
import re
from typing import Dict, Any, Optional, List

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_NAME
from homeassistant.helpers.selector import selector

from .const import (
    DOMAIN,
    CONF_SECRET_ID,
    CONF_SECRET_KEY,
    CONF_REGION,
    CONF_PERSON_GROUP_ID,
    DEFAULT_REGION,
    ERROR_INVALID_CONFIG,
    ERROR_API_ERROR,
)
from .errors import (
    validate_config,
    InvalidConfigError,
    AuthenticationError,
    NetworkError,
    RateLimitError,
    log_and_raise_error
)
from .tencent_cloud_client import TencentCloudClient

_LOGGER = logging.getLogger(__name__)

# 腾讯云区域列表
AVAILABLE_REGIONS = [
    "ap-beijing", "ap-shanghai", "ap-guangzhou", "ap-chengdu", "ap-chongqing", "ap-nanjing", "ap-hangzhou"
]

# Secret ID 格式验证
SECRET_ID_REGEX = re.compile(r'^AKID[a-zA-Z0-9\-]{36,}$')

# Secret Key 格式验证
SECRET_KEY_REGEX = re.compile(r'^[a-zA-Z0-9+/]{20,}$')

# 人员库ID格式验证
PERSON_GROUP_ID_REGEX = re.compile(r'^[a-zA-Z0-9\-_]{1,64}$')


class TencentFaceRecognitionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """腾讯云人脸识别配置流程"""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """初始化配置流程"""
        self._client = None
        self._config_info = {}

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        """处理用户配置步骤"""
        errors = {}

        if user_input is not None:
            # 验证配置
            try:
                # 验证输入格式
                self._validate_input_format(user_input, errors)
                
                if errors:
                    return self._show_user_form(errors)
                
                # 基本配置验证
                validate_config(user_input)
                
                # 尝试创建腾讯云客户端以验证凭据
                validation_result = await self._validate_tencent_cloud_credentials(user_input)
                
                if not validation_result["success"]:
                    errors = validation_result["errors"]
                    return self._show_user_form(errors)
                
                # 保存配置并创建配置项
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, "腾讯云人脸识别"),
                    data=user_input
                )
                
            except InvalidConfigError as ex:
                _LOGGER.error("配置验证失败: %s", ex)
                errors["base"] = str(ex)
            except Exception as ex:
                _LOGGER.error("配置验证失败: %s", ex, exc_info=True)
                errors["base"] = f"配置验证失败: {str(ex)}"

        # 显示配置表单
        return self._show_user_form(errors)

    def _show_user_form(self, errors: Dict[str, str]) -> dict:
        """显示用户配置表单"""
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_SECRET_ID): vol.All(str, vol.Length(min=1)),
                vol.Required(CONF_SECRET_KEY): vol.All(str, vol.Length(min=1)),
                vol.Optional(CONF_REGION, default=DEFAULT_REGION): selector({
                    "select": {
                        "options": [{"label": region, "value": region} for region in AVAILABLE_REGIONS],
                        "mode": "dropdown"
                    }
                }),
                vol.Optional(CONF_PERSON_GROUP_ID, default="Hass"): vol.All(
                    str,
                    vol.Length(min=1, max=64)
                ),
                vol.Optional(CONF_NAME, default="腾讯云人脸识别"): vol.All(str, vol.Length(min=1, max=50)),
            }),
            errors=errors,
            description_placeholders={
                "secret_id_example": "AKIDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "secret_key_example": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "person_group_id_example": "Hass",
                "region_example": "ap-shanghai"
            }
        )

    def _validate_input_format(self, user_input: Dict[str, Any], errors: Dict[str, str]) -> None:
        """验证输入格式"""
        # 验证Secret ID格式
        secret_id = user_input.get(CONF_SECRET_ID, "")
        if not SECRET_ID_REGEX.match(secret_id):
            errors[CONF_SECRET_ID] = "Secret ID格式不正确，应以AKID开头，后跟36个以上字符"
        
        # 验证Secret Key格式
        secret_key = user_input.get(CONF_SECRET_KEY, "")
        if not SECRET_KEY_REGEX.match(secret_key):
            errors[CONF_SECRET_KEY] = "Secret Key格式不正确，应为20个以上字符"
        
        # 验证区域
        region = user_input.get(CONF_REGION, DEFAULT_REGION)
        if region not in AVAILABLE_REGIONS:
            errors[CONF_REGION] = f"无效的区域，请从列表中选择有效的区域"
        
        # 验证人员库ID格式
        person_group_id = user_input.get(CONF_PERSON_GROUP_ID, "Hass")
        if not PERSON_GROUP_ID_REGEX.match(person_group_id):
            errors[CONF_PERSON_GROUP_ID] = "人员库ID只能包含字母、数字、连字符和下划线，长度1-64个字符"
        
        # 验证名称
        name = user_input.get(CONF_NAME, "腾讯云人脸识别")
        if len(name) > 50:
            errors[CONF_NAME] = "名称长度不能超过50个字符"

    async def _validate_tencent_cloud_credentials(self, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """验证腾讯云凭据"""
        try:
            _LOGGER.info("开始验证腾讯云凭据")
            
            # 创建腾讯云客户端
            self._client = TencentCloudClient(
                user_input[CONF_SECRET_ID],
                user_input[CONF_SECRET_KEY],
                user_input.get(CONF_REGION, DEFAULT_REGION)
            )
            
            _LOGGER.info("腾讯云客户端创建成功，凭据验证通过")
            
            return {"success": True}
            
        except AuthenticationError as ex:
            _LOGGER.error("腾讯云认证失败: %s", ex)
            return {
                "success": False,
                "errors": {
                    CONF_SECRET_ID: "认证失败，请检查Secret ID",
                    CONF_SECRET_KEY: "认证失败，请检查Secret Key",
                    "base": "腾讯云认证失败，请检查Secret ID和Secret Key是否正确"
                }
            }
        except NetworkError as ex:
            _LOGGER.error("腾讯云网络错误: %s", ex)
            return {
                "success": False,
                "errors": {
                    CONF_REGION: "网络错误，请检查区域设置和网络连接",
                    "base": "连接腾讯云失败，请检查网络连接和区域设置"
                }
            }
        except RateLimitError as ex:
            _LOGGER.error("腾讯云速率限制错误: %s", ex)
            return {
                "success": False,
                "errors": {
                    "base": "腾讯云API调用频率过高，请稍后再试"
                }
            }
        except Exception as ex:
            _LOGGER.error("腾讯云凭据验证失败: %s", ex, exc_info=True)
            return {
                "success": False,
                "errors": {
                    "base": f"腾讯云API验证失败: {str(ex)}"
                }
            }

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """获取选项流程"""
        return TencentFaceRecognitionOptionsFlow(config_entry)


class TencentFaceRecognitionOptionsFlow(config_entries.OptionsFlow):
    """腾讯云人脸识别选项流程"""

    def __init__(self, config_entry):
        """初始化选项流程"""
        # 存储需要的数据而不是整个 config_entry 实例
        self._entry_id = config_entry.entry_id
        self._title = config_entry.title
        self._data = dict(config_entry.data)
        self._options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):
        """管理选项流程"""
        if user_input is not None:
            action = user_input.get("action")
            
            if action == "config":
                return await self.async_step_config()
            elif action == "test_connection":
                return await self.async_step_test_connection()
            elif action == "reauth":
                return await self.async_step_reauth()
            
            return self.async_create_entry(title="", data=user_input)

        # 显示管理菜单
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("action"): selector({
                    "select": {
                        "options": [
                            {"label": "配置设置", "value": "config"},
                            {"label": "测试连接", "value": "test_connection"},
                            {"label": "重新认证", "value": "reauth"}
                        ]
                    }
                })
            }),
            description_placeholders={
                "description": "请选择要管理的项目"
            }
        )

    async def async_step_config(self, user_input=None):
        """配置设置步骤"""
        errors = {}
        
        if user_input is not None:
            # 验证区域
            region = user_input.get(CONF_REGION)
            if region not in AVAILABLE_REGIONS:
                errors[CONF_REGION] = f"无效的区域，请从列表中选择有效的区域"
            
            if not errors:
                # 验证新配置是否有效
                try:
                    # 创建临时客户端进行验证
                    temp_client = TencentCloudClient(
                        self._data.get(CONF_SECRET_ID),
                        self._data.get(CONF_SECRET_KEY),
                        region
                    )
                    
                    _LOGGER.info("配置验证成功")
                    
                    # 保存配置
                    return self.async_create_entry(title="", data=user_input)
                    
                except AuthenticationError as ex:
                    _LOGGER.error("腾讯云认证失败: %s", ex)
                    errors[CONF_REGION] = "认证失败，请检查区域设置"
                    errors["base"] = "腾讯云认证失败，请检查区域设置"
                except NetworkError as ex:
                    _LOGGER.error("腾讯云网络错误: %s", ex)
                    errors[CONF_REGION] = "网络错误，请检查区域设置"
                    errors["base"] = "连接腾讯云失败，请检查网络连接和区域设置"
                except Exception as ex:
                    _LOGGER.error("配置验证失败: %s", ex, exc_info=True)
                    errors["base"] = f"配置验证失败: {str(ex)}"

        options = {
            vol.Optional(
                CONF_REGION,
                default=self._options.get(CONF_REGION, self._data.get(CONF_REGION, DEFAULT_REGION))
            ): selector({
                "select": {
                    "options": [{"label": region, "value": region} for region in AVAILABLE_REGIONS],
                    "mode": "dropdown"
                }
            }),
            vol.Optional(
                CONF_PERSON_GROUP_ID,
                default=self._options.get(CONF_PERSON_GROUP_ID, self._data.get(CONF_PERSON_GROUP_ID, "Hass"))
            ): str,
        }

        return self.async_show_form(
            step_id="config",
            data_schema=vol.Schema(options),
            errors=errors,
        )
    
    async def async_step_test_connection(self, user_input=None):
        """测试连接步骤"""
        errors = {}
        connection_status = "未知"
        
        if user_input is None:
            # 尝试测试连接
            try:
                # 使用当前配置创建客户端
                client = TencentCloudClient(
                    self._data.get(CONF_SECRET_ID),
                    self._data.get(CONF_SECRET_KEY),
                    self._data.get(CONF_REGION, DEFAULT_REGION)
                )
                
                # 使用 GetGroupInfo 测试连接
                group_id = self._data.get(CONF_PERSON_GROUP_ID, "Hass")
                
                success = await self.hass.async_add_executor_job(
                    client._test_api_connection,
                    group_id
                )
                
                if not success:
                    raise Exception("连接测试失败，请检查人员库ID是否正确")
                
                connection_status = "连接成功"
                _LOGGER.info("连接测试成功")
                
            except AuthenticationError as ex:
                connection_status = f"认证失败: {str(ex)}"
                errors["base"] = "认证失败，请检查Secret ID和Secret Key"
                _LOGGER.error("连接测试认证失败: %s", ex)
            except NetworkError as ex:
                connection_status = f"网络错误: {str(ex)}"
                errors["base"] = "网络错误，请检查网络连接和区域设置"
                _LOGGER.error("连接测试网络失败: %s", ex)
            except Exception as ex:
                connection_status = f"测试失败: {str(ex)}"
                errors["base"] = f"连接测试失败: {str(ex)}"
                _LOGGER.error("连接测试失败: %s", ex, exc_info=True)
        
        return self.async_show_form(
            step_id="test_connection",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={
                "connection_status": connection_status
            }
        )
    
    async def async_step_reauth(self, user_input=None):
        """重新认证步骤"""
        errors = {}
        
        if user_input is not None:
            # 验证新凭据
            try:
                # 验证输入格式
                temp_errors = {}
                self._validate_input_format(user_input, temp_errors)
                
                if temp_errors:
                    errors = temp_errors
                    return self.async_show_form(
                        step_id="reauth",
                        data_schema=vol.Schema({
                            vol.Required(CONF_SECRET_ID, default=self._data.get(CONF_SECRET_ID, "")): str,
                            vol.Required(CONF_SECRET_KEY, default=self._data.get(CONF_SECRET_KEY, "")): str,
                        }),
                        errors=errors,
                    )
                
                # 创建腾讯云客户端验证新凭据
                new_client = TencentCloudClient(
                    user_input[CONF_SECRET_ID],
                    user_input[CONF_SECRET_KEY],
                    self._data.get(CONF_REGION, DEFAULT_REGION)
                )
                
                _LOGGER.info("重新认证成功")
                
                # 更新配置
                new_data = dict(self._data)
                new_data.update(user_input)
                
                # 重新创建配置项
                self.hass.config_entries.async_update_entry(
                    self.hass.config_entries.async_get_entry(self._entry_id),
                    data=new_data
                )
                
                return self.async_create_entry(title="", data={})
                
            except AuthenticationError as ex:
                _LOGGER.error("重新认证失败: %s", ex)
                errors["base"] = "认证失败，请检查Secret ID和Secret Key"
            except NetworkError as ex:
                _LOGGER.error("重新认证网络错误: %s", ex)
                errors["base"] = "网络错误，请检查网络连接和区域设置"
            except Exception as ex:
                _LOGGER.error("重新认证失败: %s", ex, exc_info=True)
                errors["base"] = f"重新认证失败: {str(ex)}"
        
        return self.async_show_form(
            step_id="reauth",
            data_schema=vol.Schema({
                vol.Required(CONF_SECRET_ID, default=self._data.get(CONF_SECRET_ID, "")): str,
                vol.Required(CONF_SECRET_KEY, default=self._data.get(CONF_SECRET_KEY, "")): str,
            }),
            errors=errors,
            description_placeholders={
                "current_secret_id": self._data.get(CONF_SECRET_ID, ""),
                "current_region": self._data.get(CONF_REGION, DEFAULT_REGION)
            }
        )
    
    def _validate_input_format(self, user_input: Dict[str, Any], errors: Dict[str, str]) -> None:
        """验证输入格式"""
        # 验证Secret ID格式
        secret_id = user_input.get(CONF_SECRET_ID, "")
        if not SECRET_ID_REGEX.match(secret_id):
            errors[CONF_SECRET_ID] = "Secret ID格式不正确，应以AKID开头，后跟36个以上字符"
        
        # 验证Secret Key格式
        secret_key = user_input.get(CONF_SECRET_KEY, "")
        if not SECRET_KEY_REGEX.match(secret_key):
            errors[CONF_SECRET_KEY] = "Secret Key格式不正确，应为20个以上字符"