import os
import yaml

ailhs_yaml_path = 'config.yaml' if os.path.exists('config.yaml') else "../config.yaml"
with open(ailhs_yaml_path, 'r') as file:
    config_data = yaml.load(file, Loader=yaml.FullLoader)
