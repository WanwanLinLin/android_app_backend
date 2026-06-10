from pydantic import BaseModel


class CreateOrConfirmTaskModel(BaseModel):
    device_id: str
    location: str
    event_description: str
