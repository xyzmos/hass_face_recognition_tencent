import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components"))
from hass_face_recognition_tencent import api_operations as A
from hass_face_recognition_tencent.retry import should_retry, RetryConfig
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

class FakeClient:
    def __init__(self): self.last=None
    def __getattr__(self,name):
        def f(req):
            self.last=json.loads(req.to_json_string())
            class R: RequestId="req"
            return R()
        return f

def _mk(code):
    e=TencentCloudSDKException(); e.code=code; e.message="m"; return e

def test_create_person_params():
    c=FakeClient()
    A.create_person(c, person_id="p1", person_name="n", group_id="G",
                    image_base64="QUJD", unique_person_control=2, person_tag="t")
    assert c.last["PersonId"]=="p1" and c.last["UniquePersonControl"]==2
    assert c.last["PersonExDescriptionInfos"][0]["PersonExDescription"]=="t"

def test_create_face_threshold_and_images():
    c=FakeClient()
    A.create_face(c, person_id="p1", image_base64="QUJD", face_match_threshold=75.0)
    assert c.last["Images"]==["QUJD"] and c.last["FaceMatchThreshold"]==75.0

def test_delete_face_ids_list():
    c=FakeClient(); A.delete_face(c, person_id="p1", face_id="f9")
    assert c.last["FaceIds"]==["f9"]

def test_retry_classification():
    assert should_retry(_mk("RequestLimitExceeded")) is True
    assert should_retry(_mk("InternalError")) is True
    assert should_retry(_mk("AuthFailure.SignatureFailure")) is False
    assert should_retry(_mk("InvalidParameterValue.PersonIdNotExist")) is False
    assert should_retry(_mk("ResourceUnavailable.InArrears")) is False
