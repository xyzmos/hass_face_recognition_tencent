# 腾讯云人脸识别 Home Assistant 集成

基于腾讯云人脸识别（IAI）API 的 Home Assistant 自定义集成，主要面向**自动化**场景：抓拍 → 检测/搜索 → 触发自动化。

## 功能特性

- **人脸搜索** `face_search`：在人员库中匹配人脸，返回候选人并触发识别事件
- **人脸检测** `detect_face`：检测人脸位置与尺寸
- **人脸属性** `get_face_attributes`：性别、年龄、表情、颜值、口罩、帽子、遮挡分等
- **人员管理** `create_person` / `delete_person`：支持摄像头抓拍或图片注册
- **人脸管理** `create_face` / `delete_face`：为人员补充/删除人脸
- **传感器**：人员库状态（诊断）+ 每个成员一个传感器，自动增删
- **多配置**：支持多个腾讯云账号，服务可用 `config_entry_id` 指定
- **可靠性**：指数退避重试、HTTP 连接池、图片缓存、凭据脱敏

## 安装

### 方式一：HACS（推荐）

> 本仓库遵循 HACS `custom_components/<domain>` 标准布局。

1. HACS → 右上角 **⋮** → **Custom repositories**
2. 仓库地址填 `https://code.nextrt.com/Hass/tencent_face_recognition`，类型选 **Integration**，点 **Add**
3. 在 HACS 中找到「腾讯云人脸识别」，点 **Download**
4. 重启 Home Assistant

### 方式二：手动安装

1. 将本仓库 `custom_components/tencent_face_recognition` 目录复制到 HA 的 `config/custom_components/` 下
2. 重启 Home Assistant

## 配置

1. 「设置」→「设备与服务」→「添加集成」→ 搜索「腾讯云人脸识别」
2. 填写腾讯云 **Secret ID / Secret Key**，可选区域与默认人员库 ID

| 参数 | 必需 | 默认 | 说明 |
|------|------|------|------|
| Secret ID | 是 | - | 腾讯云 API Secret ID（以 `AKID` 开头） |
| Secret Key | 是 | - | 腾讯云 API Secret Key |
| 区域 | 否 | `ap-shanghai` | 服务区域 |
| 人员库 ID | 否 | `Hass` | 默认人员库 |
| 刷新间隔 | 否 | `300` 秒 | 人员/状态传感器刷新间隔 |

凭据失效会自动弹出 **重新认证**；也可在集成「选项」中做**测试连接**与**人员管理**。

## 服务（Actions）

所有服务都支持 `response_variable` 获取结果，统一返回 `success`/`error*` 字段及 `request_id`（排障用）。

通用图片参数（按优先级取第一个有效）：`camera_entity_id`（摄像头，优先）> `image_url` > `image_path` > `image_file`（Base64）。`group_id` 在多数服务中可省略，缺省使用配置项默认人员库。

> `image_path` 须位于 `configuration.yaml` 的 `allowlist_external_dirs` 允许目录内（如 `/config/www`），否则会被拒绝读取。

### 人脸搜索 `face_search`

| 参数 | 默认 | 说明 |
|------|------|------|
| `group_id` | 默认人员库 | 目标人员库 ID |
| `max_face_num` | 1 | 最多人脸数 1–10 |
| `min_face_size` | 34 | 最小人脸（20–4096 像素） |
| `max_user_num` | 5 | 返回人数 1–100 |
| `quality_control` | 1 | 质量控制 0–4 |
| `need_rotate_check` | 1 | 旋转检查 0/1 |
| `face_match_threshold` | 60.0 | 匹配阈值 0–100 |

```yaml
action: tencent_face_recognition.face_search
response_variable: r
data:
  camera_entity_id: camera.doorbell
  max_face_num: 5
  face_match_threshold: 70
```

识别到人员时触发事件 **`tencent_face_recognition_face_detected`**（兼容旧事件 `face_detected`）：

```yaml
triggers:
  - trigger: event
    event_type: tencent_face_recognition_face_detected
actions:
  - action: notify.notify
    data:
      message: "识别到 {{ trigger.event.data.person_name }}（{{ trigger.event.data.score }}%）"
```

### 人脸检测 `detect_face`

返回人脸框 `x/y/width/height`、`image_width/height`、`face_model_version`。

### 获取人脸属性 `get_face_attributes`

返回 `gender/age/expression/beauty/glass/pitch/yaw/roll/eye_open/mask/hat` 及质量分 `quality_score/brightness/sharpness/completeness`。

### 创建人员 `create_person`

`person_id`/`person_name` 必填，`group_id` 可省。可选 `gender`（0女/1男/2未知）、`person_tag`、`unique_person_control`（0–4 同人查重）。建议同时提供图片来源以注册人脸。

### 注册人脸 `create_face`

`person_id` 必填 + 任一图片来源。可选 `face_match_threshold`（同人校验阈值，默认 60）。

### 删除人员 / 删除人脸

`delete_person`（`person_id`）与 `delete_face`（`person_id` + `face_id`）。

## 传感器

| 实体 | 说明 |
|------|------|
| `状态`（诊断） | 已连接 / 未连接 / 连接错误，属性含人员数、模型版本、库信息 |
| `人员 xxx` | 每个人员一个传感器，状态=姓名，属性含 `face_ids`、性别等 |

人员库成员变化时，传感器随协调器自动增删。

## 蓝图（Blueprint）

仓库内 `blueprints/automation/face_detection_automation.yaml` 为示例蓝图。HACS 安装不会自动导入蓝图，请手动：设置 → 自动化 → 蓝图 → **导入蓝图**，粘贴该文件 URL，或把文件复制到 `config/blueprints/automation/` 后重启。

## 故障排除

| 问题 | 处理 |
|------|------|
| 认证失败 | 检查 Secret ID/Key（AKID 开头），或欠费/停用 |
| 图片失败 | 路径可访问、格式 JPG/PNG/BMP/GIF、≤10MB |
| 无人脸 | 图片需含清晰人脸，人脸 ≥ 最小尺寸 |
| 限流 | 已内置退避重试；可降低调用频率或升级套餐 |

开发者工具 → 日志，开启 `custom_components.tencent_face_recognition` 的 debug 可获详细日志。

## 文档参考

- [腾讯云人脸识别 API](https://cloud.tencent.com/document/product/867)
- [Home Assistant 自定义集成](https://developers.home-assistant.io/docs/creating_integration_manifest)
- [HACS 发布规范](https://www.hacs.xyz/docs/publish/integration/)

## 许可证

MIT License，见 [LICENSE](LICENSE)。
