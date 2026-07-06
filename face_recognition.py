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
        self.hass = hass
        self.client = client

    async def _get_image_base64_from_source(
        self,
        image_url: Optional[str] = None,
        image_path: Optional[str] = None,
        image_file: Optional[str] = None,
        camera_entity_id: Optional[str] = None,
    ) -> str:
        if camera_entity_id:
            return await self._get_camera_image_base64(camera_entity_id)
        if image_url or image_path or image_file:
            return await self.hass.async_add_executor_job(
                self.client._get_image_base64,
                image_url,
                image_path,
                image_file,
            )
        raise ValueError("必须提供image_url、image_path、image_file或camera_entity_id")
    async def _get_camera_image_base64(self, camera_entity_id: str) -> str:
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
        image_url: Optional[str] = None,
        image_path: Optional[str] = None,
        image_file: Optional[str] = None,
        camera_entity_id: Optional[str] = None,
    ) -> None:
        if not any([image_url, image_path, image_file, camera_entity_id]):
            raise ValueError("必须提供image_url、image_path、image_file或camera_entity_id")

    async def _safe_api_call(
        self,
        operation_name: str,
        client_method,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            result = await self.hass.async_add_executor_job(
                lambda: client_method(**kwargs)
            )
            return result
        except HomeAssistantError:
            raise
        except ValueError as ex:
            _LOGGER.error("%s参数错误: %s", operation_name, ex)
            return {
                "success": False,
                "faces": [],
                "error": str(ex),
                "error_code": "invalid_parameter",
                "error_message": str(ex),
            }
        except Exception as ex:
            _LOGGER.error("%s失败: %s", operation_name, ex)
            return {
                "success": False,
                "faces": [],
                "error": str(ex),
                "error_code": "unknown_error",
                "error_message": str(ex),
            }

    async def async_search_faces(
        self,
        image_url: Optional[str] = None,
        image_path: Optional[str] = None,
        image_file: Optional[str] = None,
        camera_entity_id: Optional[str] = None,
        group_ids: Optional[List[str]] = None,
        max_face_num: int = 1,
        min_face_size: int = 34,
        max_user_num: int = 5,
        quality_control: int = 1,
        need_rotate_check: int = 1,
        face_match_threshold: float = 60.0,
    ) -> Dict[str, Any]:
        self._validate_image_params(image_url, image_path, image_file, camera_entity_id)

        if not group_ids:
            raise ValueError("必须提供至少一个人员库ID (group_ids)")

        image_base64 = await self._get_image_base64_from_source(
            image_url=image_url,
            image_path=image_path,
            image_file=image_file,
            camera_entity_id=camera_entity_id,
        )

        result = await self._safe_api_call(
            "人脸搜索",
            self.client.search_faces,
            image_base64=image_base64,
            group_ids=group_ids,
            max_face_num=max_face_num,
            min_face_size=min_face_size,
            max_user_num=max_user_num,
            quality_control=quality_control,
            need_rotate_check=need_rotate_check,
            face_match_threshold=face_match_threshold,
        )

        if result.get("success", False):
            result["faces"] = self._process_search_results(result.get("faces", []))

        return result

    def _process_search_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """规范化搜索结果字段（保留客户端返回的全部信息）。"""
        processed_results = []
        for result in results:
            processed_result = {
                "face_id": result.get("face_id"),
                "face_rect": result.get("face_rect"),
                "candidates": [],
            }

            for candidate in result.get("candidates", []):
                processed_candidate = {
                    "person_id": candidate.get("person_id"),
                    "person_name": candidate.get("person_name"),
                    "score": candidate.get("score"),
                    "face_id": candidate.get("face_id"),
                    "gender": candidate.get("gender"),
                    "person_group_infos": candidate.get("person_group_infos", []),
                }
                processed_result["candidates"].append(processed_candidate)

            processed_results.append(processed_result)

        return processed_results

    async def async_get_face_attributes(
        self,
        image_url: Optional[str] = None,
        image_path: Optional[str] = None,
        image_file: Optional[str] = None,
        camera_entity_id: Optional[str] = None,
        max_face_num: int = 1,
        need_rotate_check: int = 1,
    ) -> Dict[str, Any]:
        self._validate_image_params(image_url, image_path, image_file, camera_entity_id)

        image_base64 = await self._get_image_base64_from_source(
            image_url=image_url,
            image_path=image_path,
            image_file=image_file,
            camera_entity_id=camera_entity_id,
        )

        return await self._safe_api_call(
            "获取人脸属性",
            self.client.get_face_attributes,
            image_base64=image_base64,
            max_face_num=max_face_num,
            need_rotate_check=need_rotate_check,
        )

    async def async_detect_faces(
        self,
        image_url: Optional[str] = None,
        image_path: Optional[str] = None,
        image_file: Optional[str] = None,
        camera_entity_id: Optional[str] = None,
        max_face_num: int = 1,
        min_face_size: int = 34,
        need_rotate_check: int = 1,
    ) -> Dict[str, Any]:
        self._validate_image_params(image_url, image_path, image_file, camera_entity_id)

        image_base64 = await self._get_image_base64_from_source(
            image_url=image_url,
            image_path=image_path,
            image_file=image_file,
            camera_entity_id=camera_entity_id,
        )

        return await self._safe_api_call(
            "人脸检测",
            self.client.detect_faces,
            image_base64=image_base64,
            max_face_num=max_face_num,
            min_face_size=min_face_size,
            need_rotate_check=need_rotate_check,
        )

    async def async_create_person(
        self,
        person_id: str,
        person_name: str,
        group_id: str,
        image_url: Optional[str] = None,
        image_path: Optional[str] = None,
        image_file: Optional[str] = None,
        camera_entity_id: Optional[str] = None,
        gender: Optional[int] = None,
        person_tag: Optional[str] = None,
        quality_control: int = 1,
        need_rotate_check: int = 1,
    ) -> Dict[str, Any]:
        image_base64 = None
        if any([image_url, image_path, image_file, camera_entity_id]):
            image_base64 = await self._get_image_base64_from_source(
                image_url=image_url,
                image_path=image_path,
                image_file=image_file,
                camera_entity_id=camera_entity_id,
            )

        return await self._safe_api_call(
            "创建人员",
            self.client.create_person,
            person_id=person_id,
            person_name=person_name,
            group_id=group_id,
            image_base64=image_base64,
            gender=gender,
            person_tag=person_tag,
            quality_control=quality_control,
            need_rotate_check=need_rotate_check,
        )

    async def async_delete_person(self, person_id: str) -> Dict[str, Any]:
        return await self._safe_api_call(
            "删除人员",
            self.client.delete_person,
            person_id=person_id,
        )

    async def async_create_face(
        self,
        person_id: str,
        image_url: Optional[str] = None,
        image_path: Optional[str] = None,
        image_file: Optional[str] = None,
        camera_entity_id: Optional[str] = None,
        quality_control: int = 1,
        need_rotate_check: int = 1,
    ) -> Dict[str, Any]:
        image_base64 = await self._get_image_base64_from_source(
            image_url=image_url,
            image_path=image_path,
            image_file=image_file,
            camera_entity_id=camera_entity_id,
        )

        return await self._safe_api_call(
            "注册人脸",
            self.client.create_face,
            person_id=person_id,
            image_base64=image_base64,
            quality_control=quality_control,
            need_rotate_check=need_rotate_check,
        )

    async def async_delete_face(self, person_id: str, face_id: str) -> Dict[str, Any]:
        return await self._safe_api_call(
            "删除人脸",
            self.client.delete_face,
            person_id=person_id,
            face_id=face_id,
        )
