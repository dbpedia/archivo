from pathlib import Path

import requests

from archivo.models.databus_identifier import DatabusFileMetadata
from archivo.utils import archivoConfig
from archivo.utils.ArchivoExceptions import UnavailableContentException


def get_databus_file(nt_file_metadata: DatabusFileMetadata) -> str:
    """Checks first if the file can be loaded (faster) from disk before performing an HTTP request"""
    # check if the old file can be loaded from disk
    local_file_path = Path(f"{archivoConfig.localPath}/{nt_file_metadata}")

    if archivoConfig.localPath and local_file_path.is_file():
        with open(local_file_path) as old_nt_file:
            return old_nt_file.read()
    else:
        old_file_resp = requests.get(f"{archivoConfig.DATABUS_BASE}/{nt_file_metadata}")

        if old_file_resp.status_code >= 400:
            raise UnavailableContentException(old_file_resp)
        else:
            return old_file_resp.text
