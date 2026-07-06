"""图片处理模块。

负责从 URL / 本地路径 / 上传文件 / data URL 获取并编码图片为 base64，
并在需要时压缩、缩放、转码为 JPEG。原 ``tencent_cloud_client.py`` 中
分散的图片逻辑在此集中、简化。
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re
from functools import lru_cache
from typing import Optional

import requests

from .errors import ImageNotFoundError, NetworkError, log_and_raise_error

_LOGGER = logging.getLogger(__name__)

# 图片限制
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_IMAGE_DIMENSION = 4096
SUPPORTED_IMAGE_FORMATS = (".jpg", ".jpeg", ".png", ".bmp", ".gif")
IMAGE_COMPRESSION_QUALITY = 85
COMPRESS_TARGET_RATIO = 0.8  # 压缩目标 = MAX_IMAGE_SIZE * 0.8

_URL_PATTERN = re.compile(
    r"^https?://"
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
    r"localhost|"
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
    r"(?::\d+)?"
    r"(?:/?|[/?]\S*)$",
    re.IGNORECASE,
)


def is_valid_url(url: str) -> bool:
    """验证 URL 格式是否有效。"""
    return bool(_URL_PATTERN.match(url or ""))


def _pil_available() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def _open_image(data: bytes):
    """打开图片，返回 PIL Image 对象；PIL 不可用时抛出 ImageNotFoundError。"""
    try:
        from PIL import Image
    except ImportError as ex:
        _LOGGER.warning(
            "PIL库(Pillow)未安装，无法进行图片处理。建议安装: pip install Pillow>=10.0.0"
        )
        raise ImageNotFoundError(
            "Pillow 未安装，无法处理图片",
            error_key="image_decode_failed",
            error_details={"reason": "pillow_missing"},
        ) from ex
    return Image.open(io.BytesIO(data))


def process_image_data(image_data: bytes) -> bytes:
    """处理图片数据：尺寸校验、缩放、格式转换、压缩。

    PIL 不可用时直接返回原始数据（但仍受调用方的尺寸约束）。
    """
    if not image_data:
        return image_data

    # 超过限制先压缩
    if len(image_data) > MAX_IMAGE_SIZE:
        _LOGGER.warning("图片大小超过限制，尝试压缩: %d 字节", len(image_data))

    if not _pil_available():
        # 无法压缩时只能按原样返回，由服务端兜底校验
        return image_data

    try:
        img = _open_image(image_data)
        width, height = img.size

        # 尺寸过大则缩放
        if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
            _LOGGER.warning("图片尺寸过大，尝试缩放: %dx%d", width, height)
            scale = min(
                MAX_IMAGE_DIMENSION / width,
                MAX_IMAGE_DIMENSION / height,
            )
            new_size = (int(width * scale), int(height * scale))
            img = img.resize(new_size, _get_resample_filter())
            _LOGGER.info(
                "图片缩放完成: %dx%d -> %dx%d",
                width, height, new_size[0], new_size[1],
            )

        # 统一转 JPEG
        output = io.BytesIO()
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        img.save(output, format="JPEG", quality=IMAGE_COMPRESSION_QUALITY, optimize=True)
        result = output.getvalue()

        # 仍然过大则进一步压缩
        if len(result) > MAX_IMAGE_SIZE:
            result = _compress_to_fit(img, MAX_IMAGE_SIZE * COMPRESS_TARGET_RATIO)

        _LOGGER.debug("图片处理完成: %d -> %d 字节", len(image_data), len(result))
        return result

    except ImageNotFoundError:
        raise
    except Exception as ex:  # noqa: BLE001
        _LOGGER.warning("图片处理失败，使用原始数据: %s", ex)
        return image_data


def _get_resample_filter():
    from PIL import Image
    # LANCZOS 在不同 Pillow 版本中名称一致
    return Image.LANCZOS


def _compress_to_fit(img, target_size: int) -> bytes:
    """逐步降低质量以将图片压缩到目标大小。"""
    quality = IMAGE_COMPRESSION_QUALITY
    last_data = b""
    while quality >= 30:
        output = io.BytesIO()
        out = img
        if out.mode in ("RGBA", "LA", "P"):
            out = out.convert("RGB")
        out.save(output, format="JPEG", quality=quality, optimize=True)
        data = output.getvalue()
        last_data = data
        if len(data) <= target_size:
            _LOGGER.info(
                "图片压缩完成，最终质量: %d, 大小: %d 字节", quality, len(data)
            )
            return data
        quality -= 5
    _LOGGER.warning("图片压缩已达最低质量，仍超过目标大小: %d 字节", len(last_data))
    return last_data


def download_image_as_base64(image_url: str, session: Optional[requests.Session] = None) -> str:
    """下载图片并转换为 base64 编码。"""
    _LOGGER.debug("开始下载图片: %s", image_url)

    if not is_valid_url(image_url):
        log_and_raise_error(
            ImageNotFoundError,
            f"无效的图片URL: {image_url}",
            {"url": image_url},
        )

    sess = session or requests
    headers = {"User-Agent": "Mozilla/5.0 (HomeAssistant TencentFaceRecognition)"}

    try:
        response = sess.get(image_url, timeout=15, headers=headers)
        response.raise_for_status()
    except requests.exceptions.Timeout as ex:
        log_and_raise_error(
            NetworkError,
            f"下载图片超时: {image_url}",
            {"url": image_url, "error": "timeout"},
        )
        raise  # log_and_raise_error 抛出，此行仅为类型提示
    except requests.exceptions.ConnectionError as ex:
        log_and_raise_error(
            NetworkError,
            f"下载图片连接错误: {image_url}",
            {"url": image_url, "error": "connection_error"},
        )
        raise
    except requests.exceptions.RequestException as ex:
        log_and_raise_error(
            NetworkError,
            f"下载图片失败: {image_url}",
            {"url": image_url, "error": str(ex)},
        )
        raise

    content_type = response.headers.get("content-type", "").lower()
    if content_type and not content_type.startswith("image/"):
        log_and_raise_error(
            ImageNotFoundError,
            f"URL不是有效的图片: {image_url}, 内容类型: {content_type}",
            {"url": image_url, "content_type": content_type},
        )

    image_data = process_image_data(response.content)
    return base64.b64encode(image_data).decode("utf-8")


def read_local_image_as_base64(image_path: str) -> str:
    """读取本地图片并转换为 base64 编码。"""
    if not os.path.exists(image_path):
        log_and_raise_error(
            ImageNotFoundError,
            f"图片文件不存在: {image_path}",
            {"path": image_path},
        )
    if not os.path.isfile(image_path):
        log_and_raise_error(
            ImageNotFoundError,
            f"路径不是文件: {image_path}",
            {"path": image_path},
        )

    file_ext = os.path.splitext(image_path)[1].lower()
    if file_ext not in SUPPORTED_IMAGE_FORMATS:
        log_and_raise_error(
            ImageNotFoundError,
            f"不支持的图片格式: {file_ext}",
            {"path": image_path, "supported_formats": list(SUPPORTED_IMAGE_FORMATS)},
        )

    file_size = os.path.getsize(image_path)
    if file_size > MAX_IMAGE_SIZE:
        log_and_raise_error(
            ImageNotFoundError,
            f"图片文件过大: {image_path}",
            {
                "path": image_path,
                "size": file_size,
                "max_size": f"{MAX_IMAGE_SIZE // (1024 * 1024)}MB",
            },
        )

    try:
        with open(image_path, "rb") as img_file:
            image_data = img_file.read()
    except PermissionError:
        log_and_raise_error(
            ImageNotFoundError,
            f"没有权限读取图片文件: {image_path}",
            {"path": image_path, "error": "permission_denied"},
        )
        raise

    processed = process_image_data(image_data)
    return base64.b64encode(processed).decode("utf-8")


def encode_uploaded_image_as_base64(image_file) -> str:
    """处理上传的图片（data URL / base64 字符串 / 文件对象）并返回 base64。"""
    if isinstance(image_file, str):
        if image_file.startswith("data:image"):
            _LOGGER.debug("处理 data URL 格式图片")
            try:
                _, encoded = image_file.split(",", 1)
                image_data = base64.b64decode(encoded)
            except ValueError:
                log_and_raise_error(
                    ImageNotFoundError,
                    "无效的 data URL 格式",
                    {"data_url_length": len(image_file)},
                )
                raise
            processed = process_image_data(image_data)
            return base64.b64encode(processed).decode("utf-8")

        # 视为 base64 字符串
        _LOGGER.debug("使用 base64 编码图片，长度: %d", len(image_file))
        try:
            image_data = base64.b64decode(image_file)
        except Exception as ex:  # noqa: BLE001
            log_and_raise_error(
                ImageNotFoundError,
                "base64 解码失败",
                {"error": str(ex), "data_length": len(image_file)},
            )
            raise
        processed = process_image_data(image_data)
        return base64.b64encode(processed).decode("utf-8")

    # 文件对象
    _LOGGER.debug("处理文件对象")
    image_data = image_file.read()
    processed = process_image_data(image_data)
    return base64.b64encode(processed).decode("utf-8")


def get_image_base64(
    image_url: Optional[str] = None,
    image_path: Optional[str] = None,
    image_file=None,
    session: Optional[requests.Session] = None,
) -> str:
    """根据提供的来源获取图片 base64。

    三者任选其一；优先级 url > path > file。
    """
    if not any([image_url, image_path, image_file]):
        log_and_raise_error(
            ImageNotFoundError,
            "必须提供 image_url、image_path 或 image_file",
            {},
        )

    if image_url:
        return download_image_as_base64(image_url, session=session)
    if image_path:
        return read_local_image_as_base64(image_path)
    return encode_uploaded_image_as_base64(image_file)


class ImageCache:
    """简单的 LRU 图片缓存，避免短时间内重复下载/读取同一图片。

    下载使用的 ``requests.Session`` 通过 ``download_fn`` 注入，不参与缓存键。
    """

    def __init__(
        self,
        maxsize: int = 32,
        download_fn=None,
        read_fn=None,
    ) -> None:
        self._download = lru_cache(maxsize=maxsize)(
            download_fn or download_image_as_base64
        )
        self._read_local = lru_cache(maxsize=maxsize)(
            read_fn or read_local_image_as_base64
        )

    def get_url(self, image_url: str) -> str:
        return self._download(image_url)

    def get_path(self, image_path: str) -> str:
        return self._read_local(image_path)

    def get(self, image_url=None, image_path=None, image_file=None) -> str:
        if image_url:
            return self.get_url(image_url)
        if image_path:
            return self.get_path(image_path)
        if image_file:
            return encode_uploaded_image_as_base64(image_file)
        log_and_raise_error(
            ImageNotFoundError,
            "必须提供 image_url、image_path 或 image_file",
            {},
        )

    def clear(self) -> None:
        self._download.cache_clear()
        self._read_local.cache_clear()
