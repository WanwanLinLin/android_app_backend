from pydantic import BaseModel


class UpdateLocationModel(BaseModel):
    device_id: str
    location: str