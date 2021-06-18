import os
import yaml


def get_config(name):
    file_path = os.path.join(os.path.dirname(__file__), "../config", f"{name}.yaml")

    with open(file_path, "r") as f:
        contents = yaml.load(f, Loader=yaml.FullLoader)

    return contents


main = get_config("main")
watchers = get_config("watchers")
auth_teams = get_config("auth_teams")
