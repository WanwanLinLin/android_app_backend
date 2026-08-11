from pydantic import BaseModel


class SaveDefaultSourceConfig(BaseModel):
    username: str
    llm_id: int
    tts_id: int
    asr_id: int