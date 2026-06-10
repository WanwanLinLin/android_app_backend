# -*- coding：utf-8 -*-
from .sqlcli import Base
from sqlalchemy.orm import relationship
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, Float, func
from sqlalchemy.dialects.mysql import LONGTEXT
from datetime import datetime


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
    status = Column(Integer, default=0, comment="任务状态，0:待确认;1:已确认;2:已经到达现场;3已上传现场照片;4:已完成;5.已上传完成照片;-1:失败")
    ack = Column(Boolean, default=False, comment="是否确认提交该解决方案工单")
    exclude_engineer_id_list = Column(String(50), default=None, comment="排除的处理人列表")
    engineer_id = Column(Integer, nullable=True, comment="待解决问题的工程师id")
    report_engineer_id = Column(Integer, nullable=True, comment="上报问题的工程师id")
    create_time = Column(String(50), comment="创建时间", default=None)
    update_time = Column(String(50), comment="更新时间", default=None)
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

