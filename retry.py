"""重试与执行辅助模块。

将原 ``tencent_cloud_client.py`` 中的重试逻辑抽离出来，便于复用与测试。
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable, Optional

from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)

from .errors import handle_api_error, log_and_raise_error, ApiError

_LOGGER = logging.getLogger(__name__)

# 重试默认参数
MAX_ATTEMPTS = 3
INITIAL_RETRY_DELAY = 1.0
MAX_RETRY_DELAY = 30.0
RETRY_BACKOFF_FACTOR = 2.0
RETRY_JITTER = 0.1

# 不可重试的错误码（业务错误，重试无意义）
NON_RETRYABLE_ERRORS = frozenset({
    "AuthFailure",
    "InvalidParameter",
    "InvalidParameterValue",
    "ResourceNotFound",
    "ResourceNotFoundInUse",
    "FailedOperation.PersonExist",
    "FailedOperation.PersonNotExist",
    "FailedOperation.FaceExist",
    "FailedOperation.FaceNotExist",
    "FailedOperation.GroupExist",
    "FailedOperation.GroupNotExist",
})

# 速率限制类错误码（可重试）
RATE_LIMIT_ERRORS = frozenset({
    "RequestLimitExceeded",
    "RequestQuotaExceeded",
    "LimitExceeded",
})

# 网络/服务端临时错误码（可重试）
NETWORK_ERRORS = frozenset({
    "ResourceUnavailable.NetworkError",
    "ResourceUnavailable.ServiceTimeout",
    "InternalError",
    "FailedOperation.RequestTimeout",
})


class RetryConfig:
    """重试配置。"""

    def __init__(
        self,
        max_attempts: int = MAX_ATTEMPTS,
        initial_delay: float = INITIAL_RETRY_DELAY,
        max_delay: float = MAX_RETRY_DELAY,
        backoff_factor: float = RETRY_BACKOFF_FACTOR,
        jitter: float = RETRY_JITTER,
    ) -> None:
        self.max_attempts = max(max_attempts, 1)
        self.initial_delay = max(initial_delay, 0.0)
        self.max_delay = max(max_delay, self.initial_delay)
        self.backoff_factor = max(backoff_factor, 1.0)
        self.jitter = max(0.0, min(jitter, 1.0))


def calculate_retry_delay(attempt: int, config: RetryConfig) -> float:
    """计算第 ``attempt`` 次重试（从 1 开始）的延迟时间。"""
    delay = config.initial_delay * (config.backoff_factor ** (attempt - 1))
    delay = min(delay, config.max_delay)
    jitter = delay * config.jitter
    delay += random.uniform(-jitter, jitter)
    return max(0.0, delay)


def should_retry(exception: TencentCloudSDKException) -> bool:
    """判断 SDK 异常是否可重试。"""
    code = getattr(exception, "code", "") or ""

    # 精确匹配不可重试
    if code in NON_RETRYABLE_ERRORS:
        return False

    # 精确匹配可重试
    if code in RATE_LIMIT_ERRORS or code in NETWORK_ERRORS:
        return True

    # 前缀匹配：AuthFailure.* / InvalidParameter.* / ResourceNotFound.* 不可重试
    for prefix in ("AuthFailure", "InvalidParameter", "ResourceNotFound"):
        if code.startswith(prefix):
            return False

    # 其它未知错误默认可重试（服务端临时问题居多）
    return True


def execute_with_retry(
    api_call: Callable[[], Any],
    operation_name: str,
    config: Optional[RetryConfig] = None,
    sanitize_error: Optional[Callable[[str], str]] = None,
) -> Any:
    """执行带重试的 API 调用。

    ``api_call`` 应返回业务结果字典（成功）或抛出 ``TencentCloudSDKException``
    /其它异常。当 ``api_call`` 内部已经把异常转化为 ``{success: False}`` 结果时，
    本函数不会重试——重试仅针对抛出的异常。

    Args:
        api_call: 实际的 API 调用函数。
        operation_name: 操作名称，用于日志。
        config: 重试配置，默认 ``RetryConfig()``。
        sanitize_error: 可选的错误信息脱敏函数。
    """
    cfg = config or RetryConfig()
    sanitize = sanitize_error or (lambda s: s)
    last_exception: Optional[Exception] = None

    for attempt in range(cfg.max_attempts):
        try:
            if attempt > 0:
                delay = calculate_retry_delay(attempt, cfg)
                _LOGGER.info(
                    "重试第 %d 次 %s，延迟 %.2f 秒", attempt, operation_name, delay
                )
                time.sleep(delay)
            return api_call()
        except TencentCloudSDKException as ex:
            last_exception = ex
            _LOGGER.warning(
                "%s 失败 (尝试 %d/%d): %s",
                operation_name, attempt + 1, cfg.max_attempts, ex.code,
            )
            if not should_retry(ex):
                _LOGGER.error("遇到不可重试的错误: %s", ex.code)
                break
        except Exception as ex:  # noqa: BLE001 — 顶层兜底
            last_exception = ex
            _LOGGER.warning(
                "%s 失败 (尝试 %d/%d): %s",
                operation_name, attempt + 1, cfg.max_attempts, sanitize(str(ex)),
            )

    # 所有尝试均失败
    if isinstance(last_exception, TencentCloudSDKException):
        handle_api_error(last_exception.code, last_exception.message)
        # handle_api_error 总会抛出，这里保险返回
        raise ApiError(f"{operation_name} 失败: {last_exception.code}")

    if last_exception is not None:
        log_and_raise_error(
            ApiError,
            f"{operation_name} 失败: {last_exception}",
            {"error": str(last_exception), "error_type": type(last_exception).__name__},
        )

    # 理论不可达
    raise ApiError(f"{operation_name} 失败: 未知错误")
