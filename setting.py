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


VAD_MODEL_FILES = (
    "firered_vad_packed_cache_stream.ncnn.param",
    "firered_vad_packed_cache_stream.ncnn.bin",
    "cmvn_means_stream.bin",
    "cmvn_istd_stream.bin",
)


def vad_model_paths(base_path: str = "") -> tuple:
    """返回流式 VAD 的四个模型文件绝对路径。

    优先使用 config.yaml MODEL_CONFIG 指定的外部模型目录（保持旧行为）；
    该目录不存在时回退到 fireredvad 包内置的模型，无需再依赖外部路径。
    """
    import fireredvad

    if base_path and os.path.exists(os.path.join(base_path, VAD_MODEL_FILES[0])):
        return tuple(os.path.join(base_path, name) for name in VAD_MODEL_FILES)
    return tuple(fireredvad.model_path(name) for name in VAD_MODEL_FILES)


# aec config
FRAME_MAGIC = b"MICK"
FRAME_HEADER_SIZE = 18  # 4 + 4 + 4 + 4 + 2
AEC_DELAY_OFFSET = 8


CURRENT_PATH = os.path.dirname(os.path.abspath(__file__))

LOGS_PATH = os.path.join(CURRENT_PATH, "logs")