"""腾讯云人脸识别插件常量定义"""

DOMAIN = "hass_face_recognition_tencent"
PLATFORMS = ["sensor"]
MANUFACTURER = "Tencent Cloud"

CONF_SECRET_ID = "secret_id"
CONF_SECRET_KEY = "secret_key"
CONF_REGION = "region"
CONF_PERSON_GROUP_ID = "person_group_id"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_REGION = "ap-shanghai"
DEFAULT_PERSON_GROUP_ID = "Hass"
DEFAULT_MAX_FACE_NUM = 1
# 腾讯云 IAI 文档：人脸最小尺寸下限为 20 像素，常用默认 34
DEFAULT_MIN_FACE_SIZE = 34
DEFAULT_MAX_USER_NUM = 5
DEFAULT_QUALITY_CONTROL = 1
DEFAULT_NEED_ROTATE_CHECK = 1
DEFAULT_FACE_MATCH_THRESHOLD = 60.0
DEFAULT_SCAN_INTERVAL = 300  # seconds (5 minutes)
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 86400

SERVICE_FACE_SEARCH = "face_search"
SERVICE_DETECT_FACE = "detect_face"
SERVICE_GET_FACE_ATTRIBUTES = "get_face_attributes"
SERVICE_CREATE_PERSON = "create_person"
SERVICE_DELETE_PERSON = "delete_person"
SERVICE_CREATE_FACE = "create_face"
SERVICE_DELETE_FACE = "delete_face"

ATTR_IMAGE_URL = "image_url"
ATTR_IMAGE_PATH = "image_path"
ATTR_IMAGE_FILE = "image_file"
ATTR_CAMERA_ENTITY_ID = "camera_entity_id"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_GROUP_ID = "group_id"
ATTR_MAX_FACE_NUM = "max_face_num"
ATTR_MIN_FACE_SIZE = "min_face_size"
ATTR_MAX_USER_NUM = "max_user_num"
ATTR_QUALITY_CONTROL = "quality_control"
ATTR_NEED_ROTATE_CHECK = "need_rotate_check"
ATTR_FACE_MATCH_THRESHOLD = "face_match_threshold"
ATTR_PERSON_ID = "person_id"
ATTR_PERSON_NAME = "person_name"
ATTR_GENDER = "gender"
ATTR_FACE_ID = "face_id"
ATTR_PERSON_TAG = "person_tag"

# 事件类型带域名前缀，避免与其它集成冲突；同时保留原事件名做兼容
EVENT_FACE_DETECTED = f"{DOMAIN}_face_detected"
EVENT_FACE_DETECTED_LEGACY = "face_detected"

# Sensor identifiers
SENSOR_STATUS = "status"
SENSOR_PERSON = "person"


def get_entry_value(entry, key, default=None):
    """Get a config value from entry.options with fallback to entry.data."""
    return entry.options.get(key, entry.data.get(key, default))
