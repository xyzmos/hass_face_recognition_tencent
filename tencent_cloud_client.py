"""腾讯云客户端"""

import base64
import io
import json
import logging
import os
import random
import re
import requests
import time
import uuid
from typing import Dict, Any, List, Optional, Union, Callable

from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.iai.v20200303 import iai_client, models

from .const import (
    CONF_SECRET_ID,
    CONF_SECRET_KEY,
    CONF_REGION,
)
from .errors import (
    handle_api_error,
    ImageNotFoundError,
    FaceNotDetectedError,
    log_and_raise_error,
    validate_config,
    NetworkError,
    AuthenticationError,
    RateLimitError,
)

_LOGGER = logging.getLogger(__name__)
_LOGGER_POLLING = _LOGGER.getChild("polling")
_LOGGER_POLLING.setLevel(logging.DEBUG)

ENABLE_REQUEST_LOGGING = False
ENABLE_RESPONSE_LOGGING = False
ENABLE_PERFORMANCE_LOGGING = True
LOG_REQUEST_PAYLOAD_MAX_SIZE = 1024
LOG_RESPONSE_PAYLOAD_MAX_SIZE = 1024

MAX_ATTEMPTS = 3
INITIAL_RETRY_DELAY = 1
MAX_RETRY_DELAY = 30
RETRY_BACKOFF_FACTOR = 2
RETRY_JITTER = 0.1

NON_RETRYABLE_ERRORS = {
    "AuthFailure",
    "InvalidParameter",
    "ResourceNotFound",
    "LimitExceeded",
    "RequestLimitExceeded",
    "RequestQuotaExceeded",
}

RATE_LIMIT_ERRORS = {
    "RequestLimitExceeded",
    "RequestQuotaExceeded",
    "LimitExceeded",
}

NETWORK_ERRORS = {
    "ResourceUnavailable.NetworkError",
    "ResourceUnavailable.ServiceTimeout",
}

MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_IMAGE_DIMENSION = 4096
SUPPORTED_IMAGE_FORMATS = [".jpg", ".jpeg", ".png", ".bmp", ".gif"]
IMAGE_COMPRESSION_QUALITY = 85
MIN_FACE_SIZE = 34


class RetryConfig:
    """重试配置类"""

    def __init__(
        self,
        max_attempts: int = MAX_ATTEMPTS,
        initial_delay: float = INITIAL_RETRY_DELAY,
        max_delay: float = MAX_RETRY_DELAY,
        backoff_factor: float = RETRY_BACKOFF_FACTOR,
        jitter: float = RETRY_JITTER
    ):
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter


class TencentCloudClient:
    """腾讯云客户端"""

    def __init__(
        self,
        secret_id: str,
        secret_key: str,
        region: str = "ap-shanghai",
        retry_config: Optional[RetryConfig] = None
    ):
        config = {
            "secret_id": secret_id,
            "secret_key": secret_key,
            "region": region
        }
        validate_config(config)

        self.secret_id = secret_id
        self.secret_key = secret_key
        self.region = region
        self.retry_config = retry_config or RetryConfig()
        self.client = self._create_client()

    def _create_client(self) -> iai_client.IaiClient:
        """创建腾讯云人脸识别客户端"""
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
                {"region": self.region, "error_type": type(ex).__name__}
            )

    def verify_credentials(self) -> bool:
        """验证凭据是否有效，通过调用 GetGroupList 测试"""
        try:
            req = models.GetGroupListRequest()
            params = {"Limit": 1, "Offset": 0}
            req.from_json_string(json.dumps(params))
            self.client.GetGroupList(req)
            _LOGGER.info("凭据验证成功")
            return True
        except TencentCloudSDKException as ex:
            _LOGGER.error("凭据验证失败: %s", ex.code)
            handle_api_error(ex.code, ex.message)

    def _handle_error(self, ex: TencentCloudSDKException) -> None:
        """处理API错误"""
        _LOGGER.error(
            "腾讯云API调用失败: 错误码=%s, 请求ID=%s",
            ex.code, getattr(ex, 'request_id', '未知')
        )
        handle_api_error(ex.code, ex.message)

    def _sanitize_error(self, error_msg: str) -> str:
        """脱敏错误信息中的凭据"""
        if self.secret_id and self.secret_id in error_msg:
            error_msg = error_msg.replace(self.secret_id, f"{self.secret_id[:8]}***")
        if self.secret_key and self.secret_key in error_msg:
            error_msg = error_msg.replace(self.secret_key, "***")
        return error_msg

    def _get_image_base64(self, image_url: str = None, image_path: str = None, image_file: str = None) -> str:
        """获取图片的base64编码"""
        _LOGGER.debug(
            "获取图片 base64: image_url=%s, image_path=%s, image_file is not None: %s",
            image_url, image_path, image_file is not None
        )

        if not any([image_url, image_path, image_file]):
            log_and_raise_error(
                ValueError,
                "必须提供image_url、image_path或image_file"
            )

        try:
            if image_url:
                _LOGGER.debug("使用图片URL: %s", image_url)
                return self._download_image_as_base64(image_url)
            elif image_path:
                _LOGGER.debug("使用本地图片路径: %s", image_path)
                return self._read_local_image_as_base64(image_path)
            elif image_file:
                _LOGGER.debug("使用上传的图片文件")
                return self._process_uploaded_image_as_base64(image_file)
        except Exception as ex:
            _LOGGER.error("处理图片失败: %s", ex)
            log_and_raise_error(
                ImageNotFoundError,
                f"处理图片失败: {str(ex)}",
                {"image_url": image_url, "image_path": image_path, "error_type": type(ex).__name__}
            )

    def _download_image_as_base64(self, image_url: str) -> str:
        """下载图片并转换为base64编码"""
        try:
            _LOGGER.debug("开始下载图片: %s", image_url)

            if not self._is_valid_url(image_url):
                log_and_raise_error(
                    ValueError,
                    f"无效的图片URL: {image_url}",
                    {"url": image_url}
                )

            session = requests.Session()
            session.mount('http://', requests.adapters.HTTPAdapter(max_retries=2))
            session.mount('https://', requests.adapters.HTTPAdapter(max_retries=2))

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            response = session.get(image_url, timeout=10, headers=headers)
            response.raise_for_status()

            content_type = response.headers.get('content-type', '').lower()
            if not content_type.startswith('image/'):
                log_and_raise_error(
                    ValueError,
                    f"URL不是有效的图片: {image_url}, 内容类型: {content_type}",
                    {"url": image_url, "content_type": content_type}
                )

            image_data = self._process_image_data(response.content)
            encoded_image = base64.b64encode(image_data).decode("utf-8")

            _LOGGER.debug("成功下载并编码图片，大小: %d 字节", len(encoded_image))
            return encoded_image

        except requests.exceptions.Timeout:
            _LOGGER.error("下载图片超时: %s", image_url)
            log_and_raise_error(
                NetworkError,
                f"下载图片超时: {image_url}",
                {"url": image_url, "error": "timeout"}
            )
        except requests.exceptions.ConnectionError:
            _LOGGER.error("下载图片连接错误: %s", image_url)
            log_and_raise_error(
                NetworkError,
                f"下载图片连接错误: {image_url}",
                {"url": image_url, "error": "connection_error"}
            )
        except requests.exceptions.RequestException as ex:
            _LOGGER.error("下载图片失败: %s", image_url)
            log_and_raise_error(
                NetworkError,
                f"下载图片失败: {image_url}",
                {"url": image_url, "error": str(ex)}
            )

    def _read_local_image_as_base64(self, image_path: str) -> str:
        """读取本地图片并转换为base64编码"""
        try:
            if not os.path.exists(image_path):
                _LOGGER.error("图片文件不存在: %s", image_path)
                log_and_raise_error(
                    ImageNotFoundError,
                    f"图片文件不存在: {image_path}",
                    {"path": image_path}
                )

            if not os.path.isfile(image_path):
                _LOGGER.error("路径不是文件: %s", image_path)
                log_and_raise_error(
                    ImageNotFoundError,
                    f"路径不是文件: {image_path}",
                    {"path": image_path}
                )

            file_ext = os.path.splitext(image_path)[1].lower()
            if file_ext not in SUPPORTED_IMAGE_FORMATS:
                _LOGGER.error("不支持的图片格式: %s", file_ext)
                log_and_raise_error(
                    ImageNotFoundError,
                    f"不支持的图片格式: {file_ext}",
                    {"path": image_path, "supported_formats": SUPPORTED_IMAGE_FORMATS}
                )

            file_size = os.path.getsize(image_path)
            if file_size > MAX_IMAGE_SIZE:
                _LOGGER.error("图片文件过大: %s, 大小: %d 字节", image_path, file_size)
                log_and_raise_error(
                    ImageNotFoundError,
                    f"图片文件过大: {image_path}",
                    {"path": image_path, "size": file_size, "max_size": f"{MAX_IMAGE_SIZE // (1024*1024)}MB"}
                )

            with open(image_path, "rb") as img_file:
                image_data = img_file.read()

            processed_image = self._process_image_data(image_data)
            encoded_image = base64.b64encode(processed_image).decode("utf-8")

            _LOGGER.debug("成功读取图片文件，大小: %d 字节", len(encoded_image))
            return encoded_image

        except PermissionError:
            _LOGGER.error("没有权限读取图片文件: %s", image_path)
            log_and_raise_error(
                ImageNotFoundError,
                f"没有权限读取图片文件: {image_path}",
                {"path": image_path, "error": "permission_denied"}
            )
        except ImageNotFoundError:
            raise
        except Exception as ex:
            _LOGGER.error("读取图片文件失败: %s", image_path)
            log_and_raise_error(
                ImageNotFoundError,
                f"读取图片文件失败: {image_path}",
                {"path": image_path, "error": str(ex)}
            )

    def _process_uploaded_image_as_base64(self, image_file: str) -> str:
        """处理上传的图片文件并转换为base64编码"""
        try:
            if isinstance(image_file, str):
                if image_file.startswith('data:image'):
                    _LOGGER.debug("处理 data URL 格式图片")
                    try:
                        header, encoded = image_file.split(',', 1)
                        image_data = base64.b64decode(encoded)
                        processed_image = self._process_image_data(image_data)
                        return base64.b64encode(processed_image).decode("utf-8")
                    except ValueError:
                        log_and_raise_error(
                            ImageNotFoundError,
                            "无效的 data URL 格式",
                            {"data_url_length": len(image_file)}
                        )
                else:
                    _LOGGER.debug("使用 base64 编码图片，长度: %d", len(image_file))
                    try:
                        image_data = base64.b64decode(image_file)
                        if len(image_data) <= MAX_IMAGE_SIZE:
                            try:
                                from PIL import Image
                                img = Image.open(io.BytesIO(image_data))
                                if (img.size[0] <= MAX_IMAGE_DIMENSION
                                        and img.size[1] <= MAX_IMAGE_DIMENSION
                                        and img.format == 'JPEG'):
                                    return image_file
                            except ImportError:
                                pass
                            except Exception:
                                pass

                        processed_image = self._process_image_data(image_data)
                        return base64.b64encode(processed_image).decode("utf-8")
                    except Exception as ex:
                        _LOGGER.error("base64解码失败: %s", ex)
                        log_and_raise_error(
                            ImageNotFoundError,
                            "base64解码失败",
                            {"error": str(ex), "data_length": len(image_file)}
                        )
            else:
                _LOGGER.debug("处理文件对象")
                image_data = image_file.read()
                processed_image = self._process_image_data(image_data)
                encoded_image = base64.b64encode(processed_image).decode("utf-8")
                _LOGGER.debug("成功读取上传的图片文件，大小: %d 字节", len(encoded_image))
                return encoded_image

        except ImageNotFoundError:
            raise
        except Exception as ex:
            _LOGGER.error("处理上传的图片文件失败: %s", ex)
            log_and_raise_error(
                ImageNotFoundError,
                "处理上传的图片文件失败",
                {"error": str(ex), "error_type": type(ex).__name__}
            )

    def search_faces(
        self,
        image_url: str = None,
        image_path: str = None,
        image_file: str = None,
        image_base64: str = None,
        group_ids: List[str] = None,
        max_face_num: int = 1,
        min_face_size: int = 34,
        max_user_num: int = 5,
        quality_control: int = 1,
        need_rotate_check: int = 1,
        face_match_threshold: float = 60.0
    ) -> Dict[str, Any]:
        """搜索人脸"""
        _LOGGER.info(
            "开始搜索人脸: max_face_num=%d, min_face_size=%d, max_user_num=%d, quality_control=%d, need_rotate_check=%d, face_match_threshold=%.2f",
            max_face_num, min_face_size, max_user_num, quality_control, need_rotate_check, face_match_threshold
        )

        if not group_ids:
            _LOGGER.warning("未提供人员库ID，搜索可能失败")

        if image_base64 is None:
            image_base64 = self._get_image_base64(image_url, image_path, image_file)

        def api_call():
            request_id = str(uuid.uuid4())
            start_time = time.time()

            try:
                req = models.SearchFacesRequest()
                params = {
                    "NeedPersonInfo": 1,
                    "Image": image_base64,
                    "MaxFaceNum": max_face_num,
                    "MinFaceSize": min_face_size,
                    "MaxPersonNum": max_user_num,
                    "QualityControl": quality_control,
                    "NeedRotateCheck": need_rotate_check,
                    "FaceMatchThreshold": face_match_threshold,
                    "GroupIds": group_ids
                }

                self._log_request("人脸搜索", params, request_id)

                req.from_json_string(json.dumps(params))

                _LOGGER.debug("发送人脸搜索请求")
                resp = self.client.SearchFaces(req)

                duration = time.time() - start_time

                self._log_response("人脸搜索", request_id, resp, duration)

                results = []
                if getattr(resp, "Results", []):
                    _LOGGER.info("检测到 %d 个人脸", len(resp.Results))
                    for result in resp.Results:
                        face_result = {
                            "face_id": getattr(result, "FaceId", None),
                            "candidates": []
                        }

                        if result.Candidates:
                            for candidate in result.Candidates:
                                candidate_info = {
                                    "person_id": candidate.PersonId,
                                    "person_name": candidate.PersonName,
                                    "score": candidate.Score,
                                    "person_tag": getattr(candidate, "PersonTag", None)
                                }
                                face_result["candidates"].append(candidate_info)

                        results.append(face_result)
                else:
                    _LOGGER.info("未检测到人脸")

                return {
                    "success": True,
                    "faces": results,
                    "error": None,
                    "error_code": None,
                    "error_message": None
                }

            except Exception as ex:
                duration = time.time() - start_time
                self._log_error("人脸搜索", request_id, ex, duration)

                error_code = None
                error_message = str(ex)

                if isinstance(ex, TencentCloudSDKException):
                    error_code = getattr(ex, "code", None)
                    error_message = getattr(ex, "message", str(ex))

                return {
                    "success": False,
                    "faces": [],
                    "error": str(ex),
                    "error_code": error_code,
                    "error_message": error_message
                }

        return self._execute_with_retry(api_call, "人脸搜索")

    def detect_faces(
        self,
        image_url: str = None,
        image_path: str = None,
        image_file: str = None,
        image_base64: str = None,
        max_face_num: int = 1,
        min_face_size: int = 34,
        need_rotate_check: int = 1
    ) -> Dict[str, Any]:
        """检测人脸"""
        _LOGGER.info(
            "开始检测人脸: max_face_num=%d, min_face_size=%d, need_rotate_check=%d",
            max_face_num, min_face_size, need_rotate_check
        )

        if image_base64 is None:
            image_base64 = self._get_image_base64(image_url, image_path, image_file)

        def api_call():
            request_id = str(uuid.uuid4())
            start_time = time.time()

            try:
                req = models.DetectFaceRequest()
                params = {
                    "Image": image_base64,
                    "MaxFaceNum": max_face_num,
                    "MinFaceSize": min_face_size,
                    "NeedRotateCheck": need_rotate_check
                }

                self._log_request("人脸检测", params, request_id)

                req.from_json_string(json.dumps(params))

                _LOGGER.debug("发送人脸检测请求")
                resp = self.client.DetectFace(req)

                duration = time.time() - start_time
                self._log_response("人脸检测", request_id, resp, duration)

                results = []
                if getattr(resp, "FaceInfos", []):
                    _LOGGER.info("检测到 %d 个人脸", len(resp.FaceInfos))
                    for face_info in resp.FaceInfos:
                        face_result = {
                            "face_id": getattr(face_info, "FaceId", ""),
                            "x": getattr(face_info, "X", 0),
                            "y": getattr(face_info, "Y", 0),
                            "width": getattr(face_info, "Width", 0),
                            "height": getattr(face_info, "Height", 0),
                            "face_rect": getattr(face_info, "FaceRect", None).__dict__ if getattr(face_info, "FaceRect", None) else None
                        }
                        results.append(face_result)
                else:
                    _LOGGER.info("未检测到人脸")

                return {
                    "success": True,
                    "faces": results,
                    "error": None,
                    "error_code": None,
                    "error_message": None
                }

            except Exception as ex:
                duration = time.time() - start_time
                self._log_error("人脸检测", request_id, ex, duration)

                error_code = None
                error_message = str(ex)

                if isinstance(ex, TencentCloudSDKException):
                    error_code = getattr(ex, "code", None)
                    error_message = getattr(ex, "message", str(ex))

                return {
                    "success": False,
                    "faces": [],
                    "error": str(ex),
                    "error_code": error_code,
                    "error_message": error_message
                }

        return self._execute_with_retry(api_call, "人脸检测")

    def get_face_attributes(
        self,
        image_url: str = None,
        image_path: str = None,
        image_file: str = None,
        image_base64: str = None,
        max_face_num: int = 1,
        need_rotate_check: int = 1
    ) -> Dict[str, Any]:
        """获取人脸属性"""
        _LOGGER.info(
            "开始获取人脸属性: max_face_num=%d, need_rotate_check=%d",
            max_face_num, need_rotate_check
        )

        if image_base64 is None:
            image_base64 = self._get_image_base64(image_url, image_path, image_file)

        def api_call():
            request_id = str(uuid.uuid4())
            start_time = time.time()

            try:
                req = models.DetectFaceRequest()
                params = {
                    "Image": image_base64,
                    "MaxFaceNum": max_face_num,
                    "NeedRotateCheck": need_rotate_check,
                    "NeedFaceAttributes": 1,
                    "NeedQualityDetection": 1,
                }

                self._log_request("获取人脸属性", params, request_id)

                req.from_json_string(json.dumps(params))

                _LOGGER.debug("发送获取人脸属性请求")
                resp = self.client.DetectFace(req)

                duration = time.time() - start_time
                self._log_response("获取人脸属性", request_id, resp, duration)

                results = []
                if getattr(resp, "FaceInfos", []):
                    _LOGGER.info("检测到 %d 个人脸", len(resp.FaceInfos))
                    for face_info in resp.FaceInfos:
                        face_result = {
                            "face_id": getattr(face_info, "FaceId", ""),
                            "x": getattr(face_info, "X", 0),
                            "y": getattr(face_info, "Y", 0),
                            "width": getattr(face_info, "Width", 0),
                            "height": getattr(face_info, "Height", 0),
                            "gender": getattr(face_info, "Gender", None),
                            "age": getattr(face_info, "Age", None),
                            "expression": getattr(face_info, "Expression", None),
                            "beauty": getattr(face_info, "Beauty", None),
                            "face_rect": getattr(face_info, "FaceRect", None).__dict__ if getattr(face_info, "FaceRect", None) else None
                        }
                        results.append(face_result)
                else:
                    _LOGGER.info("未检测到人脸")

                return {
                    "success": True,
                    "faces": results,
                    "error": None,
                    "error_code": None,
                    "error_message": None
                }

            except Exception as ex:
                duration = time.time() - start_time
                self._log_error("获取人脸属性", request_id, ex, duration)

                error_code = None
                error_message = str(ex)

                if isinstance(ex, TencentCloudSDKException):
                    error_code = getattr(ex, "code", None)
                    error_message = getattr(ex, "message", str(ex))

                return {
                    "success": False,
                    "faces": [],
                    "error": str(ex),
                    "error_code": error_code,
                    "error_message": error_message
                }

        return self._execute_with_retry(api_call, "获取人脸属性")

    def create_person(
        self,
        person_id: str,
        person_name: str,
        group_id: str,
        image_url: str = None,
        image_path: str = None,
        image_file: str = None,
        image_base64: str = None,
        gender: int = None,
        person_tag: str = None,
        quality_control: int = 1,
        need_rotate_check: int = 1,
    ) -> Dict[str, Any]:
        """创建人员"""
        _LOGGER.info("开始创建人员: person_id=%s, group_id=%s", person_id, group_id)

        if image_base64 is None and any([image_url, image_path, image_file]):
            image_base64 = self._get_image_base64(image_url, image_path, image_file)

        def api_call():
            request_id = str(uuid.uuid4())
            start_time = time.time()
            try:
                req = models.CreatePersonRequest()
                params = {
                    "PersonId": person_id,
                    "PersonName": person_name,
                    "GroupId": group_id,
                    "QualityControl": quality_control,
                    "NeedRotateCheck": need_rotate_check,
                }
                if image_base64:
                    params["Image"] = image_base64
                if gender is not None:
                    params["Gender"] = gender
                if person_tag is not None:
                    params["PersonTag"] = person_tag

                self._log_request("创建人员", params, request_id)
                req.from_json_string(json.dumps(params))

                _LOGGER.debug("发送创建人员请求")
                resp = self.client.CreatePerson(req)

                duration = time.time() - start_time
                self._log_response("创建人员", request_id, resp, duration)

                return {
                    "success": True,
                    "person_id": getattr(resp, "PersonId", person_id),
                    "face_id": getattr(resp, "FaceId", ""),
                    "face_rect": str(getattr(resp, "FaceRect", "")),
                }
            except Exception as ex:
                duration = time.time() - start_time
                self._log_error("创建人员", request_id, ex, duration)
                raise

        return self._execute_with_retry(api_call, "创建人员")

    def delete_person(self, person_id: str) -> Dict[str, Any]:
        """删除人员"""
        _LOGGER.info("开始删除人员: person_id=%s", person_id)

        def api_call():
            request_id = str(uuid.uuid4())
            start_time = time.time()
            try:
                req = models.DeletePersonRequest()
                params = {"PersonId": person_id}
                self._log_request("删除人员", params, request_id)
                req.from_json_string(json.dumps(params))

                _LOGGER.debug("发送删除人员请求")
                resp = self.client.DeletePerson(req)

                duration = time.time() - start_time
                self._log_response("删除人员", request_id, resp, duration)

                return {"success": True, "person_id": person_id}
            except Exception as ex:
                duration = time.time() - start_time
                self._log_error("删除人员", request_id, ex, duration)
                raise

        return self._execute_with_retry(api_call, "删除人员")

    def create_face(
        self,
        person_id: str,
        image_url: str = None,
        image_path: str = None,
        image_file: str = None,
        image_base64: str = None,
        quality_control: int = 1,
        need_rotate_check: int = 1,
    ) -> Dict[str, Any]:
        """为人员注册人脸"""
        _LOGGER.info("开始注册人脸: person_id=%s", person_id)

        if image_base64 is None:
            image_base64 = self._get_image_base64(image_url, image_path, image_file)

        def api_call():
            request_id = str(uuid.uuid4())
            start_time = time.time()
            try:
                req = models.CreateFaceRequest()
                params = {
                    "PersonId": person_id,
                    "Image": image_base64,
                    "QualityControl": quality_control,
                    "NeedRotateCheck": need_rotate_check,
                }
                self._log_request("注册人脸", params, request_id)
                req.from_json_string(json.dumps(params))

                _LOGGER.debug("发送注册人脸请求")
                resp = self.client.CreateFace(req)

                duration = time.time() - start_time
                self._log_response("注册人脸", request_id, resp, duration)

                return {
                    "success": True,
                    "person_id": person_id,
                    "face_ids": getattr(resp, "FaceIds", []),
                    "face_rects": [str(r) for r in getattr(resp, "FaceRects", [])],
                }
            except Exception as ex:
                duration = time.time() - start_time
                self._log_error("注册人脸", request_id, ex, duration)
                raise

        return self._execute_with_retry(api_call, "注册人脸")

    def delete_face(self, person_id: str, face_id: str) -> Dict[str, Any]:
        """删除人脸"""
        _LOGGER.info("开始删除人脸: person_id=%s, face_id=%s", person_id, face_id)

        def api_call():
            request_id = str(uuid.uuid4())
            start_time = time.time()
            try:
                req = models.DeleteFaceRequest()
                params = {
                    "PersonId": person_id,
                    "FaceId": face_id,
                }
                self._log_request("删除人脸", params, request_id)
                req.from_json_string(json.dumps(params))

                _LOGGER.debug("发送删除人脸请求")
                resp = self.client.DeleteFace(req)

                duration = time.time() - start_time
                self._log_response("删除人脸", request_id, resp, duration)

                return {"success": True, "person_id": person_id, "face_id": face_id}
            except Exception as ex:
                duration = time.time() - start_time
                self._log_error("删除人脸", request_id, ex, duration)
                raise

        return self._execute_with_retry(api_call, "删除人脸")

    def get_group_info(self, group_id: str) -> Dict[str, Any]:
        """获取人员库信息"""
        _LOGGER.info("开始获取人员库信息: group_id=%s", group_id)

        def api_call():
            request_id = str(uuid.uuid4())
            start_time = time.time()
            try:
                req = models.GetGroupInfoRequest()
                params = {"GroupId": group_id}
                self._log_request("获取人员库信息", params, request_id)
                req.from_json_string(json.dumps(params))

                _LOGGER.debug("发送获取人员库信息请求")
                resp = self.client.GetGroupInfo(req)

                duration = time.time() - start_time
                self._log_response("获取人员库信息", request_id, resp, duration)

                return {
                    "group_name": getattr(resp, "GroupName", ""),
                    "group_tag": getattr(resp, "GroupTag", ""),
                    "face_model_version": getattr(resp, "FaceModelVersion", ""),
                    "creation_timestamp": getattr(resp, "CreationTimestamp", 0),
                }
            except Exception as ex:
                duration = time.time() - start_time
                self._log_error("获取人员库信息", request_id, ex, duration)
                raise

        return self._execute_with_retry(api_call, "获取人员库信息")

    def verify_credentials_lightweight(self) -> bool:
        """测试API连接，使用 GetGroupList 轻量验证凭据"""
        try:
            _LOGGER.info("开始测试API连接（轻量验证）")
            req = models.GetGroupListRequest()
            params = {"Limit": 1, "Offset": 0}
            req.from_json_string(json.dumps(params))
            self.client.GetGroupList(req)
            _LOGGER.info("API连接测试成功")
            return True
        except Exception as ex:
            _LOGGER.error("API连接测试失败: %s", self._sanitize_error(str(ex)))
            return False

    def _test_api_connection(self, group_id: str) -> bool:
        """测试API连接"""
        try:
            _LOGGER.info("开始测试API连接: group_id=%s", group_id)
            self.get_group_info(group_id)
            _LOGGER.info("API连接测试成功")
            return True
        except Exception as ex:
            _LOGGER.error("API连接测试失败: %s", self._sanitize_error(str(ex)))
            return False

    def get_person_list(self, group_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """获取人员列表"""
        _LOGGER.info("开始获取人员列表: group_id=%s, limit=%d, offset=%d", group_id, limit, offset)

        def api_call():
            request_id = str(uuid.uuid4())
            start_time = time.time()
            try:
                req = models.GetPersonListRequest()
                params = {
                    "GroupId": group_id,
                    "Limit": limit,
                    "Offset": offset
                }
                self._log_request("获取人员列表", params, request_id)
                req.from_json_string(json.dumps(params))

                _LOGGER.debug("发送获取人员列表请求")
                resp = self.client.GetPersonList(req)

                duration = time.time() - start_time
                self._log_response("获取人员列表", request_id, resp, duration)

                persons = []
                if getattr(resp, "PersonInfos", []):
                    for person_info in resp.PersonInfos:
                        persons.append({
                            "person_name": getattr(person_info, "PersonName", ""),
                            "person_id": getattr(person_info, "PersonId", ""),
                            "gender": getattr(person_info, "Gender", 0),
                            "face_ids": getattr(person_info, "FaceIds", []),
                        })
                return persons
            except Exception as ex:
                duration = time.time() - start_time
                self._log_error("获取人员列表", request_id, ex, duration)
                raise

        return self._execute_with_retry(api_call, "获取人员列表")

    def get_person_list_all(self, group_id: str) -> List[Dict[str, Any]]:
        """获取人员列表（自动分页获取全部）"""
        all_persons = []
        offset = 0
        limit = 100
        while True:
            persons = self.get_person_list(group_id, limit=limit, offset=offset)
            all_persons.extend(persons)
            if len(persons) < limit:
                break
            offset += limit
        return all_persons

    def _execute_with_retry(self, api_call: Callable, operation_name: str) -> Any:
        """执行带重试的API调用，max_attempts 为总尝试次数（1次初始 + N次重试）"""
        last_exception = None

        for attempt in range(self.retry_config.max_attempts):
            try:
                if attempt > 0:
                    delay = self._calculate_retry_delay(attempt)
                    _LOGGER.info("重试第 %d 次%s，延迟 %.2f 秒", attempt, operation_name, delay)
                    time.sleep(delay)

                return api_call()

            except TencentCloudSDKException as ex:
                last_exception = ex
                _LOGGER.warning("%s失败 (尝试 %d/%d): %s", operation_name, attempt + 1, self.retry_config.max_attempts, ex.code)

                if not self._should_retry(ex):
                    _LOGGER.error("遇到不可重试的错误: %s", ex.code)
                    self._handle_error(ex)
                    break

            except Exception as ex:
                last_exception = ex
                _LOGGER.warning("%s失败 (尝试 %d/%d): %s", operation_name, attempt + 1, self.retry_config.max_attempts, ex)

        if last_exception:
            if isinstance(last_exception, TencentCloudSDKException):
                self._handle_error(last_exception)
            else:
                _LOGGER.error("%s最终失败: %s", operation_name, last_exception)
                log_and_raise_error(
                    RuntimeError,
                    f"{operation_name}失败: {str(last_exception)}",
                    {"error": str(last_exception), "error_type": type(last_exception).__name__}
                )

    def _calculate_retry_delay(self, attempt: int) -> float:
        """计算重试延迟时间"""
        delay = self.retry_config.initial_delay * (
            self.retry_config.backoff_factor ** (attempt - 1)
        )

        delay = min(delay, self.retry_config.max_delay)

        jitter = delay * self.retry_config.jitter
        delay = delay + random.uniform(-jitter, jitter)

        return max(0, delay)

    def _should_retry(self, ex: TencentCloudSDKException) -> bool:
        """判断是否应该重试"""
        if ex.code in NON_RETRYABLE_ERRORS:
            return False

        if ex.code in RATE_LIMIT_ERRORS:
            return True

        if ex.code in NETWORK_ERRORS:
            return True

        return True

    def _is_valid_url(self, url: str) -> bool:
        """验证URL格式是否有效"""
        url_pattern = re.compile(
            r'^https?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?'
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return url_pattern.match(url) is not None

    def _process_image_data(self, image_data: bytes) -> bytes:
        """处理图片数据，包括压缩和格式转换"""
        try:
            if len(image_data) > MAX_IMAGE_SIZE:
                _LOGGER.warning("图片大小超过限制，尝试压缩: %d 字节", len(image_data))
                image_data = self._compress_image(image_data)

            try:
                from PIL import Image

                img = Image.open(io.BytesIO(image_data))

                width, height = img.size
                if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                    _LOGGER.warning("图片尺寸过大，尝试缩放: %dx%d", width, height)

                    scale = min(MAX_IMAGE_DIMENSION / width, MAX_IMAGE_DIMENSION / height)
                    new_width = int(width * scale)
                    new_height = int(height * scale)

                    img = img.resize((new_width, new_height), Image.LANCZOS)

                    output = io.BytesIO()
                    img.save(output, format='JPEG', quality=IMAGE_COMPRESSION_QUALITY)
                    image_data = output.getvalue()

                    _LOGGER.info("图片缩放完成: %dx%d -> %dx%d", width, height, new_width, new_height)

                if img.format != 'JPEG':
                    _LOGGER.debug("转换图片格式为JPEG: %s", img.format)
                    output = io.BytesIO()
                    if img.mode == 'RGBA':
                        img = img.convert('RGB')
                    img.save(output, format='JPEG', quality=IMAGE_COMPRESSION_QUALITY)
                    image_data = output.getvalue()

            except ImportError:
                _LOGGER.warning("PIL库(Pillow)未安装，无法进行图片处理。建议安装: pip install Pillow>=10.0.0")
            except Exception as ex:
                _LOGGER.warning("图片处理失败: %s", ex)

            return image_data

        except Exception as ex:
            _LOGGER.error("处理图片数据失败: %s", ex)
            return image_data

    def _compress_image(self, image_data: bytes) -> bytes:
        """压缩图片数据"""
        try:
            from PIL import Image

            img = Image.open(io.BytesIO(image_data))

            original_size = len(image_data)
            target_size = MAX_IMAGE_SIZE * 0.8
            quality = IMAGE_COMPRESSION_QUALITY

            while quality > 30 and original_size > target_size:
                output = io.BytesIO()
                img.save(output, format='JPEG', quality=quality)
                compressed_data = output.getvalue()

                if len(compressed_data) <= target_size:
                    break

                quality -= 5
                original_size = len(compressed_data)

            _LOGGER.info("图片压缩完成: %d -> %d 字节 (质量: %d)",
                        len(image_data), len(compressed_data), quality)

            return compressed_data

        except ImportError:
            _LOGGER.warning("PIL库(Pillow)未安装，无法进行图片压缩。建议安装: pip install Pillow>=10.0.0")
            return image_data
        except Exception as ex:
            _LOGGER.error("图片压缩失败: %s", ex)
            return image_data

    def _log_request(self, operation: str, params: Dict[str, Any], request_id: str) -> None:
        """记录API请求日志"""
        if not ENABLE_REQUEST_LOGGING:
            return

        _LOGGER.debug(
            "API请求: operation=%s, request_id=%s, params_count=%d",
            operation, request_id, len(params)
        )

        if ENABLE_PERFORMANCE_LOGGING:
            safe_params = {}
            for key, value in params.items():
                if key == "Image":
                    safe_params[key] = f"<base64_image_{len(str(value))}_chars>"
                else:
                    safe_params[key] = value

            params_str = json.dumps(safe_params, ensure_ascii=False)
            if len(params_str) > LOG_REQUEST_PAYLOAD_MAX_SIZE:
                params_str = params_str[:LOG_REQUEST_PAYLOAD_MAX_SIZE] + "...[truncated]"

            _LOGGER.debug(
                "API请求详情: operation=%s, request_id=%s, params=%s",
                operation, request_id, params_str
            )

    def _log_response(self, operation: str, request_id: str, response: Any, duration: float) -> None:
        """记录API响应日志"""
        if not ENABLE_RESPONSE_LOGGING:
            return

        _LOGGER.debug(
            "API响应: operation=%s, request_id=%s, duration=%.3fs, response_type=%s",
            operation, request_id, duration, type(response).__name__
        )

        if ENABLE_PERFORMANCE_LOGGING:
            if duration > 5.0:
                _LOGGER.warning(
                    "API响应缓慢: operation=%s, request_id=%s, duration=%.3fs",
                    operation, request_id, duration
                )
            elif duration > 2.0:
                _LOGGER.info(
                    "API响应较慢: operation=%s, request_id=%s, duration=%.3fs",
                    operation, request_id, duration
                )

        try:
            if hasattr(response, "__dict__"):
                response_dict = {}
                for attr in dir(response):
                    if not attr.startswith("_") and not callable(getattr(response, attr)):
                        response_dict[attr] = getattr(response, attr)

                response_str = json.dumps(response_dict, ensure_ascii=False, default=str)
            else:
                response_str = str(response)

            if len(response_str) > LOG_RESPONSE_PAYLOAD_MAX_SIZE:
                response_str = response_str[:LOG_RESPONSE_PAYLOAD_MAX_SIZE] + "...[truncated]"

            _LOGGER.debug(
                "API响应详情: operation=%s, request_id=%s, response=%s",
                operation, request_id, response_str
            )
        except Exception as ex:
            _LOGGER.debug(
                "无法记录API响应详情: operation=%s, request_id=%s, error=%s",
                operation, request_id, ex
            )

    def _log_error(self, operation: str, request_id: str, error: Exception, duration: float) -> None:
        """记录API错误日志"""
        error_type = type(error).__name__
        error_msg = self._sanitize_error(str(error))

        _LOGGER.error(
            "API错误: operation=%s, request_id=%s, duration=%.3fs, error_type=%s",
            operation, request_id, duration, error_type
        )

        if isinstance(error, TencentCloudSDKException):
            _LOGGER.error(
                "腾讯云API错误详情: operation=%s, request_id=%s, code=%s",
                operation, request_id, getattr(error, "code", "未知")
            )

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "API错误堆栈跟踪: operation=%s, request_id=%s",
                operation, request_id, exc_info=True
            )
