"""人脸识别核心功能"""

import base64
import logging
from typing import Dict, Any, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    ATTR_IMAGE_URL,
    ATTR_IMAGE_PATH,
    ATTR_CAMERA_ENTITY_ID,
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
    ATTR_GROUP_ID,
)
from .tencent_cloud_client import TencentCloudClient

_LOGGER = logging.getLogger(__name__)


class FaceRecognition:
    """人脸识别核心功能"""

    def __init__(self, hass: HomeAssistant, client: TencentCloudClient):
        """初始化人脸识别功能"""
        self.hass = hass
        self.client = client

    async def _get_image_base64_from_source(
        self,
        image_url: str = None,
        image_path: str = None,
        image_file: str = None,
        camera_entity_id: str = None,
    ) -> str:
        """从各种来源获取图片 base64 编码"""
        if camera_entity_id:
            return await self._get_camera_image_base64(camera_entity_id)
        if image_url or image_path or image_file:
            return await self.hass.async_add_executor_job(
                self.client._get_image_base64, image_url, image_path, image_file
            )
        raise ValueError("必须提供image_url、image_path、image_file或camera_entity_id")

    async def _get_camera_image_base64(self, camera_entity_id: str) -> str:
        """从摄像头实体获取图片 base64"""
        try:
            from homeassistant.components.camera import async_get_image
            image = await async_get_image(self.hass, camera_entity_id)
            return base64.b64encode(image.content).decode("utf-8")
        except ImportError:
            raise HomeAssistantError("摄像头组件不可用，无法获取图片")
        except Exception as ex:
            raise HomeAssistantError(f"获取摄像头图片失败: {ex}")

    def _validate_image_params(
        self,
        image_url: str = None,
        image_path: str = None,
        image_file: str = None,
        camera_entity_id: str = None,
    ) -> None:
        """验证图片参数"""
        if not any([image_url, image_path, image_file, camera_entity_id]):
            raise ValueError("必须提供image_url、image_path、image_file或camera_entity_id")

    async def async_search_faces(
        self,
        image_url: str = None,
        image_path: str = None,
        image_file: str = None,
        camera_entity_id: str = None,
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
            self._validate_image_params(image_url, image_path, image_file, camera_entity_id)

            image_base64 = await self._get_image_base64_from_source(
                image_url, image_path, image_file, camera_entity_id
            )

            result = await self.hass.async_add_executor_job(
                self.client.search_faces,
                None, None, None, image_base64,
                group_ids,
                max_face_num,
                min_face_size,
                max_user_num,
                quality_control,
                need_rotate_check,
                face_match_threshold
            )

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
        except HomeAssistantError:
            raise
        except Exception as ex:
            _LOGGER.error("人脸搜索失败: %s", ex)
            return {
                "success": False,
                "faces": [],
                "error": str(ex),
                "error_code": "unknown_error",
                "error_message": str(ex)
            }

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

    async def async_get_face_attributes(
        self,
        image_url: str = None,
        image_path: str = None,
        image_file: str = None,
        camera_entity_id: str = None,
        max_face_num: int = 1,
        need_rotate_check: int = 1
    ) -> Dict[str, Any]:
        """获取人脸属性"""
        try:
            self._validate_image_params(image_url, image_path, image_file, camera_entity_id)

            image_base64 = await self._get_image_base64_from_source(
                image_url, image_path, image_file, camera_entity_id
            )

            result = await self.hass.async_add_executor_job(
                self.client.get_face_attributes,
                None, None, None, image_base64,
                max_face_num,
                need_rotate_check
            )

            if result.get("success", False):
                return {
                    "success": True,
                    "faces": result.get("faces", []),
                    "error": None,
                    "error_code": None,
                    "error_message": None
                }
            else:
                return {
                    "success": False,
                    "faces": [],
                    "error": result.get("error"),
                    "error_code": result.get("error_code"),
                    "error_message": result.get("error_message")
                }

        except HomeAssistantError:
            raise
        except Exception as ex:
            _LOGGER.error("获取人脸属性失败: %s", ex)
            return {
                "success": False,
                "faces": [],
                "error": str(ex),
                "error_code": "unknown_error",
                "error_message": str(ex)
            }

    async def async_detect_faces(
        self,
        image_url: str = None,
        image_path: str = None,
        image_file: str = None,
        camera_entity_id: str = None,
        max_face_num: int = 1,
        min_face_size: int = 34,
        need_rotate_check: int = 1
    ) -> Dict[str, Any]:
        """检测人脸"""
        try:
            self._validate_image_params(image_url, image_path, image_file, camera_entity_id)

            image_base64 = await self._get_image_base64_from_source(
                image_url, image_path, image_file, camera_entity_id
            )

            result = await self.hass.async_add_executor_job(
                self.client.detect_faces,
                None, None, None, image_base64,
                max_face_num,
                min_face_size,
                need_rotate_check
            )

            if result.get("success", False):
                return {
                    "success": True,
                    "faces": result.get("faces", []),
                    "error": None,
                    "error_code": None,
                    "error_message": None
                }
            else:
                return {
                    "success": False,
                    "faces": [],
                    "error": result.get("error"),
                    "error_code": result.get("error_code"),
                    "error_message": result.get("error_message")
                }

        except HomeAssistantError:
            raise
        except Exception as ex:
            _LOGGER.error("人脸检测失败: %s", ex)
            return {
                "success": False,
                "faces": [],
                "error": str(ex),
                "error_code": "unknown_error",
                "error_message": str(ex)
            }

    async def async_create_person(
        self,
        person_id: str,
        person_name: str,
        group_id: str,
        image_url: str = None,
        image_path: str = None,
        image_file: str = None,
        camera_entity_id: str = None,
        gender: int = None,
        person_tag: str = None,
        quality_control: int = 1,
        need_rotate_check: int = 1,
    ) -> Dict[str, Any]:
        """创建人员"""
        try:
            image_base64 = None
            if any([image_url, image_path, image_file, camera_entity_id]):
                image_base64 = await self._get_image_base64_from_source(
                    image_url, image_path, image_file, camera_entity_id
                )

            result = await self.hass.async_add_executor_job(
                self.client.create_person,
                person_id, person_name, group_id,
                None, None, None, image_base64,
                gender, person_tag,
                quality_control, need_rotate_check,
            )
            return result
        except HomeAssistantError:
            raise
        except Exception as ex:
            _LOGGER.error("创建人员失败: %s", ex)
            return {
                "success": False,
                "error": str(ex),
                "error_code": "unknown_error",
                "error_message": str(ex)
            }

    async def async_delete_person(self, person_id: str) -> Dict[str, Any]:
        """删除人员"""
        try:
            result = await self.hass.async_add_executor_job(
                self.client.delete_person, person_id
            )
            return result
        except Exception as ex:
            _LOGGER.error("删除人员失败: %s", ex)
            return {
                "success": False,
                "error": str(ex),
                "error_code": "unknown_error",
                "error_message": str(ex)
            }

    async def async_create_face(
        self,
        person_id: str,
        image_url: str = None,
        image_path: str = None,
        image_file: str = None,
        camera_entity_id: str = None,
        quality_control: int = 1,
        need_rotate_check: int = 1,
    ) -> Dict[str, Any]:
        """为人员注册人脸"""
        try:
            image_base64 = await self._get_image_base64_from_source(
                image_url, image_path, image_file, camera_entity_id
            )

            result = await self.hass.async_add_executor_job(
                self.client.create_face,
                person_id,
                None, None, None, image_base64,
                quality_control, need_rotate_check,
            )
            return result
        except HomeAssistantError:
            raise
        except Exception as ex:
            _LOGGER.error("注册人脸失败: %s", ex)
            return {
                "success": False,
                "error": str(ex),
                "error_code": "unknown_error",
                "error_message": str(ex)
            }

    async def async_delete_face(self, person_id: str, face_id: str) -> Dict[str, Any]:
        """删除人脸"""
        try:
            result = await self.hass.async_add_executor_job(
                self.client.delete_face, person_id, face_id
            )
            return result
        except Exception as ex:
            _LOGGER.error("删除人脸失败: %s", ex)
            return {
                "success": False,
                "error": str(ex),
                "error_code": "unknown_error",
                "error_message": str(ex)
            }
