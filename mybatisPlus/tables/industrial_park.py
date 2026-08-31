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


class Device2UserInfo(Base):
    __tablename__ = "Device2UserInfo"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(64), index=True, comment="设备id")
    location = Column(String(64), comment="当前位置（经纬度）")
    engineer_id = Column(Integer, nullable=True, comment="对应的工程师id")
    create_time = Column(String(50), comment="创建时间", default=None)
    update_time = Column(String(50), comment="更新时间", default=None)
    is_delete = Column(Boolean, default=False, comment="该条记录是否已被删除")
    

class HandleTaskRecord(Base):
    __tablename__ = "HandleTaskRecord"
    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String(64), index=True, comment="本次任务的主题")
    device_id = Column(String(64), index=True, comment="设备id")
    task_id = Column(String(128), index=True, comment="任务id")
    location = Column(String(64), comment="事件位置（经纬度）")
    event_description = Column(Text(length=65535, collation='utf8mb4_general_ci'), default=None, comment="上报事件描述")
    solution = Column(Text(length=65535, collation='utf8mb4_general_ci'), default=None, comment="解决方案")
    status = Column(Integer, default=0, comment="任务状态，0:待确认;1:已确认;2:已经到达现场;3:已完成;4.已上传完成照片;-1:失败")
    ack = Column(Boolean, default=False, comment="是否确认提交该解决方案工单")
    exclude_engineer_id_list = Column(String(50), default=None, comment="排除的处理人列表")
    engineer_id = Column(Integer, nullable=True, comment="待解决问题的工程师id")
    report_engineer_id = Column(Integer, nullable=True, comment="上报问题的工程师id")
    create_time = Column(String(50), comment="创建时间", default=None)
    update_time = Column(String(50), comment="更新时间", default=None)
    photo_path = Column(String(500), default="")
    completed_photo_path = Column(String(500), default="")
    process_msg = Column(JSON, default=[], nullable=True, comment="任务处理时产生的中间消息")
    is_delete = Column(Boolean, default=False, comment="该条记录是否已被删除")
    

class EngineerInfo(Base):
    __tablename__ = "EngineerInfo"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), index=True, comment="用户名称")
    job = Column(Text(length=65535, collation='utf8mb4_general_ci'), default=None, comment="工作描述")
    phone_number = Column(String(64), index=True, comment="电话号码")
    create_time = Column(String(50), comment="创建时间", default=None)
    update_time = Column(String(50), comment="更新时间", default=None)
    is_free = Column(Boolean, default=True, comment="是否空闲")
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
