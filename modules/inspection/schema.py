from pydantic import BaseModel


class InfoModel(BaseModel):
    task_id: str
    

class StartModel(BaseModel):
    task_id: str
    device_id: str
    

class CheckInModel(BaseModel):
    task_id: str
    nfc_code: str
    device_id: str