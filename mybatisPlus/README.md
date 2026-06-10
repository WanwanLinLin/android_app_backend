# alembic 初始化
    alembic init migrate

# 数据库修改字段
    cd mybatisPlus/

    先修改 alembic.ini 文件的63行

    alembic revision --autogenerate -m "edit a column"

    alembic upgrade head