# 腾讯云人脸识别Home Assistant插件

这是一个基于腾讯云人脸识别API的Home Assistant插件，提供了人脸搜索功能。

## 功能特性

- **人脸搜索**：支持通过图片URL或本地文件路径搜索人脸，返回匹配的人员信息

## 安装

1. 将`custom_components/tencent_face_recognition`目录复制到Home Assistant的`custom_components`目录下
2. 重启Home Assistant
3. 在"配置" -> "集成"中点击"+"添加集成
4. 搜索"腾讯云人脸识别"并点击
5. 输入您的腾讯云凭据和配置信息

## 配置

### 必需配置

- **Secret ID**：腾讯云API的Secret ID
- **Secret Key**：腾讯云API的Secret Key

### 可选配置

- **人员库ID**：默认使用的人员库ID（默认值：Hass）
- **区域**：腾讯云服务区域（默认值：ap-shanghai）
- **名称**：集成名称（默认值：腾讯云人脸识别）

## 服务

插件提供以下服务，可以通过开发者工具中的"服务"选项卡调用：

### 人脸搜索

**服务名称**：`tencent_face_recognition.face_search`

**描述**：在人员库中搜索人脸

**参数**：

- `image_url`（可选）：要搜索的图片URL
- `image_path`（可选）：要搜索的本地图片路径
- `person_group_id`（可选）：要搜索的人员库ID，留空使用默认人员库
- `max_face_num`（可选，默认1）：最多处理的人脸数量
- `min_face_size`（可选，默认34）：最小人脸尺寸（像素）
- `max_user_num`（可选，默认5）：最多返回的匹配人员数量
- `quality_control`（可选，默认1）：是否进行质量控制（0：不控制，1：低质量控制，2：高质量控制）
- `need_rotate_check`（可选，默认1）：是否进行旋转检查（0：不检查，1：检查）
- `face_match_threshold`（可选，默认60.0）：人脸匹配阈值（0-100）

**示例**：

``` yaml
action: tencent_face_recognition.face_search
response_variable: face_recognition_result_raw
data:
  group_id: Hass
  face_match_threshold: 60
  min_face_size: 34
  max_face_num: 10
  max_user_num: 10
  image_path: /config/www/camera/face.jpg
```



```yaml
service: tencent_face_recognition.face_search
data:
  image_url: "https://example.com/face.jpg"
  group_id: "Hass"
```

## 故障排除

### 常见问题

1. **配置失败**：请检查腾讯云凭据是否正确，以及是否有足够的权限
2. **图片处理失败**：请确保图片URL可访问或本地文件路径正确
3. **人脸检测失败**：请确保图片中包含清晰的人脸，且人脸尺寸足够大
4. **API调用失败**：请检查腾讯云账户余额是否充足，以及API调用配额是否足够

### 日志查看

在Home Assistant的"开发者工具" -> "日志"中查看插件日志，可以获取更多错误信息。

## 贡献

欢迎提交Issue和Pull Request来改进这个插件。

## 许可证

MIT许可证