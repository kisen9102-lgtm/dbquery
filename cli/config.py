import json
import os
import stat

CONFIG_PATH = os.path.expanduser('~/.dbcli.json')


def load_config(path=CONFIG_PATH):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save_config(config, path=CONFIG_PATH):
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
