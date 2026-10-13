import os
import yaml

ailhs_yaml_path = 'config.yaml' if os.path.exists('config.yaml') else "../config.yaml"
with open(ailhs_yaml_path, 'r') as file:
    config_data = yaml.load(file, Loader=yaml.FullLoader)


def get_service(name: str) -> dict:
    """按服务标记键（redis / mysql / nginx / common 等）查找 SERVICES 配置项。

    SERVICES 是列表，历史代码用位置索引访问，增删条目会导致错位；
    统一改用本函数按键查找，避免此类脆弱性。
    """
    for svc in config_data["SERVICES"]:
        if name in svc:
            return svc
    raise KeyError(f"config.yaml SERVICES 中缺少服务配置项: {name}")


# aec config
FRAME_MAGIC = b"MICK"
FRAME_HEADER_SIZE = 18  # 4 + 4 + 4 + 4 + 2
AEC_DELAY_OFFSET = 8


CURRENT_PATH = os.path.dirname(os.path.abspath(__file__))

LOGS_PATH = os.path.join(CURRENT_PATH, "logs")