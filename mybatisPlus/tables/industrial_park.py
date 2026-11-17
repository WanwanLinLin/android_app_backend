# -*- coding：utf-8 -*-
from .sqlcli import Base
from sqlalchemy.orm import relationship
# 本项目不使用数据库外键约束：请勿在此引入 ForeignKey / create_foreign_key，
# 表间引用完整性一律由应用层校验保证。
from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text, Float, func
from sqlalchemy.dialects.mysql import LONGTEXT
from datetime import datetime, timedelta, timezone


def beijing_now():
    return datetime.now(timezone.utc) + timedelta(hours=8)


# 资源池上下架状态（与 is_delete 语义严格分离）：
#   active     —— 在售：可绑定到租户、可设为默认
#   off_shelf  —— 已下架：禁止新增绑定与设为默认，但已绑定的存量照常可用
# 存量行该列可能为 NULL，一律按 active 处理（读取处用 COALESCE 兜底），
# 因此判定下架必须是 status == "off_shelf"，不能写 status != "active"。
STATUS_ACTIVE = "active"
STATUS_OFF_SHELF = "off_shelf"


def shelf_status():
    """四类资源表共用的 status 列定义（列对象需每表独立创建，故用工厂函数）。"""
    return Column(String(20), index=True, default=STATUS_ACTIVE,
                  comment="上下架状态：active=在售 | off_shelf=已下架（NULL 视为 active）")




class User(Base):
    """后台管理员账号表。

    仅承担两件事：登录鉴权、以及 Tenant（业务租户）的生命周期管理。
    业务归属（资源、会话、数字人配置等）一律挂在 Tenant 上，不再使用本表 id。
    """
    __tablename__ = "User"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="admin", comment="角色: admin/operator")
    job = Column(Text, default=None, comment="\u5de5\u4f5c\u63cf\u8ff0")
    phone_number = Column(String(64), index=True, comment="\u7535\u8bdd\u53f7\u7801")
    nickname = Column(String(100), default=None, comment="真实姓名")
    create_time = Column(DateTime, default=lambda: beijing_now())
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, default=False, comment="该条记录是否已被删除")


class Tenant(Base):
    """业务租户表——数字人运行时的实际归属主体。

    终端（设备/数字人）以 tenantname 标识身份，其可用资源、默认配置、
    agent 会话等均通过 tenant_id 关联到本表。
    """
    __tablename__ = "Tenant"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, default=None, comment="归属的后台管理员id（User.id，本项目不使用外键约束）")
    tenantname = Column(String(50), unique=True, index=True, nullable=False, comment="租户名，终端业务身份标识")
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
    tenant_id = Column(Integer, index=True, comment="持有资源的租户id（Tenant.id）")
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
    # 2026-10-22: additional_param 改名 params，与 LLM/ASR 资源表及个性插件 config 统一键位
    params = Column(JSON, comment="音色参数", default="{}")
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, index=True, default=False, comment="该条记录是否已被删除")
    status = shelf_status()
    

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
    status = shelf_status()


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
    status = shelf_status()
    

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
    tenant_id = Column(Integer, index=True, comment="tenant id（Tenant.id）")
    agent_id = Column(Integer, comment="agent id")
    asr_id = Column(Integer, comment="asr id")
    tts_id = Column(Integer, comment="tts id")
    dialogue_history = Column(JSON, default=None, comment="对话记录")
    create_time = Column(DateTime, default=lambda: beijing_now())
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, index=True, default=False, comment="该条记录是否已被删除")


class BasePlugin(Base):
    """基础插件登记表——对应 utils/providers/{tts|asr|llm} 下的插件代码文件。

    插件本体是磁盘上的代码文件（一个插件一个文件，排除 base.py / __init__.py），
    本表只做「登记 + 元数据 + 上下架」：
      - 列表接口会自动扫描插件目录，把磁盘上新出现、尚未登记的文件自动登记为在售；
      - 管理员在后台可修改展示信息（desc / default_config 默认参数模板）、
        上下架、删除（注销登记——仅移除登记并连带禁用，不动磁盘代码文件）；
      - 新增 = 登记一个磁盘上已存在但尚未登记的文件（代码文件本身不能通过后台创建）。

    default_config 是给个性插件作者预填的默认参数模板（如 {"temperature": 0.7}），
    与运行时无关——运行时一律以个性插件自带的完整 config 为准。

    下架（status=off_shelf）语义为严格全面禁用：基于该基础插件的个性插件
    对普通用户不可见、不可绑定，已绑定租户的会话运行时也会直接拒绝。
    """
    __tablename__ = "BasePlugin"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(10), index=True, nullable=False, comment="插件类别：TTS | ASR | LLM")
    name = Column(String(64), index=True, nullable=False, comment="插件名（不含 .py 的文件名，运行时 import 用）")
    desc = Column(String(256), default=None, comment="插件描述")
    default_config = Column(JSON, default=None, comment="默认参数模板（创建个性插件时预填），与运行时无关")
    create_time = Column(DateTime, default=lambda: beijing_now())
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, index=True, default=False, comment="该条记录是否已被删除")
    status = shelf_status()


class CustomPlugin(Base):
    """个性插件——普通用户在某个基础插件之上定义的私有配置。

    config 为完整自带配置（type/url/apikey/params 等，
    结构同对应 Factories 行），创建时从基础插件的 default_config 预填、由用户改定；
    运行时直接使用这份 config，基础插件后续修改不影响个性插件。

    运行时解析规则：provider 文件名取关联基础插件的 name（写入 config 的
    type 字段；TTS 另写 tag），保证既有 importlib 链路无需改动。
    基础插件已被删除/下架时，个性插件一律不可用（严格全面禁用，含存量绑定）。

    owner_id 指向 User.id（本项目不使用外键）：个性插件**严格私有**，恒为创建者本人。
    （2026-10-22 取消"平台归属/共享"概念——存量 Factories 迁移行已统一归属主账号
    hopesen，不再使用 owner_id=NULL。列仍允许 NULL 仅为兼容历史，运行时不产生 NULL 行。）
    仅创建者本人可见可改可删可绑；admin 列表可见全部但不代改别人的插件。
    """
    __tablename__ = "CustomPlugin"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, comment="个性插件名称")
    category = Column(String(10), index=True, nullable=False, comment="插件类别：TTS | ASR | LLM")
    base_plugin_id = Column(Integer, index=True, default=None, comment="所属基础插件 id（BasePlugin.id，无外键）")
    desc = Column(String(256), default=None, comment="简短描述")
    config = Column(JSON, default=None, comment="完整自带配置（结构同 Factories 行：type/url/apikey/params 等）")
    owner_id = Column(Integer, index=True, default=None, comment="创建者 User.id（严格私有，恒为本人）")
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
    content = Column(LONGTEXT, default=None, comment="模板协议/配置文档全文（JSON 文本），后台查看弹窗展示")
    create_time = Column(DateTime, default=lambda: beijing_now())
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, index=True, default=False, comment="该条记录是否已被删除")
    status = shelf_status()

class PluginTestTask(Base):
    """LLM 自动化测试任务——批量测试 LLM 个性插件的联通性与输出质量。

    一次运行 = 对 plugin_ids 中每个插件，在同一会话里按 test_prompts
    顺序逐轮提问（最多 10 轮），收集全部对话后按 rules 校验（contains /
    not_contains / regex / llm_judge，其中 llm_judge 把完整对话记录交给
    config.yaml generic_llm 的判定模型），结果汇总成报告（last_report）
    并支持导出 PDF 下载。

    归属沿用个性插件的严格私有口径：owner_id 恒为创建者本人，仅本人
    可改/删/运行；admin 列表可见全部（治理用途）。

    定时运行（每日重复）：schedule_enabled=True 且 schedule_status=
    pending 且 schedule_time 到点后，由后台调度器领取（原子置 running）
    执行一次，完成后 schedule_time 自动顺延一天并回到 pending；关闭
    定时则置 canceled。schedule_time 为 naive 北京时间，与 beijing_now()
    同口径。

    钉钉播报：notify_dingtalk 控制定时运行的结果是否推送到钉钉群
    （地址 config.yaml THIRD_PARTY_SERVICES -> subscribe_address，
    播报逻辑见 utils/plugin_test/notify）。只有定时运行会播——手动
    「立即运行 / 一键测试」是调试行为，不刷群。
    """
    __tablename__ = "PluginTestTask"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, comment="任务名称")
    desc = Column(String(256), default=None, comment="任务描述")
    plugin_ids = Column(JSON, default=None, comment="待测 LLM 个性插件 id 列表（CustomPlugin.id）")
    test_prompt = Column(Text, default=None, comment="旧版单轮测试问题（已由 test_prompts 取代，兼容保留）")
    test_prompts = Column(JSON, default=None, comment="多轮测试问题列表（同一会话按序提问，最多10轮）")
    rules = Column(JSON, default=None, comment="结果校验规则列表 [{type,value}]，针对全部对话内容校验，空=只测联通性")
    schedule_enabled = Column(Boolean, default=False, comment="是否启用定时运行（每天重复）")
    schedule_time = Column(DateTime, default=None, comment="下次计划运行时间（北京时间；每次跑完自动顺延一天）")
    schedule_status = Column(String(16), default=None, comment="定时状态：pending|running|canceled（done 为旧一次性遗留）")
    notify_dingtalk = Column(Boolean, default=True, comment="定时运行结果是否播报到钉钉群（手动运行一律不播；地址见 config.yaml subscribe_address）")
    last_run_time = Column(DateTime, default=None, comment="最近一次运行时间")
    last_trigger = Column(String(16), default=None, comment="最近一次触发方式：manual|scheduled")
    last_summary = Column(JSON, default=None, comment="最近一次结果汇总 {total,ok,fail}")
    last_report = Column(JSON, default=None, comment="最近一次完整测试结果（含各插件输出与校验明细）")
    owner_id = Column(Integer, index=True, default=None, comment="创建者 User.id（严格私有，恒为本人）")
    create_time = Column(DateTime, default=lambda: beijing_now())
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, index=True, default=False, comment="该条记录是否已被删除")


class PluginTestRun(Base):
    """LLM 自动化测试的历史运行记录——每次运行（手动/定时）留档一条。

    PluginTestTask.last_report 只保留「最近一次」，本表负责全量历史：
    按任务分页查看、回看任意一次的完整报告、下载对应 PDF。
    report 是运行时刻的完整快照（含当时的规则/问题/逐轮输出），任务
    配置后续被改也不影响历史记录的回看。task_name 冗余存储，任务删除
    后历史仍可追溯（删任务不删历史）。
    归属随任务（严格私有）：owner_id 与任务创建者一致；admin 可见全部。
    """
    __tablename__ = "PluginTestRun"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, index=True, nullable=False, comment="所属 PluginTestTask.id（无外键约束）")
    task_name = Column(String(128), default=None, comment="任务名称快照（任务删除后历史可读）")
    trigger = Column(String(16), default=None, comment="触发方式：manual|scheduled")
    run_time = Column(DateTime, index=True, default=lambda: beijing_now(), comment="运行时间（北京时间）")
    summary = Column(JSON, default=None, comment="结果汇总 {total,ok,fail}")
    report = Column(JSON, default=None, comment="该次完整测试报告快照")
    owner_id = Column(Integer, index=True, default=None, comment="任务创建者 User.id（随任务）")
    create_time = Column(DateTime, default=lambda: beijing_now())
