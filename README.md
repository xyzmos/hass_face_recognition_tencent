# 腾讯云人脸识别 · Home Assistant 集成

[![Validate](https://code.nextrt.com/Hass/tencent_face_recognition/actions/workflows/validate.yml/badge.svg)](https://code.nextrt.com/Hass/tencent_face_recognition/actions)
[![Release](https://code.nextrt.com/Hass/tencent_face_recognition/actions/workflows/release.yaml/badge.svg)](https://code.nextrt.com/Hass/tencent_face_recognition/releases)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![hassfest](https://img.shields.io/badge/hassfest-passing-brightgreen)](https://developers.home-assistant.io/)

基于腾讯云人脸识别（IAI）API 的 Home Assistant 自定义集成。**专为自动化场景设计**：摄像头/门铃触发 → 抓拍 → 检测/搜索 → 驱动自动化。

```
binary_sensor(门铃/人体感应) → camera 抓拍 → face_search / detect_face
        ↓
   face_detected 事件 / 通知 / 自动化条件
```

## 功能特性

- 🔍 **人脸搜索** `face_search`：人员库匹配，返回候选人并触发识别事件
- 📷 **人脸检测** `detect_face`：返回人脸框坐标与尺寸
- 👤 **人脸属性** `get_face_attributes`：性别、年龄、表情、颜值、口罩、帽子、遮挡分等
- ➕ **人员管理** `create_person` / `delete_person`：支持摄像头抓拍注册
- 🖼️ **人脸管理** `create_face` / `delete_face`：为人员补充/删除人脸
- 📊 **传感器**：人员库状态（诊断）+ 每个成员一个传感器，自动增删
- 🔁 **多配置**：多腾讯云账号并存，服务用 `config_entry_id` 指定
- 🛡️ **可靠性**：指数退避重试、HTTP 连接池、图片缓存、凭据脱敏、`allowlist` 安全校验

## 安装

### 方式一：HACS（推荐）

> 本仓库遵循 HACS `custom_components/<domain>` 标准布局，发布包含 zip 资产。

1. 打开 **HACS** → 右上角 **⋮** → **Custom repositories**
2. 仓库地址：`https://code.nextrt.com/Hass/tencent_face_recognition`，类型选 **Integration** → **Add**
3. 找到「腾讯云人脸识别」→ **Download**
4. 重启 Home Assistant

### 方式二：手动安装

1. 将 `custom_components/tencent_face_recognition` 复制到 `config/custom_components/`
2. 重启 Home Assistant

## 配置

「设置」→「设备与服务」→「添加集成」→ 搜索「腾讯云人脸识别」。

| 参数 | 必需 | 默认 | 说明 |
|------|:--:|------|------|
| Secret ID | ✅ | - | 腾讯云 Secret ID（`AKID` 开头） |
| Secret Key | ✅ | - | 腾讯云 Secret Key |
| 区域 | - | `ap-shanghai` | 服务区域 |
| 人员库 ID | - | `Hass` | 默认人员库 |
| 刷新间隔 | - | `300` 秒 | 传感器刷新间隔 |

> 凭据失效会自动弹出**重新认证**；集成「选项」里可做**基础设置**、**测试连接**、**人员管理**（增删人员）。

## 在自动化中使用

### 触发人脸搜索

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.doorbell   # 门铃/人体感应
    to: "on"
actions:
  - action: tencent_face_recognition.face_search
    response_variable: r
    data:
      camera_entity_id: camera.doorbell
      max_face_num: 5
      face_match_threshold: 70
  - choose:
      - conditions: "{{ r.faces | length > 0 and r.faces[0].candidates | length > 0 }}"
        sequence:
          - action: notify.notify
            data:
              message: "识别到 {{ r.faces[0].candidates[0].person_name }}（{{ r.faces[0].candidates[0].score }}%）"
```

### 识别事件

`face_search` 命中人员时触发事件 **`tencent_face_recognition_face_detected`**（兼容旧 `face_detected`），可直接作为触发器：

```yaml
triggers:
  - trigger: event
    event_type: tencent_face_recognition_face_detected
actions:
  - action: notify.notify
    data:
      message: "{{ trigger.event.data.person_name }} 到家了"
```

事件数据：`person_id`、`person_name`、`score`、`face_id`、`gender`、`group_id`、`camera_entity_id`。

## 服务（Actions）

所有服务支持 `response_variable` 取结果，统一返回 `success`/`error*`/`request_id` 等字段。

通用图片参数（取第一个有效）：`camera_entity_id`（摄像头）> `image_url` > `image_path` > `image_file`（Base64）。`group_id` 多数服务可省略（用默认人员库）。

> `image_path` 须位于 `configuration.yaml` 的 `allowlist_external_dirs` 内（如 `/config/www`）。

| 服务 | 说明 | 关键参数 |
|------|------|----------|
| `face_search` | 人员库匹配 | `group_id` `max_face_num` `min_face_size` `max_user_num` `quality_control` `need_rotate_check` `face_match_threshold` |
| `detect_face` | 检测人脸位置 | `max_face_num` `min_face_size` `need_rotate_check` |
| `get_face_attributes` | 人脸属性 | `max_face_num` `need_rotate_check` |
| `create_person` | 建人员 | `person_id`* `person_name`* `group_id` `gender` `person_tag` `unique_person_control` |
| `create_face` | 给人加人脸 | `person_id`* `quality_control` `face_match_threshold` |
| `delete_person` | 删人员 | `person_id`* |
| `delete_face` | 删人脸 | `person_id`* `face_id`* |

`*` 必填。

`create_person` 建议同时给图片；`create_face` 的 `face_match_threshold` 用于同人校验（默认 60）。

## 传感器

| 实体 | 说明 |
|------|------|
| `状态`（诊断） | 已连接/未连接/连接错误，属性含人员数、模型版本、库信息 |
| `人员 xxx` | 每人一个，状态=姓名，属性含 `face_ids`、性别等 |

人员库变化时传感器自动增删。

## 蓝图（Blueprint）

`blueprints/automation/face_detection_automation.yaml`：触发实体（binary_sensor）→ 抓拍 → 检测/搜索 → 通知。

**导入方式**（HACS 不自动装蓝图）：设置 → 自动化 → 蓝图 → **导入蓝图**，粘贴该文件 URL；或把文件复制到 `config/blueprints/automation/` 后重启。

## 发布新版本（维护者）

1. 改 `custom_components/tencent_face_recognition/manifest.json` 的 `version`
2. `git tag vX.Y.Z && git push origin vX.Y.Z`
3. `release.yaml` 自动：校验版本一致性 → 打包 zip → 创建 release 并上传 `tencent_face_recognition.zip`（HACS 用）

## 故障排除

| 问题 | 处理 |
|------|------|
| 认证失败 | 检查 Secret ID/Key（`AKID` 开头）、是否欠费/停用 |
| 图片失败 | 路径可访问且在 `allowlist_external_dirs` 内；JPG/PNG/BMP/GIF、≤10MB |
| 无人脸 | 图片需含清晰人脸，人脸 ≥ 最小尺寸 |
| 限流 | 已内置退避重试；降低频率或升级套餐 |

开发者工具 → 日志，开启 `custom_components.tencent_face_recognition` 的 debug 可获详细日志。集成页可「下载诊断」（凭据已脱敏）。

## 文档参考

- [腾讯云人脸识别 API](https://cloud.tencent.com/document/product/867)
- [Home Assistant 自定义集成](https://developers.home-assistant.io/docs/creating_integration_manifest)
- [HACS 发布规范](https://www.hacs.xyz/docs/publish/integration/)

## 许可证

[MIT License](LICENSE)
