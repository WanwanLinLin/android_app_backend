"""Tenant.user_id ownership column (no FK)

Tenant 表新增 user_id 列，显式建立「后台管理员 —— 业务租户」的归属关系
（此前两表仅靠初始化迁移按 tenantname == username 1:1 播种 implicitly 对应）。

项目约定：不使用数据库外键约束，归属完整性由应用层保证
（create/update 租户时校验 user_id 对应的管理员真实存在，见 tenant_orm）。

存量数据回填：按 Tenant.tenantname == User.username 回填 user_id；
无法匹配的（如手工创建、无对应管理员的租户）保持 NULL。

注意：本迁移刻意剔除了 autogenerate 带入的噪音——
EngineerInfo / HandleTaskRecord 是移除巡检工单代码时有意保留数据的
遗留表（ORM 已删、表还在），TTScache.recog_text 的类型差异同理，
均不在本迁移处理。

Revision ID: 828424c376cd
Revises: 02ea64152c9f
Create Date: 2026-10-14 17:10:24.592971

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '828424c376cd'
down_revision: Union[str, None] = '02ea64152c9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('Tenant', sa.Column(
        'user_id', sa.Integer(), nullable=True,
        comment='归属的后台管理员id（User.id，本项目不使用外键约束）'))
    # 存量回填：历史 Tenant 由 User 按同名播种，按 tenantname == username 挂回管理员
    op.execute(
        """
        UPDATE `Tenant` t
        JOIN `User` u ON u.`username` = t.`tenantname`
        SET t.`user_id` = u.`id`
        WHERE t.`user_id` IS NULL
        """
    )
    op.create_index(op.f('ix_Tenant_user_id'), 'Tenant', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_Tenant_user_id'), table_name='Tenant')
    op.drop_column('Tenant', 'user_id')
