from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta, timezone
from .sqlcli2 import Base_Work_Order


def beijing_now():
    return datetime.now(timezone.utc) + timedelta(hours=8)

class User(Base_Work_Order):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="engineer", comment="角色: admin/engineer")
    job = Column(Text, default=None, comment="\u5de5\u4f5c\u63cf\u8ff0")
    phone_number = Column(String(64), index=True, comment="\u7535\u8bdd\u53f7\u7801")
    nickname = Column(String(100), default=None, comment="真实姓名")
    created_at = Column(DateTime, default=lambda: beijing_now())
    updated_at = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    tasks = relationship("Task", back_populates="owner")


class ApiKey(Base_Work_Order):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True, index=True)
    key_prefix = Column(String(20), nullable=False)
    hashed_key = Column(String(255), nullable=False)
    name = Column(String(100), default="")
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=lambda: beijing_now())
    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User")


class Device2UserInfo(Base_Work_Order):
    __tablename__ = "Device2UserInfo"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(64), index=True, comment="\u8bbe\u5907id")
    location = Column(String(64), comment="\u5f53\u524d\u4f4d\u7f6e\uff08\u7ecf\u7eac\u5ea6\uff09")
    engineer_id = Column(Integer, nullable=True, comment="\u5bf9\u5e94\u7684\u5de5\u7a0b\u5e08\u7528\u6237id")
    create_time = Column(String(50), default=None, comment="\u521b\u5efa\u65f6\u95f4")
    update_time = Column(String(50), default=None, comment="\u66f4\u65b0\u65f6\u95f4")
    is_delete = Column(Boolean, default=False, comment="\u8be5\u6761\u8bb0\u5f55\u662f\u5426\u5df2\u88ab\u5220\u9664")


class Task(Base_Work_Order):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(36), unique=True, index=True, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    photo_path = Column(String(500), default="")
    completed_photo_path = Column(String(500), default="")
    status = Column(Integer, default=0)
    assignee_ids = Column(String(500), default="[]")
    task_type = Column(String(50), default="", comment="任务类型")
    created_at = Column(DateTime, default=lambda: beijing_now())
    updated_at = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="tasks")


class NfcFloor(Base_Work_Order):
    __tablename__ = "nfc_floors"
    id = Column(Integer, primary_key=True, index=True)
    nfc_code = Column(String(64), unique=True, index=True, nullable=False, comment="NFC编码")
    floor_name = Column(String(100), nullable=False, comment="楼层名称")
    created_at = Column(DateTime, default=lambda: beijing_now())
    updated_at = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())


class InspectionTask(Base_Work_Order):
    __tablename__ = "inspection_tasks"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(15), unique=True, index=True, nullable=False, comment="15位唯一标识")
    title = Column(String(200), nullable=False, comment="巡检任务名称")
    assignee_ids = Column(String(500), default="[]", comment="指定人员ID列表")
    floor_ids = Column(String(500), default="[]", comment="选中楼层ID列表")
    start_time = Column(String(50), default="", comment="巡检开始时间")
    status = Column(Integer, default=0, comment="0:未开始;1:进行中;2:已完成;3:超时")
    process_msg = Column(Text, default="[]", comment="记录巡检过的楼层及打卡时间")
    checked_floor_ids = Column(String(500), default="[]", comment="已巡检楼层ID列表")
    created_at = Column(DateTime, default=lambda: beijing_now())
    updated_at = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User")
