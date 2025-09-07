"""人脸识别核心功能"""

import logging
import json
from typing import Dict, Any, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    ATTR_IMAGE_URL,
    ATTR_IMAGE_PATH,
    ATTR_MAX_FACE_NUM,
    ATTR_MIN_FACE_SIZE,
    ATTR_MAX_USER_NUM,
    ATTR_QUALITY_CONTROL,
    ATTR_NEED_ROTATE_CHECK,
    ATTR_FACE_MATCH_THRESHOLD,
    ERROR_IMAGE_NOT_FOUND,
    ERROR_FACE_NOT_DETECTED,
)
from .tencent_cloud_client import TencentCloudClient

_LOGGER = logging.getLogger(__name__)


class FaceRecognition:
    """人脸识别核心功能"""

    def __init__(self, hass: HomeAssistant, client: TencentCloudClient):
        """初始化人脸识别功能"""
        self.hass = hass
        self.client = client

    async def async_search_faces(
        self,
        image_url: str = None,
        image_path: str = None,
        image_file: str = None,
        group_ids: List[str] = None,
        max_face_num: int = 1,
        min_face_size: int = 34,
        max_user_num: int = 5,
        quality_control: int = 1,
        need_rotate_check: int = 1,
        face_match_threshold: float = 60.0
    ) -> Dict[str, Any]:
        """搜索人脸"""
        try:
            # 验证参数
            self._validate_image_params(image_url, image_path, image_file)

            # 调用腾讯云API搜索人脸
            result = await self.hass.async_add_executor_job(
                self.client.search_faces,
                image_url,
                image_path,
                image_file,
                group_ids,
                max_face_num,
                min_face_size,
                max_user_num,
                quality_control,
                need_rotate_check,
                face_match_threshold
            )

            # 处理结果
            if result.get("success", False):
                processed_faces = self._process_search_results(result.get("faces", []))
                return {
                    "success": True,
                    "faces": processed_faces,
                    "error": None,
                    "error_code": None,
                    "error_message": None
                }
            else:
                # 返回错误信息
                return {
                    "success": False,
                    "faces": [],
                    "error": result.get("error"),
                    "error_code": result.get("error_code"),
                    "error_message": result.get("error_message")
                }

        except ValueError as ex:
            _LOGGER.error("人脸搜索参数错误: %s", ex)
            return {
                "success": False,
                "faces": [],
                "error": str(ex),
                "error_code": "invalid_parameter",
                "error_message": str(ex)
            }
        except Exception as ex:
            _LOGGER.error("人脸搜索失败: %s", ex)
            return {
                "success": False,
                "faces": [],
                "error": str(ex),
                "error_code": "unknown_error",
                "error_message": str(ex)
            }

    def _validate_image_params(self, image_url: str, image_path: str, image_file: str) -> None:
        """验证图片参数"""
        if not image_url and not image_path and not image_file:
            raise ValueError("必须提供image_url、image_path或image_file")
    
    def _process_search_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """处理人脸搜索结果"""
        processed_results = []
        for result in results:
            processed_result = {
                "face_id": result.get("face_id"),
                "candidates": []
            }

            for candidate in result.get("candidates", []):
                processed_candidate = {
                    "person_id": candidate.get("person_id"),
                    "person_name": candidate.get("person_name"),
                    "score": candidate.get("score"),
                    "person_tag": candidate.get("person_tag")
                }
                processed_result["candidates"].append(processed_candidate)

            processed_results.append(processed_result)

        return processed_results
    
    def _process_detect_results(self, results: List[Dict[str, Any]], include_attributes: bool = False) -> List[Dict[str, Any]]:
        """处理人脸检测结果"""
        processed_results = []
        for result in results:
            face_result = {
                "face_id": result.get("face_id", ""),
                "x": result.get("x", 0),
                "y": result.get("y", 0),
                "width": result.get("width", 0),
                "height": result.get("height", 0),
                "face_rect": result.get("face_rect")
            }
            
            # 如果需要包含属性信息
            if include_attributes:
                face_result.update({
                    "gender": result.get("gender"),
                    "age": result.get("age"),
                    "expression": result.get("expression"),
                    "beauty": result.get("beauty")
                })
            
            processed_results.append(face_result)

        return processed_results
    
    def _handle_api_error(self, operation: str, ex: Exception) -> None:
        """处理API错误"""
        _LOGGER.error("%s失败: %s", operation, ex)
        if isinstance(ex, ValueError):
            raise HomeAssistantError(str(ex))
        else:
            raise HomeAssistantError(f"{operation}失败: {str(ex)}")
    
    def _get_config_entry(self):
        """获取配置项"""
        from homeassistant.config_entries import ConfigEntry
        from . import DOMAIN

        for entry in self.hass.config_entries.async_entries(DOMAIN):
            return entry
        return None

    async def async_get_face_attributes(
        self,
        image_url: str = None,
        image_path: str = None,
        image_file: str = None,
        max_face_num: int = 1,
        need_rotate_check: int = 1
    ) -> Dict[str, Any]:
        """获取人脸属性"""
        try:
            # 验证参数
            self._validate_image_params(image_url, image_path, image_file)

            # 调用腾讯云API获取人脸属性
            result = await self.hass.async_add_executor_job(
                self.client.get_face_attributes,
                image_url,
                image_path,
                image_file,
                max_face_num,
                need_rotate_check
            )

            # 处理结果
            if result.get("success", False):
                return {
                    "success": True,
                    "faces": result.get("faces", []),
                    "error": None,
                    "error_code": None,
                    "error_message": None
                }
            else:
                # 返回错误信息
                return {
                    "success": False,
                    "faces": [],
                    "error": result.get("error"),
                    "error_code": result.get("error_code"),
                    "error_message": result.get("error_message")
                }

        except Exception as ex:
            _LOGGER.error("获取人脸属性失败: %s", ex)
            return {
                "success": False,
                "faces": [],
                "error": str(ex),
                "error_code": "unknown_error",
                "error_message": str(ex)
            }

    # 移除 _get_face_attributes_sync 方法，因为现在直接使用客户端的 get_face_attributes 方法

    async def async_detect_faces(
        self,
        image_url: str = None,
        image_path: str = None,
        image_file: str = None,
        max_face_num: int = 1,
        min_face_size: int = 34,
        need_rotate_check: int = 1
    ) -> Dict[str, Any]:
        """检测人脸"""
        try:
            # 验证参数
            self._validate_image_params(image_url, image_path, image_file)

            # 调用腾讯云API检测人脸
            result = await self.hass.async_add_executor_job(
                self.client.detect_faces,
                image_url,
                image_path,
                image_file,
                max_face_num,
                min_face_size,
                need_rotate_check
            )

            # 处理结果
            if result.get("success", False):
                return {
                    "success": True,
                    "faces": result.get("faces", []),
                    "error": None,
                    "error_code": None,
                    "error_message": None
                }
            else:
                # 返回错误信息
                return {
                    "success": False,
                    "faces": [],
                    "error": result.get("error"),
                    "error_code": result.get("error_code"),
                    "error_message": result.get("error_message")
                }

        except Exception as ex:
            _LOGGER.error("人脸检测失败: %s", ex)
            return {
                "success": False,
                "faces": [],
                "error": str(ex),
                "error_code": "unknown_error",
                "error_message": str(ex)
            }

    # 移除 _detect_faces_sync 方法，因为现在直接使用客户端的 detect_faces 方法