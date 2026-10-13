# -*- coding：utf-8 -*-
from .sqlcli import Base
from sqlalchemy.orm import relationship
from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, Float, func
from sqlalchemy.dialects.mysql import LONGTEXT
from datetime import datetime, timedelta, timezone


def beijing_now():
    return datetime.now(timezone.utc) + timedelta(hours=8)



class User(Base):
    __tablename__ = "User"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="engineer", comment="角色: admin/engineer")
    job = Column(Text, default=None, comment="\u5de5\u4f5c\u63cf\u8ff0")
    phone_number = Column(String(64), index=True, comment="\u7535\u8bdd\u53f7\u7801")
    nickname = Column(String(100), default=None, comment="真实姓名")
    create_time = Column(DateTime, default=lambda: beijing_now())
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, default=False, comment="该条记录是否已被删除")


class Tenant(Base):
    __tablename__ = "Tenant"
    id = Column(Integer, primary_key=True, index=True)
    tenantname = Column(String(50), nullable=False)
    job = Column(Text, default=None, comment="\u5de5\u4f5c\u63cf\u8ff0")
    phone_number = Column(String(64), index=True, comment="\u7535\u8bdd\u53f7\u7801")
    nickname = Column(String(100), default=None, comment="真实姓名")
    create_time = Column(DateTime, default=lambda: beijing_now())
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, default=False, comment="该条记录是否已被删除")


class Device2UserInfo(Base):
    __tablename__ = "Device2UserInfo"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(64), index=True, comment="设备id")
    location = Column(String(64), comment="当前位置（经纬度）")
    engineer_id = Column(Integer, nullable=True, comment="对应的工程师id")
    create_time = Column(String(50), comment="创建时间", default=None)
    update_time = Column(String(50), comment="更新时间", default=None)
    is_delete = Column(Boolean, default=False, comment="该条记录是否已被删除")
    

class SourceList(Base):
    __tablename__ = "SourceList"
    
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(30), index=True, comment="资源类型，TTS | LLM | ASR")
    reference_id = Column(Integer, index=True, comment="映射的资源id")
    user_id = Column(Integer, index=True, comment="持有资源的用户id")
    is_default = Column(Boolean, index=True, default=False, comment="是否是默认资源")
    create_time = Column(DateTime, default=lambda: beijing_now())
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, index=True, default=False, comment="该条记录是否已被删除")


class TTSFactories(Base):
    """
    TTS
    """
    __tablename__ = "TTSFactories"
    
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(30), index=True, comment="接口类型：generic|openai")
    url = Column(String(256), default=None, comment="接口地址")
    desc = Column(String(256), default=None, comment="简短的音色描述")
    tag = Column(String(64), index=True, comment="音色标签")
    voice = Column(String(128), index=True, comment="音色名称")
    apikey = Column(String(128), comment="请求密钥")
    create_time = Column(DateTime, default=lambda: beijing_now())
    additional_param = Column(JSON, comment="大模型参数", default="{}")
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, index=True, default=False, comment="该条记录是否已被删除")
    

class LLMFactories(Base):
    """
    LLM
    """
    __tablename__ = "LLMFactories"
    
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(30), index=True, comment="接口类型：generic|openai")
    url = Column(String(256), default=None, comment="接口地址")
    apikey = Column(String(128), comment="请求密钥")
    desc = Column(String(256), default=None, comment="大模型描述")
    params = Column(JSON, comment="大模型参数")
    create_time = Column(DateTime, default=lambda: beijing_now())
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, index=True, default=False, comment="该条记录是否已被删除")


class ASRFactories(Base):
    """
    ASR
    """
    __tablename__ = "ASRFactories"
    
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(30), index=True, comment="接口类型：qwen3_asr|sensevoice")
    url = Column(String(256), default=None, comment="接口地址")
    desc = Column(String(256), default=None, comment="简短描述")
    params = Column(JSON, comment="语音识别参数")
    apikey = Column(String(128), comment="请求密钥")
    create_time = Column(DateTime, default=lambda: beijing_now())
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, index=True, default=False, comment="该条记录是否已被删除")
    

class FigureFactories(Base):
    """
    数字形象管理
    """
    __tablename__ = "FigureFactories"
    
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(30), index=True, comment="BACKGROUND|FIGURE")
    name = Column(String(256), comment="资源名称")
    savename = Column(String(256), comment="资源解压后的保存名称（可能为目录|文件名称）")
    filename = Column(String(256), default=None, comment="压缩包文件名")
    author = Column(String(128), comment="作者")
    version = Column(String(128), comment="当前版本号")
    desc = Column(Text, default=None, comment="形象描述")
    resolution = Column(JSON, default="[]", comment="支持的分辨率")
    create_time = Column(DateTime, default=lambda: beijing_now())
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, index=True, default=False, comment="该条记录是否已被删除")
    

class TTScache(Base):
    """
    TTS缓存表，采用md5加密合成文本
    """
    __tablename__ = "TTScache"
    
    id = Column(Integer, primary_key=True, index=True)
    tag = Column(String(64), index=True, comment="tts推理后端名称")
    voice = Column(String(64), index=True, comment="音色")
    sec_text = Column(String(512), index=True, comment="加密文本")
    format = Column(String(32), index=True, comment="音频格式，如pcm/wav/mp3等")
    speed = Column(Float, comment="语速")
    sr = Column(Integer, comment="采样率", default=16000, index=True)
    speed = Column(Float, comment="语速", default=1.0, index=True)
    save_path = Column(String(1024), comment="缓存路径")
    recog_text = Column(Text(length=65535, collation='utf8mb4_general_ci'), comment="输入文本")
    create_time = Column(DateTime, default=lambda: beijing_now())
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, index=True, default=False, comment="该条记录是否已被删除")


class AgentSessionManagement(Base):
    """
    管理agent生命周期
    """
    __tablename__ = "AgentSessionManagement"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(88), index=True, comment="session id")
    user_id = Column(Integer, index=True, comment="user id")
    agent_id = Column(Integer, comment="agent id")
    asr_id = Column(Integer, comment="asr id")
    tts_id = Column(Integer, comment="tts id")
    dialogue_history = Column(JSON, default=None, comment="对话记录")
    create_time = Column(DateTime, default=lambda: beijing_now())
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, index=True, default=False, comment="该条记录是否已被删除")


class DigitalHumanChatTemplate(Base):
    """
    数字人对话模板
    """
    __tablename__ = "DigitalHumanChatTemplate"
    
    id = Column(Integer, primary_key=True, index=True)
    module_path = Column(String(256), comment="对话模板路径")
    desc = Column(String(256), default=None, comment="简短的模板描述")
    create_time = Column(DateTime, default=lambda: beijing_now())
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, index=True, default=False, comment="该条记录是否已被删除")