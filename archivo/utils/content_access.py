from pathlib import Path

import requests

from models.databus_identifier import DatabusFileMetadata
from utils import archivo_config
from utils.archivo_exceptions import UnavailableContentException


def get_databus_file(file_metadata: DatabusFileMetadata) -> str:
    """Checks first if the file can be loaded (faster) from disk before performing an HTTP request"""
    # check if the old file can be loaded from disk
    local_file_path = Path(f"{archivo_config.LOCAL_PATH}/{file_metadata}")

    if archivo_config.LOCAL_PATH and local_file_path.is_file():
        with open(local_file_path) as old_nt_file:
            return old_nt_file.read()
    else:
        old_file_resp = requests.get(f"{archivo_config.DATABUS_BASE}/{file_metadata}")

        if old_file_resp.status_code >= 400:
            raise UnavailableContentException(old_file_resp)
        else:
            return old_file_resp.text


def get_location_url(file_metadata: DatabusFileMetadata) -> str:
    """Returns the URL of a file, either a file path oder a http URL, based on availability. Files are preferred"""

    local_file_path = Path(f"{archivo_config.LOCAL_PATH}/{file_metadata}")

    if archivo_config.LOCAL_PATH and local_file_path.is_file():
        return str(local_file_path)
    else:
        return f"{archivo_config.PUBLIC_URL_BASE}/{file_metadata}"
