"""错误处理模块"""

import logging
from typing import Dict, Any, Optional

from homeassistant.exceptions import HomeAssistantError

from .const import CONF_SECRET_ID, CONF_SECRET_KEY, CONF_REGION, CONF_PERSON_GROUP_ID

_LOGGER = logging.getLogger(__name__)

ERROR_MESSAGES = {
    "zh_CN": {
        "missing_config": "缺少必需的配置项: {key}",
        "invalid_secret_id": "Secret ID 必须是非空字符串，且应以 AKID 开头",
        "invalid_secret_key": "Secret Key 必须是非空字符串",
        "invalid_region": "区域必须是非空字符串，且为有效的腾讯云区域",
        "invalid_person_group_id": "人员库ID必须是非空字符串，只能包含字母、数字、连字符和下划线",

        "image_not_found": "图片未找到: {path}",
        "image_too_large": "图片文件过大: {path}, 大小: {size} 字节，最大支持: {max_size}",
        "image_format_not_supported": "不支持的图片格式: {format}, 支持的格式: {supported_formats}",
        "image_decode_failed": "图片解码失败，请确保图片格式正确",
        "image_download_timeout": "下载图片超时: {url}",
        "image_download_error": "下载图片失败: {url}, 错误: {error}",
        "invalid_image_url": "无效的图片URL: {url}",
        "permission_denied": "没有权限读取图片文件: {path}",

        "face_not_detected": "未检测到人脸，请确保图片中包含清晰的人脸",
        "face_too_small": "人脸太小，请使用包含更大人脸的图片",
        "face_quality_poor": "人脸质量较差，请使用更清晰的图片",

        "api_error": "API调用失败: {code} - {message}",
        "person_not_found": "人员未找到: {person_id}",
        "group_not_found": "人员库未找到: {group_id}",
        "face_not_found": "人脸未找到: {face_id}",

        "network_error": "网络连接错误，请检查网络连接",
        "timeout_error": "请求超时，请稍后重试",

        "auth_failure": "认证失败，请检查Secret ID和Secret Key是否正确",
        "auth_expired": "认证已过期，请更新凭证",

        "rate_limit_exceeded": "API调用频率超限，请稍后重试",
        "quota_exceeded": "API调用配额已用完，请等待配额重置或升级套餐",

        "unknown_error": "未知错误: {message}",
        "invalid_parameter": "无效参数: {parameter}",
        "person_exist_in_group": "人员已存在: {code}",
        "group_exist_in_group": "人员库已存在: {code}",
        "delete_face_num_exceed": "删除人脸数量超出限制，人员至少需保留一张人脸",
        "resource_unavailable": "服务不可用: {code}",
    },
    "en_US": {
        "missing_config": "Missing required configuration: {key}",
        "invalid_secret_id": "Secret ID must be a non-empty string starting with AKID",
        "invalid_secret_key": "Secret Key must be a non-empty string",
        "invalid_region": "Region must be a non-empty string and a valid Tencent Cloud region",
        "invalid_person_group_id": "Person Group ID must be a non-empty string containing only letters, numbers, hyphens, and underscores",

        "image_not_found": "Image not found: {path}",
        "image_too_large": "Image file too large: {path}, size: {size} bytes, maximum supported: {max_size}",
        "image_format_not_supported": "Unsupported image format: {format}, supported formats: {supported_formats}",
        "image_decode_failed": "Image decode failed, please ensure the image format is correct",
        "image_download_timeout": "Image download timeout: {url}",
        "image_download_error": "Image download failed: {url}, error: {error}",
        "invalid_image_url": "Invalid image URL: {url}",
        "permission_denied": "Permission denied when reading image file: {path}",

        "face_not_detected": "No face detected, please ensure the image contains clear faces",
        "face_too_small": "Face too small, please use an image with larger faces",
        "face_quality_poor": "Poor face quality, please use a clearer image",

        "api_error": "API call failed: {code} - {message}",
        "person_not_found": "Person not found: {person_id}",
        "group_not_found": "Person group not found: {group_id}",
        "face_not_found": "Face not found: {face_id}",

        "network_error": "Network connection error, please check your network connection",
        "timeout_error": "Request timeout, please try again later",

        "auth_failure": "Authentication failed, please check if Secret ID and Secret Key are correct",
        "auth_expired": "Authentication expired, please update credentials",

        "rate_limit_exceeded": "API call rate limit exceeded, please try again later",
        "quota_exceeded": "API call quota used up, please wait for quota reset or upgrade plan",

        "unknown_error": "Unknown error: {message}",
        "invalid_parameter": "Invalid parameter: {parameter}",
        "person_exist_in_group": "Person already exists: {code}",
        "group_exist_in_group": "Group already exists: {code}",
        "delete_face_num_exceed": "Delete face count exceeded; a person must keep at least one face",
        "resource_unavailable": "Service unavailable: {code}",
    }
}

ERROR_SOLUTIONS = {
    "zh_CN": {
        "missing_config": "请在配置中添加缺少的配置项",
        "invalid_secret_id": "请检查Secret ID格式，应以AKID开头",
        "invalid_secret_key": "请检查Secret Key格式，确保输入正确",
        "invalid_region": "请选择有效的腾讯云区域，如ap-shanghai",
        "invalid_person_group_id": "请使用字母、数字、连字符和下划线组合",

        "image_not_found": "请检查图片路径是否正确",
        "image_too_large": "请使用小于10MB的图片，或对图片进行压缩",
        "image_format_not_supported": "请将图片转换为JPG、PNG、BMP或GIF格式",
        "image_decode_failed": "请确保图片文件未损坏，并尝试重新保存",
        "image_download_timeout": "请检查网络连接，或尝试使用其他图片URL",
        "image_download_error": "请检查图片URL是否有效，或稍后重试",
        "invalid_image_url": "请提供有效的图片URL",
        "permission_denied": "请检查文件权限，或使用其他图片",

        "face_not_detected": "请使用包含清晰人脸的图片",
        "face_too_small": "请使用人脸更大的图片，或调整拍摄距离",
        "face_quality_poor": "请使用光线充足、对焦清晰的图片",

        "api_error": "请稍后重试，如果问题持续，请联系技术支持",
        "person_not_found": "请检查人员ID是否正确，或确保人员已添加到人员库",
        "group_not_found": "请检查人员库ID是否正确，或创建新的人员库",
        "face_not_found": "请检查人脸ID是否正确",

        "network_error": "请检查网络连接，确保网络通畅",
        "timeout_error": "请稍后重试，或在网络状况良好时使用",

        "auth_failure": "请检查Secret ID和Secret Key是否正确",
        "auth_expired": "请更新腾讯云凭证",

        "rate_limit_exceeded": "请降低调用频率，稍后重试",
        "quota_exceeded": "请等待配额重置，或升级腾讯云套餐",

        "unknown_error": "请记录错误信息并联系技术支持",
        "invalid_parameter": "请检查API调用参数是否正确",
    },
    "en_US": {
        "missing_config": "Please add the missing configuration item",
        "invalid_secret_id": "Please check the Secret ID format, it should start with AKID",
        "invalid_secret_key": "Please check the Secret Key format, ensure it's entered correctly",
        "invalid_region": "Please select a valid Tencent Cloud region, such as ap-shanghai",
        "invalid_person_group_id": "Please use a combination of letters, numbers, hyphens, and underscores",

        "image_not_found": "Please check if the image path is correct",
        "image_too_large": "Please use an image smaller than 10MB, or compress the image",
        "image_format_not_supported": "Please convert the image to JPG, PNG, BMP, or GIF format",
        "image_decode_failed": "Please ensure the image file is not corrupted and try saving it again",
        "image_download_timeout": "Please check your network connection, or try using a different image URL",
        "image_download_error": "Please check if the image URL is valid, or try again later",
        "invalid_image_url": "Please provide a valid image URL",
        "permission_denied": "Please check file permissions, or use a different image",

        "face_not_detected": "Please use an image that contains clear faces",
        "face_too_small": "Please use an image with larger faces, or adjust the shooting distance",
        "face_quality_poor": "Please use a well-lit and focused image",

        "api_error": "Please try again later, if the problem persists, please contact technical support",
        "person_not_found": "Please check if the person ID is correct, or ensure the person has been added to the person group",
        "group_not_found": "Please check if the person group ID is correct, or create a new person group",
        "face_not_found": "Please check if the face ID is correct",

        "network_error": "Please check your network connection, ensure it's working properly",
        "timeout_error": "Please try again later, or use when network conditions are good",

        "auth_failure": "Please check if Secret ID and Secret Key are correct",
        "auth_expired": "Please update Tencent Cloud credentials",

        "rate_limit_exceeded": "Please reduce call frequency and try again later",
        "quota_exceeded": "Please wait for quota reset, or upgrade Tencent Cloud plan",

        "unknown_error": "Please record the error information and contact technical support",
        "invalid_parameter": "Please check if the API call parameters are correct",
    }
}


class TencentFaceRecognitionError(HomeAssistantError):
    """腾讯云人脸识别基础错误类"""

    def __init__(
        self,
        message: str,
        error_key: Optional[str] = None,
        error_details: Optional[Dict[str, Any]] = None,
        locale: str = "zh_CN"
    ):
        super().__init__(message)
        self.error_key = error_key
        self.error_details = error_details or {}
        self.locale = locale

        self.localized_message = self._get_localized_message()
        self.solution = self._get_solution()

    def _get_localized_message(self) -> str:
        if not self.error_key:
            return str(self)

        messages = ERROR_MESSAGES.get(self.locale, ERROR_MESSAGES["zh_CN"])
        template = messages.get(self.error_key, str(self))

        try:
            return template.format(**self.error_details)
        except (KeyError, ValueError):
            return str(self)

    def _get_solution(self) -> str:
        if not self.error_key:
            return ""

        solutions = ERROR_SOLUTIONS.get(self.locale, ERROR_SOLUTIONS["zh_CN"])
        return solutions.get(self.error_key, "")


class InvalidConfigError(TencentFaceRecognitionError):
    """无效配置错误"""
    pass


class ApiError(TencentFaceRecognitionError):
    """API调用错误"""
    pass


class ImageNotFoundError(TencentFaceRecognitionError):
    """图片未找到错误"""
    pass


class FaceNotDetectedError(TencentFaceRecognitionError):
    """未检测到人脸错误"""
    pass


class PersonNotFoundError(TencentFaceRecognitionError):
    """人员未找到错误"""
    pass


class PersonGroupNotFoundError(TencentFaceRecognitionError):
    """人员库未找到错误"""
    pass


class FaceNotFoundError(TencentFaceRecognitionError):
    """人脸未找到错误"""
    pass


class NetworkError(TencentFaceRecognitionError):
    """网络错误"""
    pass


class AuthenticationError(TencentFaceRecognitionError):
    """认证错误"""
    pass


class RateLimitError(TencentFaceRecognitionError):
    """速率限制错误"""
    pass


class QuotaExceededError(TencentFaceRecognitionError):
    """配额超限错误"""
    pass


def handle_api_error(error_code: str, error_message: str) -> None:
    """处理API错误。

    先尝试精确匹配，再用前缀匹配，最后回退到通用 ``ApiError``。
    """
    # 真实错误码映射（腾讯云 IAI 文档 32808），key = code
    error_mapping = {
        # 认证 / 签名
        "AuthFailure.SignatureFailure": (AuthenticationError, "auth_failure"),
        "AuthFailure.SecretIdNotFound": (AuthenticationError, "auth_failure"),
        "AuthFailure.InvalidAuthorization": (AuthenticationError, "auth_failure"),
        # 图片相关
        "FailedOperation.ImageDecodeFailed": (ImageNotFoundError, "image_decode_failed"),
        "FailedOperation.ImageSizeExceed": (ImageNotFoundError, "image_too_large"),
        "FailedOperation.ImageResolutionExceed": (ImageNotFoundError, "image_too_large"),
        "FailedOperation.ImageResolutionTooSmall": (ImageNotFoundError, "face_too_small"),
        "FailedOperation.ImageDownloadError": (NetworkError, "image_download_error"),
        # 人脸检测
        "InvalidParameterValue.NoFaceInPhoto": (FaceNotDetectedError, "face_not_detected"),
        "FailedOperation.FaceSizeTooSmall": (FaceNotDetectedError, "face_too_small"),
        "FailedOperation.FaceQualityNotQualified": (FaceNotDetectedError, "face_quality_poor"),
        # 人员 / 人员库 / 人脸
        "InvalidParameterValue.PersonIdNotExist": (PersonNotFoundError, "person_not_found"),
        "ResourceNotFound.ErrorPersonNotExisted": (PersonNotFoundError, "person_not_found"),
        "InvalidParameterValue.PersonExistInGroup": (ApiError, "person_exist_in_group"),
        "InvalidParameterValue.PersonIdAlreadyExist": (ApiError, "person_exist_in_group"),
        "InvalidParameterValue.GroupIdNotExist": (PersonGroupNotFoundError, "group_not_found"),
        "InvalidParameterValue.GroupIdAlreadyExist": (ApiError, "group_exist_in_group"),
        "FailedOperation.GroupPersonMapNotExist": (FaceNotFoundError, "face_not_found"),
        "FailedOperation.DeleteFaceNumExceed": (ApiError, "delete_face_num_exceed"),
        # 配额 / 限流 / 计费
        "RequestLimitExceeded": (RateLimitError, "rate_limit_exceeded"),
        "FailedOperation.RequestLimitExceeded": (RateLimitError, "rate_limit_exceeded"),
        "LimitExceeded.ErrorFaceNumExceed": (QuotaExceededError, "quota_exceeded"),
        "ResourceUnavailable.InArrears": (QuotaExceededError, "quota_exceeded"),
        "ResourceUnavailable.LowBalance": (QuotaExceededError, "quota_exceeded"),
        "ResourceUnavailable.Freeze": (ApiError, "resource_unavailable"),
        "ResourceUnavailable.StopUsing": (ApiError, "resource_unavailable"),
        # 网络 / 服务
        "FailedOperation.RequestTimeout": (NetworkError, "timeout_error"),
        "FailedOperation.ServerError": (NetworkError, "network_error"),
        "FailedOperation.ConflictOperation": (ApiError, "api_error"),
        "FailedOperation.CreateFaceConcurrent": (ApiError, "api_error"),
        "InternalError": (NetworkError, "network_error"),
        "MissingParameter.ErrorParameterEmpty": (ApiError, "invalid_parameter"),
        "UnsupportedOperation.UnknowMethod": (ApiError, "invalid_parameter"),
    }

    error_class = None
    error_key = None

    if error_code in error_mapping:
        error_class, error_key = error_mapping[error_code]
    else:
        # 前缀兜底
        if error_code.startswith("AuthFailure"):
            error_class, error_key = AuthenticationError, "auth_failure"
        elif error_code.startswith("InvalidParameterValue.PersonId"):
            error_class, error_key = ApiError, "invalid_parameter"
        elif error_code.startswith("InvalidParameterValue.GroupId"):
            error_class, error_key = ApiError, "invalid_parameter"
        elif error_code.startswith("InvalidParameter") or error_code.startswith("MissingParameter"):
            error_class, error_key = ApiError, "invalid_parameter"
        elif error_code.startswith("ResourceNotFound"):
            error_class, error_key = ApiError, "api_error"
        elif error_code.startswith("LimitExceeded"):
            error_class, error_key = RateLimitError, "rate_limit_exceeded"
        elif error_code.startswith("RequestLimitExceeded"):
            error_class, error_key = RateLimitError, "rate_limit_exceeded"
        else:
            error_class, error_key = ApiError, "api_error"
        _LOGGER.debug("按前缀匹配错误码: %s -> %s/%s", error_code, error_class.__name__, error_key)

    if error_class is None:
        error_class, error_key = ApiError, "api_error"

    _LOGGER.error("腾讯云API错误: %s - %s", error_code, error_message)

    error_details = {
        "code": error_code,
        "message": error_message
    }

    raise error_class(
        f"{error_code}: {error_message}",
        error_key=error_key,
        error_details=error_details
    )


def log_and_raise_error(error_class, message: str, details: Dict[str, Any] = None, error_key: Optional[str] = None) -> None:
    """记录日志并抛出错误。

    ``error_class`` 必须是 ``TencentFaceRecognitionError``（或 ``HomeAssistantError``）
    的子类，以保证上层 ``except HomeAssistantError`` 能正确捕获。
    如果传入的 ``error_class`` 无法构造为带 ``error_key``/``error_details`` 的自定义错误
    （例如 ``ValueError``），则退化为抛出 ``ApiError``，避免异常类型不可控。
    """
    _LOGGER.error("%s: %s", error_class.__name__, message)

    try:
        raise error_class(
            message,
            error_key=error_key,
            error_details=details or {}
        )
    except TypeError:
        # error_class 不支持 error_key/error_details 关键字参数
        raise ApiError(
            message,
            error_key=error_key,
            error_details=details or {}
        ) from None


def validate_config(config: Dict[str, Any]) -> None:
    """验证配置"""
    required_keys = [CONF_SECRET_ID, CONF_SECRET_KEY]

    for key in required_keys:
        if not config.get(key):
            log_and_raise_error(
                InvalidConfigError,
                f"缺少必需的配置项: {key}",
                {"key": key},
                "missing_config"
            )

    secret_id = config.get(CONF_SECRET_ID)
    if not isinstance(secret_id, str) or len(secret_id.strip()) == 0:
        log_and_raise_error(
            InvalidConfigError,
            "Secret ID必须是非空字符串，且应以 AKID 开头",
            {"secret_id": "***"},
            "invalid_secret_id"
        )

    secret_key = config.get(CONF_SECRET_KEY)
    if not isinstance(secret_key, str) or len(secret_key.strip()) == 0:
        log_and_raise_error(
            InvalidConfigError,
            "Secret Key必须是非空字符串",
            {"secret_key": "***"},
            "invalid_secret_key"
        )

    region = config.get(CONF_REGION, "ap-shanghai")
    if not isinstance(region, str) or len(region.strip()) == 0:
        log_and_raise_error(
            InvalidConfigError,
            "区域必须是非空字符串，且为有效的腾讯云区域",
            {"region": str(region)},
            "invalid_region"
        )

    person_group_id = config.get(CONF_PERSON_GROUP_ID, "Hass")
    if not isinstance(person_group_id, str) or len(person_group_id.strip()) == 0:
        log_and_raise_error(
            InvalidConfigError,
            "人员库ID必须是非空字符串，只能包含字母、数字、连字符和下划线",
            {"person_group_id": str(person_group_id)},
            "invalid_person_group_id"
        )

    _LOGGER.debug("配置验证通过")
