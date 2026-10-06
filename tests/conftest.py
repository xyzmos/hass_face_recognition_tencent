import sys, types, os
_pkg = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "custom_components"))
sys.path.insert(0, _pkg)

def _mod(name):
    m = types.ModuleType(name); sys.modules[name] = m; return m

ha = _mod("homeassistant"); ha.__path__ = []
exc = _mod("homeassistant.exceptions")
class HomeAssistantError(Exception): pass
class ConfigEntryNotReady(HomeAssistantError): pass
class ConfigEntryAuthFailed(HomeAssistantError): pass
class ServiceValidationError(HomeAssistantError): pass
for n in ("HomeAssistantError","ConfigEntryNotReady","ConfigEntryAuthFailed","ServiceValidationError"):
    setattr(exc,n,globals()[n])

const = _mod("homeassistant.const"); const.CONF_NAME="name"
ce = _mod("homeassistant.config_entries")
class ConfigEntry:
    def __init__(self,**k): self.__dict__.update(k); self.runtime_data=None; self.options={}; self.data={}
    def __class_getitem__(cls,item): return cls
class ConfigFlow:
    def __init_subclass__(cls, **kw): super().__init_subclass__()
class OptionsFlow: pass
ce.ConfigEntry=ConfigEntry; ce.ConfigFlow=ConfigFlow; ce.OptionsFlow=OptionsFlow; ce.ConfigFlowResult=dict

core = _mod("homeassistant.core")
core.HomeAssistant=object; core.ServiceCall=object; core.ServiceResponse=dict
core.callback=lambda f: f

helpers = _mod("homeassistant.helpers"); helpers.__path__=[]
cv = _mod("homeassistant.helpers.config_validation"); cv.string=str; cv.entity_id=lambda v:v; cv.positive_int=int
svc = _mod("homeassistant.helpers.service")
class SupportsResponse: NONE="none"; OPTIONAL="optional"; ONLY="only"
svc.SupportsResponse=SupportsResponse
sel = _mod("homeassistant.helpers.selector")
class _S:
    def __init__(self,*a,**k): pass
sel.SelectSelector=sel.EntitySelector=sel.NumberSelector=sel.TextSelector=_S
sel.SelectSelectorConfig=sel.EntitySelectorConfig=sel.NumberSelectorConfig=sel.TextSelectorConfig=_S
class _M: pass
sel.SelectSelectorMode=_M; sel.SelectSelectorMode.DROPDOWN="dropdown"; sel.SelectSelectorMode.LIST="list"
sel.NumberSelectorMode=_M; sel.NumberSelectorMode.BOX="box"; sel.NumberSelectorMode.SLIDER="slider"
sel.TextSelectorType=_M; sel.TextSelectorType.TEXT="text"; sel.TextSelectorType.PASSWORD="password"
dr = _mod("homeassistant.helpers.device_registry")
class DeviceInfo(dict):
    def __init__(self,**k): super().__init__(k)
dr.DeviceInfo=DeviceInfo
ent = _mod("homeassistant.helpers.entity")
class EntityCategory: DIAGNOSTIC="diagnostic"; CONFIG="config"
ent.EntityCategory=EntityCategory
ep = _mod("homeassistant.helpers.entity_platform"); ep.AddEntitiesCallback=object
uc = _mod("homeassistant.helpers.update_coordinator")
class UpdateFailed(Exception): pass
class DataUpdateCoordinator:
    def __init__(self,*a,**k): self.data=None; self.last_update_success=False; self.last_exception=None
uc.UpdateFailed=UpdateFailed; uc.DataUpdateCoordinator=DataUpdateCoordinator; uc.CoordinatorEntity=object

comp = _mod("homeassistant.components"); comp.__path__=[]
ws = _mod("homeassistant.components.websocket_api")
ws.websocket_command=lambda *a,**k:(lambda f:f); ws.async_response=lambda f:f
ws.ActiveConnection=object; ws.async_register_command=lambda h,c:None
cam = _mod("homeassistant.components.camera")
async def _agi(h,e): return None
cam.async_get_image=_agi
sen = _mod("homeassistant.components.sensor")
class SensorEntity: pass
sen.SensorEntity=SensorEntity
diag = _mod("homeassistant.components.diagnostics")
def _redact(data, keys):
    return {k: ("***" if k in keys else v) for k,v in (data or {}).items()}
diag.async_redact_data=_redact
