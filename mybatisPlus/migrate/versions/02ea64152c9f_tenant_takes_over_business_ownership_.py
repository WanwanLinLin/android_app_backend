"""tenant takes over business ownership from user

业务归属主体由 User 切换为 Tenant：
  * SourceList.user_id            -> tenant_id
  * AgentSessionManagement.user_id -> tenant_id
  * Tenant.tenantname 加唯一索引（业务身份标识）
  * User.role 注释语义调整为 admin/operator（User 退为后台管理员）

数据迁移：Tenant 表此前为空，而 SourceList/AgentSessionManagement 的归属列存的是
User.id。为保证既有归属继续有效，先用 User 表按 id 一一对应地播种 Tenant，
再重命名归属列——列值语义即自然变为 Tenant.id，无需改写数值。

注意：本迁移刻意不包含 HandleTaskRecord / EngineerInfo 的删除。
这两张表是移除巡检工单代码时有意保留数据的遗留表（ORM 模型已删），
如需清理请单独走一次明确的删表迁移。

Revision ID: 02ea64152c9f
Revises: b6a0382923b0
Create Date: 2026-10-14 09:56:33.746963

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '02ea64152c9f'
down_revision: Union[str, None] = 'b6a0382923b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. 历史数据中 is_delete 存在 NULL（旧表未写入该列），统一归一为 0，
    #    否则后续按 is_delete=False 过滤会漏掉既有记录。
    op.execute("UPDATE `Tenant` SET `is_delete` = 0 WHERE `is_delete` IS NULL")

    # 1. 用 User 播种 Tenant，保持 id 一一对应，使既有归属列的值继续有效
    op.execute(
        """
        INSERT INTO `Tenant` (id, tenantname, job, phone_number, nickname,
                              create_time, update_time, is_delete)
        SELECT u.`id`, u.`username`, u.`job`, u.`phone_number`, u.`nickname`,
               u.`create_time`, u.`update_time`, COALESCE(u.`is_delete`, 0)
        FROM `User` u
        WHERE NOT EXISTS (SELECT 1 FROM `Tenant` t WHERE t.`id` = u.`id`)
        """
    )

    # 2. 归属列改名（保留数据）
    op.alter_column('SourceList', 'user_id',
                    new_column_name='tenant_id',
                    existing_type=mysql.INTEGER(),
                    existing_nullable=True,
                    existing_comment='持有资源的用户id',
                    existing_server_default=False)
    op.alter_column('SourceList', 'tenant_id',
                    comment='持有资源的租户id（Tenant.id）',
                    existing_type=mysql.INTEGER(),
                    existing_nullable=True)
    # MySQL 重命名列不会同步改索引名，需显式重命名以匹配 ORM 声明
    op.execute("ALTER TABLE `SourceList` RENAME INDEX `ix_SourceList_user_id` TO `ix_SourceList_tenant_id`")

    op.alter_column('AgentSessionManagement', 'user_id',
                    new_column_name='tenant_id',
                    existing_type=mysql.INTEGER(),
                    existing_nullable=True,
                    existing_comment='user id',
                    existing_server_default=False)
    op.alter_column('AgentSessionManagement', 'tenant_id',
                    comment='tenant id（Tenant.id）',
                    existing_type=mysql.INTEGER(),
                    existing_nullable=True)
    op.execute("ALTER TABLE `AgentSessionManagement` RENAME INDEX `ix_AgentSessionManagement_user_id` TO `ix_AgentSessionManagement_tenant_id`")

    # 3. Tenant 名为业务身份标识，加唯一索引
    op.create_index(op.f('ix_Tenant_tenantname'), 'Tenant', ['tenantname'], unique=True)

    # 4. User 语义收窄为后台管理员
    op.alter_column('User', 'role',
                    existing_type=mysql.VARCHAR(length=20, collation='utf8mb4_unicode_ci'),
                    comment='角色: admin/operator',
                    existing_comment='角色: admin/engineer',
                    existing_nullable=True)


def downgrade() -> None:
    op.alter_column('User', 'role',
                    existing_type=mysql.VARCHAR(length=20, collation='utf8mb4_unicode_ci'),
                    comment='角色: admin/engineer',
                    existing_comment='角色: admin/operator',
                    existing_nullable=True)

    op.drop_index(op.f('ix_Tenant_tenantname'), table_name='Tenant')

    op.execute("ALTER TABLE `AgentSessionManagement` RENAME INDEX `ix_AgentSessionManagement_tenant_id` TO `ix_AgentSessionManagement_user_id`")
    op.alter_column('AgentSessionManagement', 'tenant_id',
                    new_column_name='user_id',
                    existing_type=mysql.INTEGER(),
                    existing_nullable=True,
                    existing_comment='tenant id（Tenant.id）',
                    existing_server_default=False)
    op.execute("ALTER TABLE `SourceList` RENAME INDEX `ix_SourceList_tenant_id` TO `ix_SourceList_user_id`")
    op.alter_column('SourceList', 'tenant_id',
                    new_column_name='user_id',
                    existing_type=mysql.INTEGER(),
                    existing_nullable=True,
                    existing_comment='持有资源的租户id（Tenant.id）',
                    existing_server_default=False)

    # 播种来的 Tenant 记录回滚（仅删除与 User 同 id 的行，业务侧手工建的租户保留）
    op.execute("DELETE t FROM `Tenant` t JOIN `User` u ON t.`id` = u.`id`")
