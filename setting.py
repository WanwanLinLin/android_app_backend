import os
import yaml

ailhs_yaml_path = 'config.yaml' if os.path.exists('config.yaml') else "../config.yaml"
with open(ailhs_yaml_path, 'r') as file:
    config_data = yaml.load(file, Loader=yaml.FullLoader)


# aec config
FRAME_MAGIC = b"MICK"
FRAME_HEADER_SIZE = 18  # 4 + 4 + 4 + 4 + 2
AEC_DELAY_OFFSET = 8


CURRENT_PATH = os.path.dirname(os.path.abspath(__file__))
