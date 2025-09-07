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

# 日志记录配置
ENABLE_REQUEST_LOGGING = True  # 是否启用请求日志记录
ENABLE_RESPONSE_LOGGING = True  # 是否启用响应日志记录
ENABLE_PERFORMANCE_LOGGING = True  # 是否启用性能日志记录
LOG_REQUEST_PAYLOAD_MAX_SIZE = 1024  # 请求负载日志记录的最大大小（字节）
LOG_RESPONSE_PAYLOAD_MAX_SIZE = 1024  # 响应负载日志记录的最大大小（字节）

# API调用重试配置
MAX_RETRIES = 1
INITIAL_RETRY_DELAY = 1  # 秒
MAX_RETRY_DELAY = 30  # 秒
RETRY_BACKOFF_FACTOR = 2  # 指数退避因子
RETRY_JITTER = 0.1  # 抖动因子，避免多个客户端同时重试

# 错误码分类
NON_RETRYABLE_ERRORS = {
    "AuthFailure",  # 认证失败
    "InvalidParameter",  # 无效参数
    "ResourceNotFound",  # 资源未找到
    "LimitExceeded",  # 配额超限
    "RequestLimitExceeded",  # 请求频率超限
    "RequestQuotaExceeded",  # 请求配额超限
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

# 图片处理配置
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_IMAGE_DIMENSION = 4096  # 最大图片尺寸
SUPPORTED_IMAGE_FORMATS = [".jpg", ".jpeg", ".png", ".bmp", ".gif"]
IMAGE_COMPRESSION_QUALITY = 85  # 图片压缩质量
MIN_FACE_SIZE = 34  # 最小人脸尺寸


class RetryConfig:
    """重试配置类"""
    
    def __init__(
        self,
        max_retries: int = MAX_RETRIES,
        initial_delay: float = INITIAL_RETRY_DELAY,
        max_delay: float = MAX_RETRY_DELAY,
        backoff_factor: float = RETRY_BACKOFF_FACTOR,
        jitter: float = RETRY_JITTER
    ):
        self.max_retries = max_retries
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
        """初始化腾讯云客户端"""
        # 验证配置
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
            _LOGGER.error("创建腾讯云客户端失败: %s", ex, exc_info=True)
            log_and_raise_error(
                AuthenticationError,
                f"创建腾讯云客户端失败: {str(ex)}",
                {"region": self.region, "error_type": type(ex).__name__}
            )

    def _handle_error(self, ex: TencentCloudSDKException) -> None:
        """处理API错误"""
        _LOGGER.error(
            "腾讯云API调用失败: 错误码=%s, 错误消息=%s, 请求ID=%s",
            ex.code, ex.message, getattr(ex, 'request_id', '未知')
        )
        handle_api_error(ex.code, ex.message)

    def _get_image_base64(self, image_url: str = None, image_path: str = None, image_file: str = None) -> str:
        """获取图片的base64编码"""
        _LOGGER.debug(
            "获取图片 base64: image_url=%s, image_path=%s, image_file is not None: %s",
            image_url, image_path, image_file is not None
        )
        
        # 验证参数
        if not any([image_url, image_path, image_file]):
            log_and_raise_error(
                ValueError,
                "必须提供image_url、image_path或image_file"
            )
        
        try:
            if image_url:
                # 如果是URL，下载图片并转换为base64
                _LOGGER.debug("使用图片URL: %s", image_url)
                return self._download_image_as_base64(image_url)
            elif image_path:
                # 如果是本地文件路径，读取文件并转换为base64
                _LOGGER.debug("使用本地图片路径: %s", image_path)
                return self._read_local_image_as_base64(image_path)
            elif image_file:
                # 如果是上传的文件，直接转换为base64
                _LOGGER.debug("使用上传的图片文件")
                return self._process_uploaded_image_as_base64(image_file)
        except Exception as ex:
            _LOGGER.error("处理图片失败: %s", ex, exc_info=True)
            log_and_raise_error(
                ImageNotFoundError,
                f"处理图片失败: {str(ex)}",
                {"image_url": image_url, "image_path": image_path, "error_type": type(ex).__name__}
            )
    
    def _download_image_as_base64(self, image_url: str) -> str:
        """下载图片并转换为base64编码"""
        try:
            _LOGGER.debug("开始下载图片: %s", image_url)
            
            # 验证URL格式
            if not self._is_valid_url(image_url):
                log_and_raise_error(
                    ValueError,
                    f"无效的图片URL: {image_url}",
                    {"url": image_url}
                )
            
            # 设置请求超时和重试
            session = requests.Session()
            session.mount('http://', requests.adapters.HTTPAdapter(max_retries=2))
            session.mount('https://', requests.adapters.HTTPAdapter(max_retries=2))
            
            # 设置请求头，模拟浏览器请求
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            # 下载图片
            response = session.get(image_url, timeout=10, headers=headers)
            response.raise_for_status()
            
            # 检查内容类型是否为图片
            content_type = response.headers.get('content-type', '').lower()
            if not content_type.startswith('image/'):
                log_and_raise_error(
                    ValueError,
                    f"URL不是有效的图片: {image_url}, 内容类型: {content_type}",
                    {"url": image_url, "content_type": content_type}
                )
            
            # 处理图片数据
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
            _LOGGER.error("下载图片失败: %s, 错误: %s", image_url, ex)
            log_and_raise_error(
                NetworkError,
                f"下载图片失败: {image_url}",
                {"url": image_url, "error": str(ex)}
            )
    
    def _read_local_image_as_base64(self, image_path: str) -> str:
        """读取本地图片并转换为base64编码"""
        try:
            # 检查文件是否存在
            if not os.path.exists(image_path):
                _LOGGER.error("图片文件不存在: %s", image_path)
                log_and_raise_error(
                    ImageNotFoundError,
                    f"图片文件不存在: {image_path}",
                    {"path": image_path}
                )
            
            # 检查是否为文件
            if not os.path.isfile(image_path):
                _LOGGER.error("路径不是文件: %s", image_path)
                log_and_raise_error(
                    ImageNotFoundError,
                    f"路径不是文件: {image_path}",
                    {"path": image_path}
                )
            
            # 检查文件扩展名
            file_ext = os.path.splitext(image_path)[1].lower()
            if file_ext not in SUPPORTED_IMAGE_FORMATS:
                _LOGGER.error("不支持的图片格式: %s", file_ext)
                log_and_raise_error(
                    ImageNotFoundError,
                    f"不支持的图片格式: {file_ext}",
                    {"path": image_path, "supported_formats": SUPPORTED_IMAGE_FORMATS}
                )
            
            # 检查文件大小
            file_size = os.path.getsize(image_path)
            if file_size > MAX_IMAGE_SIZE:
                _LOGGER.error("图片文件过大: %s, 大小: %d 字节", image_path, file_size)
                log_and_raise_error(
                    ImageNotFoundError,
                    f"图片文件过大: {image_path}",
                    {"path": image_path, "size": file_size, "max_size": f"{MAX_IMAGE_SIZE // (1024*1024)}MB"}
                )
            
            # 读取文件内容
            with open(image_path, "rb") as img_file:
                image_data = img_file.read()
            
            # 处理图片数据
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
        except Exception as ex:
            _LOGGER.error("读取图片文件失败: %s, 错误: %s", image_path, ex)
            log_and_raise_error(
                ImageNotFoundError,
                f"读取图片文件失败: {image_path}",
                {"path": image_path, "error": str(ex)}
            )
    
    def _process_uploaded_image_as_base64(self, image_file: str) -> str:
        """处理上传的图片文件并转换为base64编码"""
        try:
            # image_file 应该是 base64 编码的字符串或文件对象
            if isinstance(image_file, str):
                # 检查是否已经是 base64 编码
                if image_file.startswith('data:image'):
                    # 处理 data URL 格式
                    _LOGGER.debug("处理 data URL 格式图片")
                    try:
                        header, encoded = image_file.split(',', 1)
                        _LOGGER.debug("成功解析 data URL 格式图片，头部: %s", header)
                        
                        # 解码base64并重新处理
                        image_data = base64.b64decode(encoded)
                        processed_image = self._process_image_data(image_data)
                        return base64.b64encode(processed_image).decode("utf-8")
                    except ValueError:
                        _LOGGER.error("无效的 data URL 格式")
                        log_and_raise_error(
                            ImageNotFoundError,
                            "无效的 data URL 格式",
                            {"data_url_length": len(image_file)}
                        )
                else:
                    # 假设已经是 base64 编码
                    _LOGGER.debug("使用 base64 编码图片，长度: %d", len(image_file))
                    
                    # 解码base64并重新处理
                    try:
                        image_data = base64.b64decode(image_file)
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
                # 如果是文件对象，读取并转换为 base64
                _LOGGER.debug("处理文件对象")
                image_data = image_file.read()
                
                # 处理图片数据
                processed_image = self._process_image_data(image_data)
                encoded_image = base64.b64encode(processed_image).decode("utf-8")
                
                _LOGGER.debug("成功读取上传的图片文件，大小: %d 字节", len(encoded_image))
                return encoded_image
                
        except Exception as ex:
            _LOGGER.error("处理上传的图片文件失败: %s", ex)
            log_and_raise_error(
                ImageNotFoundError,
                f"处理上传的图片文件失败",
                {"error": str(ex), "error_type": type(ex).__name__}
            )

    def search_faces(
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
        _LOGGER.info(
            "开始搜索人脸: image_url=%s, image_path=%s, image_file is not None: %s, max_face_num=%d, min_face_size=%d, max_user_num=%d, quality_control=%d, need_rotate_check=%d, face_match_threshold=%.2f",
            image_url, image_path, image_file is not None, max_face_num, min_face_size, max_user_num, quality_control, need_rotate_check, face_match_threshold
        )
        
        # 验证参数
        if not group_ids:
            _LOGGER.warning("未提供人员库ID，搜索可能失败")
        
        # 定义API调用函数
        def api_call():
            # 生成请求ID
            request_id = str(uuid.uuid4())
            start_time = time.time()
            
            try:
                # 获取图片数据
                image = self._get_image_base64(image_url, image_path, image_file)
                
                # 创建请求
                req = models.SearchFacesRequest()
                params = {
                    "NeedPersonInfo": 1,
                    "Image": image,
                    "MaxFaceNum": max_face_num,
                    "MinFaceSize": min_face_size,
                    "MaxPersonNum": max_user_num,
                    "QualityControl": quality_control,
                    "NeedRotateCheck": need_rotate_check,
                    "FaceMatchThreshold": face_match_threshold,
                    "GroupIds": group_ids
                }
                
                # 记录请求日志
                self._log_request("人脸搜索", params)
                
                req.from_json_string(json.dumps(params))
                
                # 发送请求
                _LOGGER.debug("发送人脸搜索请求")
                resp = self.client.SearchFaces(req)
                
                # 计算请求耗时
                duration = time.time() - start_time
                
                # 记录响应日志
                self._log_response("人脸搜索", request_id, resp, duration)
                
                # 解析响应
                results = []
                if getattr(resp, "Results", []):
                    _LOGGER.info("检测到 %d 个人脸", len(resp.Results))
                    for result in resp.Results:
                        face_result = {
                            "face_id": getattr(result, "FaceId", None),
                            "candidates": []
                        }
                        
                        if result.Candidates:
                            face_id = getattr(result, "FaceId", "未知")
                            _LOGGER.debug("人脸 %s 有 %d 个候选匹配", face_id, len(result.Candidates))
                            for candidate in result.Candidates:
                                candidate_info = {
                                    "person_id": candidate.PersonId,
                                    "person_name": candidate.PersonName,
                                    "score": candidate.Score,
                                    "person_tag": getattr(candidate, "PersonTag", None)
                                }
                                face_result["candidates"].append(candidate_info)
                                _LOGGER.debug(
                                    "候选匹配: person_id=%s, person_name=%s, score=%.2f, person_tag=%s",
                                    candidate.PersonId, candidate.PersonName, candidate.Score, getattr(candidate, "PersonTag", None)
                                )
                        
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
                # 计算请求耗时
                duration = time.time() - start_time
                
                # 记录错误日志
                self._log_error("人脸搜索", request_id, ex, duration)
                
                # 不抛出异常，而是返回包含错误信息的结构化结果
                error_code = None
                error_message = str(ex)
                
                # 如果是腾讯云API异常，提取错误码和消息
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
        
        # 执行带重试的API调用
        return self._execute_with_retry(api_call, "人脸搜索")

    def detect_faces(
        self,
        image_url: str = None,
        image_path: str = None,
        image_file: str = None,
        max_face_num: int = 1,
        min_face_size: int = 34,
        need_rotate_check: int = 1
    ) -> Dict[str, Any]:
        """检测人脸"""
        _LOGGER.info(
            "开始检测人脸: max_face_num=%d, min_face_size=%d, need_rotate_check=%d",
            max_face_num, min_face_size, need_rotate_check
        )
        
        # 定义API调用函数
        def api_call():
            # 生成请求ID
            request_id = str(uuid.uuid4())
            start_time = time.time()
            
            try:
                # 获取图片数据
                image = self._get_image_base64(image_url, image_path, image_file)
                
                # 创建请求
                req = models.DetectFaceRequest()
                params = {
                    "Image": image,
                    "MaxFaceNum": max_face_num,
                    "MinFaceSize": min_face_size,
                    "NeedRotateCheck": need_rotate_check
                }
                
                # 记录请求日志
                self._log_request("人脸检测", params)
                
                req.from_json_string(json.dumps(params))
                
                # 发送请求
                _LOGGER.debug("发送人脸检测请求")
                resp = self.client.DetectFace(req)
                
                # 计算请求耗时
                duration = time.time() - start_time
                
                # 记录响应日志
                self._log_response("人脸检测", request_id, resp, duration)
                
                # 解析响应
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
                # 计算请求耗时
                duration = time.time() - start_time
                
                # 记录错误日志
                self._log_error("人脸检测", request_id, ex, duration)
                
                # 不抛出异常，而是返回包含错误信息的结构化结果
                error_code = None
                error_message = str(ex)
                
                # 如果是腾讯云API异常，提取错误码和消息
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
        
        # 执行带重试的API调用
        return self._execute_with_retry(api_call, "人脸检测")

    def get_face_attributes(
        self,
        image_url: str = None,
        image_path: str = None,
        image_file: str = None,
        max_face_num: int = 1,
        need_rotate_check: int = 1
    ) -> Dict[str, Any]:
        """获取人脸属性"""
        _LOGGER.info(
            "开始获取人脸属性: max_face_num=%d, need_rotate_check=%d",
            max_face_num, need_rotate_check
        )
        
        # 定义API调用函数
        def api_call():
            # 生成请求ID
            request_id = str(uuid.uuid4())
            start_time = time.time()
            
            try:
                # 获取图片数据
                image = self._get_image_base64(image_url, image_path, image_file)
                
                # 创建请求
                req = models.DetectFaceRequest()
                params = {
                    "Image": image,
                    "MaxFaceNum": max_face_num,
                    "NeedRotateCheck": need_rotate_check
                }
                
                # 记录请求日志
                self._log_request("获取人脸属性", params)
                
                req.from_json_string(json.dumps(params))
                
                # 发送请求
                _LOGGER.debug("发送获取人脸属性请求")
                resp = self.client.DetectFace(req)
                
                # 计算请求耗时
                duration = time.time() - start_time
                
                # 记录响应日志
                self._log_response("获取人脸属性", request_id, resp, duration)
                
                # 解析响应
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
                # 计算请求耗时
                duration = time.time() - start_time
                
                # 记录错误日志
                self._log_error("获取人脸属性", request_id, ex, duration)
                
                # 不抛出异常，而是返回包含错误信息的结构化结果
                error_code = None
                error_message = str(ex)
                
                # 如果是腾讯云API异常，提取错误码和消息
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
        
        # 执行带重试的API调用
        return self._execute_with_retry(api_call, "获取人脸属性")
    
    def get_group_info(self, group_id: str) -> Dict[str, Any]:
        """获取人员库信息"""
        _LOGGER.info("开始获取人员库信息: group_id=%s", group_id)

        def api_call():
            request_id = str(uuid.uuid4())
            start_time = time.time()
            try:
                req = models.GetGroupInfoRequest()
                params = {"GroupId": group_id}
                self._log_request("获取人员库信息", params)
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

    def _test_api_connection(self, group_id: str) -> bool:
        """测试API连接"""
        try:
            _LOGGER.info("开始测试API连接: group_id=%s", group_id)
            self.get_group_info(group_id)
            _LOGGER.info("API连接测试成功")
            return True
        except Exception as ex:
            _LOGGER.error("API连接测试失败: %s", ex, exc_info=True)
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
                self._log_request("获取人员列表", params)
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

    def _execute_with_retry(self, api_call: Callable, operation_name: str) -> Any:
        """执行带重试的API调用"""
        last_exception = None
        
        for attempt in range(self.retry_config.max_retries):
            try:
                if attempt > 0:
                    # 计算重试延迟
                    delay = self._calculate_retry_delay(attempt)
                    _LOGGER.info("重试第 %d 次%s，延迟 %.2f 秒", attempt + 1, operation_name, delay)
                    time.sleep(delay)
                
                # 执行API调用
                return api_call()
                
            except TencentCloudSDKException as ex:
                last_exception = ex
                _LOGGER.warning("%s失败 (尝试 %d/%d): %s", operation_name, attempt + 1, self.retry_config.max_retries, ex)
                
                # 检查是否应该重试
                if not self._should_retry(ex):
                    _LOGGER.error("遇到不可重试的错误: %s", ex.code)
                    self._handle_error(ex)
                    break
                    
            except Exception as ex:
                last_exception = ex
                _LOGGER.warning("%s失败 (尝试 %d/%d): %s", operation_name, attempt + 1, self.retry_config.max_retries, ex)
        
        # 所有重试都失败后，抛出最后一个异常
        if last_exception:
            if isinstance(last_exception, TencentCloudSDKException):
                self._handle_error(last_exception)
            else:
                _LOGGER.error("%s最终失败: %s", operation_name, last_exception, exc_info=True)
                log_and_raise_error(
                    RuntimeError,
                    f"{operation_name}失败: {str(last_exception)}",
                    {"error": str(last_exception), "error_type": type(last_exception).__name__}
                )
    
    def _calculate_retry_delay(self, attempt: int) -> float:
        """计算重试延迟时间"""
        # 指数退避算法
        delay = self.retry_config.initial_delay * (
            self.retry_config.backoff_factor ** (attempt - 1)
        )
        
        # 限制最大延迟
        delay = min(delay, self.retry_config.max_delay)
        
        # 添加抖动，避免多个客户端同时重试
        jitter = delay * self.retry_config.jitter
        delay = delay + random.uniform(-jitter, jitter)
        
        # 确保延迟不为负数
        return max(0, delay)
    
    def _should_retry(self, ex: TencentCloudSDKException) -> bool:
        """判断是否应该重试"""
        # 如果错误码在不可重试的错误列表中，则不重试
        if ex.code in NON_RETRYABLE_ERRORS:
            return False
        
        # 如果是速率限制错误，但已经是最后一次尝试，则不重试
        if ex.code in RATE_LIMIT_ERRORS:
            return True
        
        # 如果是网络错误，则重试
        if ex.code in NETWORK_ERRORS:
            return True
        
        # 默认情况下，其他错误都重试
        return True
    
    def _is_valid_url(self, url: str) -> bool:
        """验证URL格式是否有效"""
        url_pattern = re.compile(
            r'^https?://'  # http:// 或 https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # 域名
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP地址
            r'(?::\d+)?'  # 可选端口
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return url_pattern.match(url) is not None
    
    def _process_image_data(self, image_data: bytes) -> bytes:
        """处理图片数据，包括压缩和格式转换"""
        try:
            # 检查图片大小
            if len(image_data) > MAX_IMAGE_SIZE:
                _LOGGER.warning("图片大小超过限制，尝试压缩: %d 字节", len(image_data))
                image_data = self._compress_image(image_data)
            
            # 尝试使用PIL处理图片
            try:
                from PIL import Image
                
                # 将字节数据转换为PIL图像对象
                img = Image.open(io.BytesIO(image_data))
                
                # 检查图片尺寸
                width, height = img.size
                if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                    _LOGGER.warning("图片尺寸过大，尝试缩放: %dx%d", width, height)
                    
                    # 计算缩放比例
                    scale = min(MAX_IMAGE_DIMENSION / width, MAX_IMAGE_DIMENSION / height)
                    new_width = int(width * scale)
                    new_height = int(height * scale)
                    
                    # 缩放图片
                    img = img.resize((new_width, new_height), Image.LANCZOS)
                    
                    # 将处理后的图片转换回字节数据
                    output = io.BytesIO()
                    img.save(output, format='JPEG', quality=IMAGE_COMPRESSION_QUALITY)
                    image_data = output.getvalue()
                    
                    _LOGGER.info("图片缩放完成: %dx%d -> %dx%d", width, height, new_width, new_height)
                
                # 如果图片不是JPEG格式，转换为JPEG以减少大小
                if img.format != 'JPEG':
                    _LOGGER.debug("转换图片格式为JPEG: %s", img.format)
                    output = io.BytesIO()
                    if img.mode == 'RGBA':
                        img = img.convert('RGB')
                    img.save(output, format='JPEG', quality=IMAGE_COMPRESSION_QUALITY)
                    image_data = output.getvalue()
                
            except ImportError:
                _LOGGER.warning("PIL库未安装，无法进行图片处理")
            except Exception as ex:
                _LOGGER.warning("图片处理失败: %s", ex)
            
            return image_data
            
        except Exception as ex:
            _LOGGER.error("处理图片数据失败: %s", ex, exc_info=True)
            # 如果处理失败，返回原始数据
            return image_data
    
    def _compress_image(self, image_data: bytes) -> bytes:
        """压缩图片数据"""
        try:
            from PIL import Image
            
            # 将字节数据转换为PIL图像对象
            img = Image.open(io.BytesIO(image_data))
            
            # 计算压缩比例
            original_size = len(image_data)
            target_size = MAX_IMAGE_SIZE * 0.8  # 目标大小为最大限制的80%
            quality = IMAGE_COMPRESSION_QUALITY
            
            # 逐步降低质量直到满足大小要求
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
            _LOGGER.warning("PIL库未安装，无法进行图片压缩")
            return image_data
        except Exception as ex:
            _LOGGER.error("图片压缩失败: %s", ex, exc_info=True)
            return image_data
    
    def _log_request(self, operation: str, params: Dict[str, Any]) -> None:
        """记录API请求日志"""
        if not ENABLE_REQUEST_LOGGING:
            return
        
        # 生成请求ID
        request_id = str(uuid.uuid4())
        
        # 记录请求基本信息
        _LOGGER.info(
            "API请求: operation=%s, request_id=%s, params_count=%d",
            operation, request_id, len(params)
        )
        
        # 记录请求参数（截断过长的参数）
        if ENABLE_PERFORMANCE_LOGGING:
            safe_params = {}
            for key, value in params.items():
                if key == "Image":
                    # 图片参数只记录长度，不记录内容
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
        
        # 记录响应基本信息
        _LOGGER.info(
            "API响应: operation=%s, request_id=%s, duration=%.3fs, response_type=%s",
            operation, request_id, duration, type(response).__name__
        )
        
        # 记录性能指标
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
        
        # 记录响应详情（截断过长的响应）
        try:
            if hasattr(response, "__dict__"):
                # 如果是对象，尝试转换为字典
                response_dict = {}
                for attr in dir(response):
                    if not attr.startswith("_") and not callable(getattr(response, attr)):
                        response_dict[attr] = getattr(response, attr)
                
                response_str = json.dumps(response_dict, ensure_ascii=False, default=str)
            else:
                # 如果不是对象，直接转换为字符串
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
        error_msg = str(error)
        
        # 记录错误基本信息
        _LOGGER.error(
            "API错误: operation=%s, request_id=%s, duration=%.3fs, error_type=%s, error_msg=%s",
            operation, request_id, duration, error_type, error_msg
        )
        
        # 记录错误详情
        if isinstance(error, TencentCloudSDKException):
            _LOGGER.error(
                "腾讯云API错误详情: operation=%s, request_id=%s, code=%s, message=%s, request_id=%s",
                operation, request_id, getattr(error, "code", "未知"),
                getattr(error, "message", "未知"),
                getattr(error, "request_id", "未知")
            )
        
        # 记录堆栈跟踪
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "API错误堆栈跟踪: operation=%s, request_id=%s",
                operation, request_id, exc_info=True
            )