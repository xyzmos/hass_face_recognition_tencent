"""腾讯云人脸识别客户端（精简门面）。

原 1311 行的客户端已拆分为：
- ``retry.py``: 重试配置与执行器
- ``image_processor.py``: 图片获取/压缩/编码
- ``api_operations.py``: 各 API 操作的实现（搜索/检测/属性/人员/人脸/库信息/列表）

本文件仅保留：凭据创建、HTTP Session 管理、错误脱敏、以及对外暴露的
``TencentCloudClient`` 门面，委托给上述模块。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)
from tencentcloud.iai.v20200303 import iai_client

from . import api_operations
from .errors import (
    ApiError,
    AuthenticationError,
    log_and_raise_error,
    validate_config,
)
from .image_processor import ImageCache, get_image_base64
from .retry import RetryConfig
from .const import CONF_REGION, CONF_SECRET_ID, CONF_SECRET_KEY

_LOGGER = logging.getLogger(__name__)


class TencentCloudClient:
    """腾讯云人脸识别客户端门面。"""

    def __init__(
        self,
        secret_id: str,
        secret_key: str,
        region: str = "ap-shanghai",
        retry_config: Optional[RetryConfig] = None,
    ) -> None:
        validate_config({
            CONF_SECRET_ID: secret_id,
            CONF_SECRET_KEY: secret_key,
            CONF_REGION: region,
        })

        self.secret_id = secret_id
        self.secret_key = secret_key
        self.region = region
        self.retry_config = retry_config or RetryConfig()
        self.client = self._create_client()

        # HTTP 连接池化
        self._session = requests.Session()
        self._session.mount(
            "http://", requests.adapters.HTTPAdapter(max_retries=2)
        )
        self._session.mount(
            "https://", requests.adapters.HTTPAdapter(max_retries=2)
        )

        # 图片缓存（url/path），通过 session 下载
        self._image_cache = ImageCache(
            maxsize=32,
            download_fn=lambda url: get_image_base64(
                image_url=url, session=self._session
            ),
            read_fn=None,
        )

    # --- 资源管理 --------------------------------------------------------

    def close(self) -> None:
        """释放 HTTP Session 等资源。"""
        if self._session:
            self._session.close()
        self._image_cache.clear()

    # --- 客户端创建 -------------------------------------------------------

    def _create_client(self) -> iai_client.IaiClient:
        try:
            _LOGGER.debug("创建腾讯云客户端，区域: %s", self.region)
            cred = credential.Credential(self.secret_id, self.secret_key)
            client = iai_client.IaiClient(cred, self.region)
            _LOGGER.debug("腾讯云客户端创建成功")
            return client
        except Exception as ex:
            _LOGGER.error("创建腾讯云客户端失败: %s", self._sanitize_error(str(ex)))
            log_and_raise_error(
                AuthenticationError,
                "创建腾讯云客户端失败",
                {"region": self.region, "error_type": type(ex).__name__},
            )

    # --- 凭据验证 ---------------------------------------------------------

    def verify_credentials(self) -> bool:
        """验证凭据（轻量 GetGroupList）。失败抛出对应错误。"""
        return api_operations.verify_credentials(
            self.client, retry_config=self.retry_config
        )

    def verify_credentials_lightweight(self) -> bool:
        """测试 API 连接（轻量验证）。失败返回 False，不抛异常。"""
        try:
            self.verify_credentials()
            return True
        except Exception as ex:  # noqa: BLE001
            _LOGGER.error("API连接测试失败: %s", self._sanitize_error(str(ex)))
            return False

    def test_api_connection(self, group_id: str) -> bool:
        """测试与指定人员库的连接。失败返回 False。"""
        try:
            _LOGGER.info("开始测试API连接: group_id=%s", group_id)
            result = self.get_group_info(group_id)
            if result.get("success", False):
                _LOGGER.info("API连接测试成功")
                return True
            _LOGGER.error("API连接测试失败: %s", result.get("error_message"))
            return False
        except Exception as ex:  # noqa: BLE001
            _LOGGER.error("API连接测试失败: %s", self._sanitize_error(str(ex)))
            return False

    # 兼容旧调用名
    _test_api_connection = test_api_connection

    # --- 图片 ------------------------------------------------------------

    def _get_image_base64(
        self,
        image_url: Optional[str] = None,
        image_path: Optional[str] = None,
        image_file: Optional[Any] = None,
    ) -> str:
        """获取图片 base64（带 url/path 缓存）。"""
        if image_url:
            return self._image_cache.get_url(image_url)
        if image_path:
            return self._image_cache.get_path(image_path)
        if image_file:
            return self._image_cache.get(image_file=image_file)
        log_and_raise_error(
            ApiError,
            "必须提供 image_url、image_path 或 image_file",
            {"reason": "no_image_source"},
        )

    # --- 业务 API（委托 api_operations） ----------------------------------

    def search_faces(
        self,
        image_url: Optional[str] = None,
        image_path: Optional[str] = None,
        image_file: Optional[Any] = None,
        image_base64: Optional[str] = None,
        group_ids: Optional[List[str]] = None,
        max_face_num: int = 1,
        min_face_size: int = 34,
        max_user_num: int = 5,
        quality_control: int = 1,
        need_rotate_check: int = 1,
        face_match_threshold: float = 60.0,
    ) -> Dict[str, Any]:
        if image_base64 is None:
            image_base64 = self._get_image_base64(image_url, image_path, image_file)
        if not group_ids:
            _LOGGER.warning("未提供人员库ID，搜索可能失败")
        return api_operations.search_faces(
            self.client,
            image_base64=image_base64,
            group_ids=group_ids or [],
            max_face_num=max_face_num,
            min_face_size=min_face_size,
            max_user_num=max_user_num,
            quality_control=quality_control,
            need_rotate_check=need_rotate_check,
            face_match_threshold=face_match_threshold,
            retry_config=self.retry_config,
            sanitize=self._sanitize_error,
        )

    def detect_faces(
        self,
        image_url: Optional[str] = None,
        image_path: Optional[str] = None,
        image_file: Optional[Any] = None,
        image_base64: Optional[str] = None,
        max_face_num: int = 1,
        min_face_size: int = 34,
        need_rotate_check: int = 1,
    ) -> Dict[str, Any]:
        if image_base64 is None:
            image_base64 = self._get_image_base64(image_url, image_path, image_file)
        return api_operations.detect_faces(
            self.client,
            image_base64=image_base64,
            max_face_num=max_face_num,
            min_face_size=min_face_size,
            need_rotate_check=need_rotate_check,
            retry_config=self.retry_config,
            sanitize=self._sanitize_error,
        )

    def get_face_attributes(
        self,
        image_url: Optional[str] = None,
        image_path: Optional[str] = None,
        image_file: Optional[Any] = None,
        image_base64: Optional[str] = None,
        max_face_num: int = 1,
        need_rotate_check: int = 1,
    ) -> Dict[str, Any]:
        if image_base64 is None:
            image_base64 = self._get_image_base64(image_url, image_path, image_file)
        return api_operations.get_face_attributes(
            self.client,
            image_base64=image_base64,
            max_face_num=max_face_num,
            need_rotate_check=need_rotate_check,
            retry_config=self.retry_config,
            sanitize=self._sanitize_error,
        )

    def create_person(
        self,
        person_id: str,
        person_name: str,
        group_id: str,
        image_url: Optional[str] = None,
        image_path: Optional[str] = None,
        image_file: Optional[Any] = None,
        image_base64: Optional[str] = None,
        gender: Optional[int] = None,
        person_tag: Optional[str] = None,
        quality_control: int = 1,
        need_rotate_check: int = 1,
    ) -> Dict[str, Any]:
        if image_base64 is None and any([image_url, image_path, image_file]):
            image_base64 = self._get_image_base64(image_url, image_path, image_file)
        return api_operations.create_person(
            self.client,
            person_id=person_id,
            person_name=person_name,
            group_id=group_id,
            image_base64=image_base64,
            gender=gender,
            person_tag=person_tag,
            quality_control=quality_control,
            need_rotate_check=need_rotate_check,
            retry_config=self.retry_config,
            sanitize=self._sanitize_error,
        )

    def delete_person(self, person_id: str) -> Dict[str, Any]:
        return api_operations.delete_person(
            self.client,
            person_id=person_id,
            retry_config=self.retry_config,
            sanitize=self._sanitize_error,
        )

    def create_face(
        self,
        person_id: str,
        image_url: Optional[str] = None,
        image_path: Optional[str] = None,
        image_file: Optional[Any] = None,
        image_base64: Optional[str] = None,
        quality_control: int = 1,
        need_rotate_check: int = 1,
    ) -> Dict[str, Any]:
        if image_base64 is None:
            image_base64 = self._get_image_base64(image_url, image_path, image_file)
        return api_operations.create_face(
            self.client,
            person_id=person_id,
            image_base64=image_base64,
            quality_control=quality_control,
            need_rotate_check=need_rotate_check,
            retry_config=self.retry_config,
            sanitize=self._sanitize_error,
        )

    def delete_face(self, person_id: str, face_id: str) -> Dict[str, Any]:
        return api_operations.delete_face(
            self.client,
            person_id=person_id,
            face_id=face_id,
            retry_config=self.retry_config,
            sanitize=self._sanitize_error,
        )

    def get_group_info(self, group_id: str) -> Dict[str, Any]:
        return api_operations.get_group_info(
            self.client,
            group_id=group_id,
            retry_config=self.retry_config,
            sanitize=self._sanitize_error,
        )

    def get_person_list(
        self, group_id: str, limit: int = 100, offset: int = 0
    ) -> Dict[str, Any]:
        return api_operations.get_person_list(
            self.client,
            group_id=group_id,
            limit=limit,
            offset=offset,
            retry_config=self.retry_config,
            sanitize=self._sanitize_error,
        )

    def get_person_list_all(self, group_id: str) -> Dict[str, Any]:
        return api_operations.get_person_list_all(
            self.client,
            group_id=group_id,
            retry_config=self.retry_config,
            sanitize=self._sanitize_error,
        )

    # --- 辅助 ------------------------------------------------------------

    def _sanitize_error(self, error_msg: str) -> str:
        """脱敏错误信息中的凭据。"""
        if not isinstance(error_msg, str):
            return str(error_msg)
        if self.secret_id and self.secret_id in error_msg:
            error_msg = error_msg.replace(
                self.secret_id, f"{self.secret_id[:8]}***"
            )
        if self.secret_key and self.secret_key in error_msg:
            error_msg = error_msg.replace(self.secret_key, "***")
        return error_msg

    # 兼容旧代码：暴露 TencentCloudSDKException 别名
    @staticmethod
    def is_sdk_exception(ex: Exception) -> bool:
        return isinstance(ex, TencentCloudSDKException)
