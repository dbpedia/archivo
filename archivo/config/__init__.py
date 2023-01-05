import toml
import os

__ARCHIVO_BASEDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

__CONFIG_PATH = os.path.join(__ARCHIVO_BASEDIR, "archivo_config.toml")
ARCHIVO_CONFIG = toml.load(__CONFIG_PATH)