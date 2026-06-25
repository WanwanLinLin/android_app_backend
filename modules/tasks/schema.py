from pydantic import BaseModel


class CreateOrConfirmTaskModel(BaseModel):
    device_id: str
    location: str
    event_description: str
    

class GetTaskDetail(BaseModel):
    task_id: str
    
class GetTaskList(BaseModel):
    device_id: str


class SubmitTaskMsgModel(BaseModel):
    task_id: str
    device_id: str
    location: str
    event_description: str