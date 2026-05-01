# 腾讯云人脸识别 Home Assistant 插件

基于腾讯云人脸识别 API 的 Home Assistant 自定义集成，提供完整的人脸管理能力。

## 功能特性

- **人脸搜索**：通过图片 URL、本地文件、Base64 编码或摄像头实体搜索人脸，返回匹配的人员信息
- **人脸检测**：检测图片中的人脸位置和尺寸
- **人脸属性分析**：获取人脸的性别、年龄、表情等属性
- **人员管理**：创建/删除人员，支持带图或无图创建
- **人脸管理**：为人员注册新人脸或删除已有人脸
- **传感器**：自动同步人员库状态，提供人员数量和连接状态传感器
- **多配置支持**：支持多个腾讯云账号同时接入
- **自动重试**：内置指数退避重试机制，应对网络波动和限流
- **连接复用**：HTTP Session 池化，减少重复连接开销
- **图片缓存**：URL/路径图片 LRU 缓存，避免重复下载

## 安装

### 方式一：手动安装

1. 将 `tencent_face_recognition` 目录复制到 Home Assistant 的 `custom_components` 目录下
2. 重启 Home Assistant

### 方式二：HACS 安装

在 HACS 中搜索"腾讯云人脸识别"并安装。

### 配置集成

1. 在"设置" → "设备与服务"中点击"添加集成"
2. 搜索"腾讯云人脸识别"
3. 输入腾讯云 Secret ID、Secret Key 及可选的区域和人员库 ID

## 腾讯云相关

- [腾讯云人脸识别](https://curl.qcloud.com/oqiFPa7h)
- [人脸管理控制台](https://curl.qcloud.com/RMATbuiO)
- [获取 API 密钥](https://curl.qcloud.com/cT0HlJRW)

## 配置项

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| Secret ID | 是 | - | 腾讯云 API 的 Secret ID |
| Secret Key | 是 | - | 腾讯云 API 的 Secret Key |
| 区域 | 否 | `ap-shanghai` | 腾讯云服务区域 |
| 人员库 ID | 否 | `Hass` | 默认使用的人员库 ID |

## 服务

所有服务均支持 `response_variable` 获取返回结果，统一返回格式：

```json
{
  "success": true,
  "error": null,
  "error_code": null,
  "error_message": null
}
```

失败时：

```json
{
  "success": false,
  "error": "错误描述",
  "error_code": "error_code",
  "error_message": "详细错误信息"
}
```

通用图片参数（按优先级取第一个有效的）：

| 参数 | 说明 |
|------|------|
| `camera_entity_id` | 摄像头实体 ID（优先） |
| `image_url` | 图片 URL |
| `image_path` | 本地文件路径 |
| `image_file` | Base64 编码图片 |
| `config_entry_id` | 多配置时指定配置项 ID |

---

### 人脸搜索

`tencent_face_recognition.face_search`

在人员库中搜索匹配的人脸。搜索成功时会触发 `face_detected` 事件。

**独有参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `group_id` (必填) | - | 要搜索的人员库 ID |
| `max_face_num` | 1 | 最多处理的人脸数量 |
| `min_face_size` | 34 | 最小人脸尺寸（像素） |
| `max_user_num` | 5 | 最多返回的匹配人员数量 |
| `quality_control` | 1 | 质量控制（0=关闭，1=开启） |
| `need_rotate_check` | 1 | 旋转检查（0=关闭，1=开启） |
| `face_match_threshold` | 60.0 | 匹配阈值（0-100） |

**示例**：

```yaml
action: tencent_face_recognition.face_search
response_variable: search_result
data:
  group_id: "Hass"
  image_path: "/config/www/camera/face.jpg"
  face_match_threshold: 70
  max_face_num: 5
```

**触发事件** `face_detected`：

```yaml
- trigger:
    - platform: event
      event_type: face_detected
  action:
    - service: persistent_notification.create
      data:
        message: "识别到 {{ trigger.event.data.person_name }}，置信度 {{ trigger.event.data.score }}"
```

---

### 人脸检测

`tencent_face_recognition.detect_face`

检测图片中的人脸位置和尺寸。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_face_num` | 1 | 最多检测的人脸数量 |
| `min_face_size` | 34 | 最小人脸尺寸（像素） |
| `need_rotate_check` | 1 | 旋转检查 |

**示例**：

```yaml
action: tencent_face_recognition.detect_face
response_variable: detect_result
data:
  camera_entity_id: "camera.front_door"
  max_face_num: 10
```

---

### 获取人脸属性

`tencent_face_recognition.get_face_attributes`

获取图片中人脸的性别、年龄、表情等属性信息。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_face_num` | 1 | 最多分析的人脸数量 |
| `need_rotate_check` | 1 | 旋转检查 |

**示例**：

```yaml
action: tencent_face_recognition.get_face_attributes
response_variable: attr_result
data:
  image_url: "https://example.com/photo.jpg"
```

---

### 创建人员

`tencent_face_recognition.create_person`

在人员库中创建新人员，图片为可选（支持先建人后传图）。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `person_id` (必填) | - | 人员唯一标识符 |
| `person_name` (必填) | - | 人员名称 |
| `group_id` (必填) | - | 所属人员库 ID |
| `gender` | - | 性别（0=女，1=男） |
| `person_tag` | - | 备注标签 |
| `quality_control` | 1 | 质量控制 |
| `need_rotate_check` | 1 | 旋转检查 |

**示例**：

```yaml
action: tencent_face_recognition.create_person
response_variable: create_result
data:
  person_id: "person_001"
  person_name: "张三"
  group_id: "Hass"
  image_url: "https://example.com/face.jpg"
  gender: 1
```

---

### 删除人员

`tencent_face_recognition.delete_person`

从人员库中删除人员。

| 参数 | 说明 |
|------|------|
| `person_id` (必填) | 要删除的人员 ID |

---

### 注册人脸

`tencent_face_recognition.create_face`

为已有人员添加新的人脸照片。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `person_id` (必填) | - | 人员 ID |
| `quality_control` | 1 | 质量控制 |
| `need_rotate_check` | 1 | 旋转检查 |

---

### 删除人脸

`tencent_face_recognition.delete_face`

删除指定人员的人脸。

| 参数 | 说明 |
|------|------|
| `person_id` (必填) | 人员 ID |
| `face_id` (必填) | 要删除的人脸 ID |

---

## 传感器

集成会自动创建以下传感器：

| 传感器 | 说明 |
|--------|------|
| 状态传感器 | 显示连接状态（已连接/未连接/连接错误） |
| 人员传感器 | 每个注册人员一个传感器，显示名称和属性 |

传感器每 5 分钟自动刷新。

## 故障排除

| 问题 | 解决方案 |
|------|----------|
| 配置失败 | 检查 Secret ID/Key 是否正确，确认以 AKID 开头 |
| 图片处理失败 | 确保 URL 可访问或本地路径正确，图片格式为 JPG/PNG/BMP/GIF，大小不超过 10MB |
| 人脸检测失败 | 确保图片中包含清晰的人脸，人脸尺寸不小于 34 像素 |
| API 调用失败 | 检查账户余额和 API 调用配额 |
| 限流错误 | 降低调用频率，插件已内置重试机制 |

在"开发者工具" → "日志"中开启调试日志可获取更详细的错误信息。

## 许可证

MIT 许可证
