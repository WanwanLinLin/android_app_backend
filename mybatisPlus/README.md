# alembic 初始化
    alembic init migrate

# 数据库修改字段
    cd mybatisPlus/

    先修改 alembic.ini 文件的63行

    alembic revision --autogenerate -m "edit a column"

    alembic upgrade head


# python解释器路径
    /home/linwan/miniconda3/envs/android-backend/bin/python3


# 开发用的系统账号密码（有sudo权限）
    账号：linwan
    密码：linwanwan


# Mysql 数据库
    本地开发：Android-Backend