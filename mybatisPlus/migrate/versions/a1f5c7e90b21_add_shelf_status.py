"""add shelf status to resource pool tables

为四类资源池表增加独立的上下架状态列 status（active | off_shelf），
与 is_delete 语义分离：下架只停止新增绑定，存量绑定与默认引用保持可用。

手写迁移（不走 autogenerate）：autogenerate 会试图 drop ORM 已删但数据保留的
遗留表 HandleTaskRecord / EngineerInfo，必须规避。

列本身可空、无 server_default，存量行为 NULL；应用层读取一律按 active 兜底
（判定下架用 status == 'off_shelf'，不能用 status != 'active'）。
建列后额外做一次 UPDATE 把存量 NULL 归一为 active，避免后续查询依赖兜底逻辑。

Revision ID: a1f5c7e90b21
Revises: 
Create Date: 2026-10-16
"""
from alembic import op
import sqlalchemy as sa

revision = "a1f5c7e90b21"
down_revision = None
branch_labels = None
depends_on = None

TABLES = ("TTSFactories", "LLMFactories", "ASRFactories", "DigitalHumanChatTemplate")


def _has_column(bind, table, column):
    return column in sa.inspect(bind).get_columns(table)


def upgrade():
    bind = op.get_bind()
    for t in TABLES:
        if not _has_column(bind, t, "status"):
            op.add_column(t, sa.Column("status", sa.String(length=20),
                                       nullable=True,
                                       comment="上下架状态：active=在售 | off_shelf=已下架（NULL 视为 active）"))
            op.create_index(f"ix_{t}_status", t, ["status"])
        # 存量归一：历史行 status 为 NULL，统一置为 active
        bind.execute(sa.text(f"UPDATE {t} SET status = 'active' WHERE status IS NULL"))


def downgrade():
    bind = op.get_bind()
    for t in TABLES:
        if _has_column(bind, t, "status"):
            try:
                op.drop_index(f"ix_{t}_status", table_name=t)
            except Exception:
                pass
            op.drop_column(t, "status")
