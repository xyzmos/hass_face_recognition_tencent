"""API 操作实现。

将原 ``tencent_cloud_client.py`` 中各 API 调用方法（搜索/检测/属性/创建人员/
删除人员/注册人脸/删除人脸/获取库信息/获取人员列表等）抽离为独立函数，
由 ``TencentCloudClient`` 委托调用。每个函数返回标准化的结果字典。

腾讯云 IAI SDK (``tencentcloud.iai.v20200303``) 关键字段（已按 SDK 模型源码核对）：
- 旋转检测参数名为 ``NeedRotateDetection``（SDK 中不存在 ``NeedRotateCheck``）。
- ``CreateFaceRequest`` 使用 ``Images``（列表）；``CreateFaceResponse`` 出参为 ``SucFaceIds``/``SucIndexes``/``SucDeletedNum``。
- ``DeleteFaceResponse`` 出参为 ``SucDeletedNum``/``SucFaceIds``（无 ``SucIndexes``）。
- ``CreatePersonResponse`` 出参为 ``FaceId``/``FaceRect``/``SimilarPersonId``/``FaceModelVersion``（无 ``PersonId``/``SucFaceNum``）。
- ``Candidate`` 无 ``PersonTag`` 字段；``GetGroupInfoResponse`` 库标签字段是 ``Tag``（非 ``GroupTag``）。
- ``FaceInfo`` 的属性位于 ``FaceAttributesInfo``/``FaceQualityInfo`` 子结构，``FaceQualityInfo`` 含 ``Completeness`` 遮挡分。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from tencentcloud.iai.v20200303 import models

from .retry import BENIGN_ERRORS, RetryConfig, execute_with_retry

_LOGGER = logging.getLogger(__name__)

# 是否记录请求/响应载荷详情（调试用）
ENABLE_REQUEST_LOGGING = False
ENABLE_RESPONSE_LOGGING = False
ENABLE_PERFORMANCE_LOGGING = True
LOG_PAYLOAD_MAX_SIZE = 1024


def _log_request(operation: str, params: Dict[str, Any], request_id: str) -> None:
    if not ENABLE_REQUEST_LOGGING:
        return
    safe_params = {}
    for key, value in params.items():
        if key in ("Image", "Images", "Url"):
            safe_params[key] = f"<image_{len(str(value))}_chars>"
        else:
            safe_params[key] = value
    try:
        params_str = json.dumps(safe_params, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        params_str = str(safe_params)
    if len(params_str) > LOG_PAYLOAD_MAX_SIZE:
        params_str = params_str[:LOG_PAYLOAD_MAX_SIZE] + "...[truncated]"
    _LOGGER.debug("API请求: op=%s id=%s params=%s", operation, request_id, params_str)


def _log_response(operation: str, request_id: str, response: Any, duration: float) -> None:
    if ENABLE_PERFORMANCE_LOGGING:
        if duration > 5.0:
            _LOGGER.warning("API响应缓慢: op=%s id=%s duration=%.3fs", operation, request_id, duration)
        elif duration > 2.0:
            _LOGGER.info("API响应较慢: op=%s id=%s duration=%.3fs", operation, request_id, duration)
    if not ENABLE_RESPONSE_LOGGING:
        return
    try:
        resp_dict = {}
        for attr in dir(response):
            if attr.startswith("_") or callable(getattr(response, attr)):
                continue
            resp_dict[attr] = getattr(response, attr)
        resp_str = json.dumps(resp_dict, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        resp_str = str(response)
    if len(resp_str) > LOG_PAYLOAD_MAX_SIZE:
        resp_str = resp_str[:LOG_PAYLOAD_MAX_SIZE] + "...[truncated]"
    _LOGGER.debug("API响应: op=%s id=%s response=%s", operation, request_id, resp_str)


def _log_error(operation: str, request_id: str, error: Exception, duration: float, sanitize=None) -> None:
    sanitize = sanitize or (lambda s: s)
    code = getattr(error, "code", None)
    # 预期内的业务空结果（如无人脸）不打 ERROR，避免污染日志
    benign = code in BENIGN_ERRORS
    if benign:
        _LOGGER.info(
            "API业务结果: op=%s id=%s duration=%.3fs code=%s msg=%s",
            operation, request_id, duration, code, sanitize(str(error)),
        )
    else:
        _LOGGER.error(
            "API错误: op=%s id=%s duration=%.3fs error_type=%s msg=%s",
            operation, request_id, duration, type(error).__name__,
            sanitize(str(error)),
        )
        if code:
            _LOGGER.error(
                "腾讯云API错误详情: op=%s id=%s code=%s", operation, request_id, code
            )
    if _LOGGER.isEnabledFor(logging.DEBUG):
        _LOGGER.debug("API错误堆栈: op=%s id=%s", operation, request_id, exc_info=True)


def _build_error_result(ex: Exception, **extra: Any) -> Dict[str, Any]:
    """构造失败结果字典。"""
    from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
        TencentCloudSDKException,
    )
    result: Dict[str, Any] = {"success": False}
    result.update(extra)
    if isinstance(ex, TencentCloudSDKException):
        result["error_code"] = getattr(ex, "code", None)
        result["error_message"] = getattr(ex, "message", str(ex))
    else:
        result["error_code"] = None
        result["error_message"] = str(ex)
    result["error"] = str(ex)
    return result


def _run(
    client,
    operation_name: str,
    build_request,
    send,
    parse_response,
    *,
    retry_config: Optional[RetryConfig] = None,
    sanitize=None,
    success_extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """统一的 API 调用包装：构建请求 -> 发送 -> 解析响应，带重试。

    - ``build_request()`` 返回 ``(models.XxxRequest, params_dict)``。
    - ``send(req)`` 调用 client 的实际 SDK 方法，返回 response。
    - ``parse_response(resp)`` 返回业务结果字典（成功部分）。
    """

    def api_call() -> Dict[str, Any]:
        request_id = str(uuid.uuid4())
        start = time.time()
        try:
            req, params = build_request()
            _log_request(operation_name, params, request_id)
            resp = send(req)
            duration = time.time() - start
            _log_response(operation_name, request_id, resp, duration)
            result = {"success": True}
            request_id = getattr(resp, "RequestId", None)
            if request_id:
                result["request_id"] = request_id
            if success_extra:
                result.update(success_extra)
            result.update(parse_response(resp))
            return result
        except Exception as ex:  # noqa: BLE001
            duration = time.time() - start
            _log_error(operation_name, request_id, ex, duration, sanitize)
            # 抛出交由 execute_with_retry 决定是否重试
            raise

    return execute_with_retry(
        api_call, operation_name, config=retry_config, sanitize_error=sanitize
    )


# --- 各操作实现 -----------------------------------------------------------


def search_faces(
    client,
    *,
    image_base64: str,
    group_ids: List[str],
    max_face_num: int = 1,
    min_face_size: int = 34,
    max_user_num: int = 5,
    quality_control: int = 1,
    need_rotate_check: int = 1,
    face_match_threshold: float = 60.0,
    retry_config: Optional[RetryConfig] = None,
    sanitize=None,
) -> Dict[str, Any]:
    """搜索人脸。"""

    def build_request():
        req = models.SearchFacesRequest()
        params = {
            "NeedPersonInfo": 1,
            "Image": image_base64,
            "MaxFaceNum": max_face_num,
            "MinFaceSize": min_face_size,
            "MaxPersonNum": max_user_num,
            "QualityControl": quality_control,
            "NeedRotateDetection": need_rotate_check,
            "FaceMatchThreshold": face_match_threshold,
            "GroupIds": group_ids,
        }
        req.from_json_string(json.dumps(params))
        return req, params

    def parse_response(resp):
        results: List[Dict[str, Any]] = []
        for result in getattr(resp, "Results", []) or []:
            face_result: Dict[str, Any] = {
                "face_id": None,
                "candidates": [],
                "face_rect": _face_rect_dict(getattr(result, "FaceRect", None)),
                # Result.RetCode：0 正常，-1601 质量不达标等
                "ret_code": getattr(result, "RetCode", 0),
            }
            for candidate in getattr(result, "Candidates", []) or []:
                face_result["candidates"].append({
                    "person_id": getattr(candidate, "PersonId", None),
                    "person_name": getattr(candidate, "PersonName", None),
                    "score": getattr(candidate, "Score", None),
                    "face_id": getattr(candidate, "FaceId", None),
                    "gender": getattr(candidate, "Gender", None),
                    "person_group_infos": _person_group_infos(
                        getattr(candidate, "PersonGroupInfos", None)
                    ),
                })
            results.append(face_result)
        return {
            "faces": results,
            "face_count": getattr(resp, "FaceNum", len(results)),
            "face_model_version": getattr(resp, "FaceModelVersion", ""),
        }

    return _run(
        client, "人脸搜索", build_request,
        lambda req: client.SearchFaces(req), parse_response,
        retry_config=retry_config, sanitize=sanitize,
    )


def detect_faces(
    client,
    *,
    image_base64: str,
    max_face_num: int = 1,
    min_face_size: int = 34,
    need_rotate_check: int = 1,
    retry_config: Optional[RetryConfig] = None,
    sanitize=None,
) -> Dict[str, Any]:
    """检测人脸（不返回属性）。"""

    def build_request():
        req = models.DetectFaceRequest()
        params = {
            "Image": image_base64,
            "MaxFaceNum": max_face_num,
            "MinFaceSize": min_face_size,
            "NeedRotateDetection": need_rotate_check,
        }
        req.from_json_string(json.dumps(params))
        return req, params

    def parse_response(resp):
        results = []
        for info in getattr(resp, "FaceInfos", []) or []:
            results.append({
                "x": getattr(info, "X", 0),
                "y": getattr(info, "Y", 0),
                "width": getattr(info, "Width", 0),
                "height": getattr(info, "Height", 0),
            })
        return {"faces": results, "face_count": len(results),
                "image_width": getattr(resp, "ImageWidth", 0),
                "image_height": getattr(resp, "ImageHeight", 0),
                "face_model_version": getattr(resp, "FaceModelVersion", "")}

    return _run(
        client, "人脸检测", build_request,
        lambda req: client.DetectFace(req), parse_response,
        retry_config=retry_config, sanitize=sanitize,
    )


def get_face_attributes(
    client,
    *,
    image_base64: str,
    max_face_num: int = 1,
    need_rotate_check: int = 1,
    retry_config: Optional[RetryConfig] = None,
    sanitize=None,
) -> Dict[str, Any]:
    """获取人脸属性。"""

    def build_request():
        req = models.DetectFaceRequest()
        params = {
            "Image": image_base64,
            "MaxFaceNum": max_face_num,
            "NeedRotateDetection": need_rotate_check,
            "NeedFaceAttributes": 1,
            "NeedQualityDetection": 1,
        }
        req.from_json_string(json.dumps(params))
        return req, params

    def parse_response(resp):
        results = []
        for info in getattr(resp, "FaceInfos", []) or []:
            attrs = getattr(info, "FaceAttributesInfo", None)
            quality = getattr(info, "FaceQualityInfo", None)
            results.append({
                "x": getattr(info, "X", 0),
                "y": getattr(info, "Y", 0),
                "width": getattr(info, "Width", 0),
                "height": getattr(info, "Height", 0),
                "gender": getattr(attrs, "Gender", None) if attrs else None,
                "age": getattr(attrs, "Age", None) if attrs else None,
                "expression": getattr(attrs, "Expression", None) if attrs else None,
                "beauty": getattr(attrs, "Beauty", None) if attrs else None,
                "glass": getattr(attrs, "Glass", None) if attrs else None,
                "pitch": getattr(attrs, "Pitch", None) if attrs else None,
                "yaw": getattr(attrs, "Yaw", None) if attrs else None,
                "roll": getattr(attrs, "Roll", None) if attrs else None,
                "eye_open": getattr(attrs, "EyeOpen", None) if attrs else None,
                "mask": getattr(attrs, "Mask", None) if attrs else None,
                "hat": getattr(attrs, "Hat", None) if attrs else None,
                "quality_score": getattr(quality, "Score", None) if quality else None,
                "quality_brightness": getattr(quality, "Brightness", None) if quality else None,
                "quality_sharpness": getattr(quality, "Sharpness", None) if quality else None,
                "quality_completeness": _completeness_dict(
                    getattr(quality, "Completeness", None) if quality else None
                ),
            })
        return {"faces": results, "face_count": len(results),
                "image_width": getattr(resp, "ImageWidth", 0),
                "image_height": getattr(resp, "ImageHeight", 0),
                "face_model_version": getattr(resp, "FaceModelVersion", "")}

    return _run(
        client, "获取人脸属性", build_request,
        lambda req: client.DetectFace(req), parse_response,
        retry_config=retry_config, sanitize=sanitize,
    )


def create_person(
    client,
    *,
    person_id: str,
    person_name: str,
    group_id: str,
    image_base64: Optional[str] = None,
    gender: Optional[int] = None,
    person_tag: Optional[str] = None,
    quality_control: int = 1,
    need_rotate_check: int = 1,
    unique_person_control: Optional[int] = None,
    retry_config: Optional[RetryConfig] = None,
    sanitize=None,
) -> Dict[str, Any]:
    """创建人员。"""

    def build_request():
        req = models.CreatePersonRequest()
        params: Dict[str, Any] = {
            "PersonId": person_id,
            "PersonName": person_name,
            "GroupId": group_id,
            "QualityControl": quality_control,
            "NeedRotateDetection": need_rotate_check,
        }
        if image_base64:
            params["Image"] = image_base64
        if gender is not None:
            params["Gender"] = gender
        # 0=不查重 1=查重 2=全局查重 3=全局并拒绝 4=自定义
        if unique_person_control is not None:
            params["UniquePersonControl"] = unique_person_control
        # ``PersonTag`` 字段在 SDK 中已废弃，人员备注需通过
        # ``PersonExDescriptionInfos``（外部描述列表）存储。
        if person_tag is not None:
            params["PersonExDescriptionInfos"] = [
                {
                    "PersonExDescriptionIndex": 0,
                    "PersonExDescription": person_tag,
                }
            ]
        req.from_json_string(json.dumps(params))
        return req, params

    def parse_response(resp):
        return {
            "person_id": getattr(resp, "PersonId", person_id),
            "face_id": getattr(resp, "FaceId", ""),
            "face_rect": _face_rect_dict(getattr(resp, "FaceRect", None)),
            "face_model_version": getattr(resp, "FaceModelVersion", ""),
            # 疑似同一人（已存在相似人员）时返回，供调用方去重
            "similar_person_id": getattr(resp, "SimilarPersonId", ""),
        }

    return _run(
        client, "创建人员", build_request,
        lambda req: client.CreatePerson(req), parse_response,
        retry_config=retry_config, sanitize=sanitize,
    )


def delete_person(
    client,
    *,
    person_id: str,
    retry_config: Optional[RetryConfig] = None,
    sanitize=None,
) -> Dict[str, Any]:
    """删除人员。"""

    def build_request():
        req = models.DeletePersonRequest()
        params = {"PersonId": person_id}
        req.from_json_string(json.dumps(params))
        return req, params

    return _run(
        client, "删除人员", build_request,
        lambda req: client.DeletePerson(req), lambda resp: {"person_id": person_id},
        retry_config=retry_config, sanitize=sanitize,
    )


def create_face(
    client,
    *,
    person_id: str,
    image_base64: str,
    quality_control: int = 1,
    need_rotate_check: int = 1,
    face_match_threshold: Optional[float] = None,
    retry_config: Optional[RetryConfig] = None,
    sanitize=None,
) -> Dict[str, Any]:
    """为人员注册人脸。

    ``CreateFaceRequest`` 接受 ``Images``（列表），单张图片包装为单元素列表。
    ``face_match_threshold`` 为同人校验阈值（默认 60），用于避免向同一人员
    重复注册高度相似的人脸。
    """

    def build_request():
        req = models.CreateFaceRequest()
        params: Dict[str, Any] = {
            "PersonId": person_id,
            "Images": [image_base64],
            "QualityControl": quality_control,
            "NeedRotateDetection": need_rotate_check,
        }
        if face_match_threshold is not None:
            params["FaceMatchThreshold"] = face_match_threshold
        req.from_json_string(json.dumps(params))
        return req, params

    def parse_response(resp):
        return {
            "person_id": person_id,
            "face_ids": list(getattr(resp, "SucFaceIds", []) or []),
            "face_rects": [_face_rect_dict(r) for r in (getattr(resp, "SucFaceRects", []) or [])],
            "suc_face_num": getattr(resp, "SucFaceNum", 0),
            "suc_indexes": list(getattr(resp, "SucIndexes", []) or []),
            "ret_code": getattr(resp, "RetCode", None),
            "face_model_version": getattr(resp, "FaceModelVersion", ""),
        }

    return _run(
        client, "注册人脸", build_request,
        lambda req: client.CreateFace(req), parse_response,
        retry_config=retry_config, sanitize=sanitize,
    )


def delete_face(
    client,
    *,
    person_id: str,
    face_id: str,
    retry_config: Optional[RetryConfig] = None,
    sanitize=None,
) -> Dict[str, Any]:
    """删除人脸。``DeleteFaceRequest`` 接受 ``FaceIds``（列表）。"""

    def build_request():
        req = models.DeleteFaceRequest()
        params = {"PersonId": person_id, "FaceIds": [face_id]}
        req.from_json_string(json.dumps(params))
        return req, params

    return _run(
        client, "删除人脸", build_request,
        lambda req: client.DeleteFace(req),
        lambda resp: {"person_id": person_id, "face_id": face_id,
                      "suc_face_ids": list(getattr(resp, "SucFaceIds", []) or []),
                      "suc_deleted_num": getattr(resp, "SucDeletedNum", 0)},
        retry_config=retry_config, sanitize=sanitize,
    )


def get_group_info(
    client,
    *,
    group_id: str,
    retry_config: Optional[RetryConfig] = None,
    sanitize=None,
) -> Dict[str, Any]:
    """获取人员库信息。"""

    def build_request():
        req = models.GetGroupInfoRequest()
        params = {"GroupId": group_id}
        req.from_json_string(json.dumps(params))
        return req, params

    def parse_response(resp):
        return {
            "group_id": getattr(resp, "GroupId", group_id),
            "group_name": getattr(resp, "GroupName", ""),
            # SDK 字段名为 Tag（库标签），原代码误用 GroupTag
            "group_tag": getattr(resp, "Tag", ""),
            "face_model_version": getattr(resp, "FaceModelVersion", ""),
            "creation_timestamp": getattr(resp, "CreationTimestamp", 0),
            "group_ex_descriptions": list(getattr(resp, "GroupExDescriptions", []) or []),
        }

    return _run(
        client, "获取人员库信息", build_request,
        lambda req: client.GetGroupInfo(req), parse_response,
        retry_config=retry_config, sanitize=sanitize,
    )


def get_person_list(
    client,
    *,
    group_id: str,
    limit: int = 100,
    offset: int = 0,
    retry_config: Optional[RetryConfig] = None,
    sanitize=None,
) -> Dict[str, Any]:
    """获取人员列表（单页）。"""

    def build_request():
        req = models.GetPersonListRequest()
        params = {"GroupId": group_id, "Limit": limit, "Offset": offset}
        req.from_json_string(json.dumps(params))
        return req, params

    def parse_response(resp):
        persons = []
        for info in getattr(resp, "PersonInfos", []) or []:
            persons.append({
                "person_id": getattr(info, "PersonId", ""),
                "person_name": getattr(info, "PersonName", ""),
                "gender": getattr(info, "Gender", 0),
                "face_ids": list(getattr(info, "FaceIds", []) or []),
                "person_ex_descriptions": list(
                    getattr(info, "PersonExDescriptions", []) or []
                ),
                "creation_timestamp": getattr(info, "CreationTimestamp", 0),
            })
        return {
            "persons": persons,
            "person_num": getattr(resp, "PersonNum", len(persons)),
            "face_model_version": getattr(resp, "FaceModelVersion", ""),
        }

    return _run(
        client, "获取人员列表", build_request,
        lambda req: client.GetPersonList(req), parse_response,
        retry_config=retry_config, sanitize=sanitize,
    )


def get_person_list_all(
    client,
    *,
    group_id: str,
    limit: int = 100,
    retry_config: Optional[RetryConfig] = None,
    sanitize=None,
) -> Dict[str, Any]:
    """获取人员列表（自动分页获取全部）。"""
    all_persons: List[Dict[str, Any]] = []
    offset = 0
    face_model_version = ""
    while True:
        page = get_person_list(
            client, group_id=group_id, limit=limit, offset=offset,
            retry_config=retry_config, sanitize=sanitize,
        )
        if not page.get("success", False):
            return page
        persons = page.get("persons", [])
        all_persons.extend(persons)
        face_model_version = page.get("face_model_version", face_model_version)
        # 单页不足 limit 视为末页
        if len(persons) < limit:
            break
        offset += limit
        # 防御：person_num 已达上限则停止
        person_num = page.get("person_num", 0)
        if person_num and len(all_persons) >= person_num:
            break

    return {
        "success": True,
        "persons": all_persons,
        "person_count": len(all_persons),
        "face_model_version": face_model_version,
        "error": None,
        "error_code": None,
        "error_message": None,
    }


def verify_credentials(client, retry_config: Optional[RetryConfig] = None) -> bool:
    """验证凭据是否有效，通过调用 GetGroupList 轻量测试。

    成功返回 True；失败抛出对应的 ``TencentFaceRecognitionError``。
    """

    def api_call() -> bool:
        req = models.GetGroupListRequest()
        req.from_json_string(json.dumps({"Limit": 1, "Offset": 0}))
        client.GetGroupList(req)
        return True

    execute_with_retry(api_call, "凭据验证", config=retry_config)
    _LOGGER.info("凭据验证成功")
    return True


# --- 辅助 -----------------------------------------------------------------


def _face_rect_dict(face_rect) -> Optional[Dict[str, Any]]:
    """将 SDK 的 FaceRect 对象转为字典。"""
    if face_rect is None:
        return None
    return {
        "x": getattr(face_rect, "X", 0),
        "y": getattr(face_rect, "Y", 0),
        "width": getattr(face_rect, "Width", 0),
        "height": getattr(face_rect, "Height", 0),
    }


def _completeness_dict(completeness) -> Optional[Dict[str, Any]]:
    """FaceQualityInfo.Completeness（五官遮挡分）转字典。"""
    if completeness is None:
        return None
    return {
        "eyebrow": getattr(completeness, "Eyebrow", None),
        "eye": getattr(completeness, "Eye", None),
        "nose": getattr(completeness, "Nose", None),
        "cheek": getattr(completeness, "Cheek", None),
        "mouth": getattr(completeness, "Mouth", None),
        "chin": getattr(completeness, "Chin", None),
    }


def _person_group_infos(infos) -> List[Dict[str, Any]]:
    """将 Candidate.PersonGroupInfos 转为列表字典。"""
    if not infos:
        return []
    result = []
    for info in infos:
        result.append({
            "group_id": getattr(info, "GroupId", ""),
            "person_ex_descriptions": list(getattr(info, "PersonExDescriptions", []) or []),
        })
    return result
