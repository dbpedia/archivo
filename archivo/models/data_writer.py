import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator, Dict, List, Optional

from archivo.models.databus_identifier import DatabusFileMetadata
from archivo.utils.WebDAVUtils import WebDAVHandler


class DataWriter(ABC):
    """Wrapper Class for handling the writing of Files and keeping track of the written files"""

    written_files: Dict[DatabusFileMetadata, Optional[str]]
    target_url_base: str

    @abstractmethod
    def __write_data(self, content: str, db_file_metadata: DatabusFileMetadata) -> None:
        """Writing the data to the resource identifier"""
        pass

    def write_databus_file(
        self, content: str, db_file_metadata: DatabusFileMetadata, log_file: bool = True
    ) -> None:

        try:
            self.__write_data(content, db_file_metadata)
            if log_file:
                self.written_files[db_file_metadata] = None
        except Exception as e:
            if log_file:
                self.written_files[db_file_metadata] = str(e)


class FileWriter(DataWriter):
    def __init__(
        self, path_base: Path, target_url_base: str, create_parent_dirs: bool = True
    ):
        self.path_base = path_base
        self.create_parent_dirs = create_parent_dirs
        self.written_files = {}
        self.target_url_base = target_url_base

    def __write_data(self, content: str, db_file_metadata: DatabusFileMetadata) -> None:
        version_dir = os.path.join(
            self.path_base,
            db_file_metadata.version_identifier.group,
            db_file_metadata.version_identifier.artifact,
            db_file_metadata.version_identifier.version,
        )

        filepath = os.path.join(version_dir, db_file_metadata.get_file_name())

        if self.create_parent_dirs and not os.path.isdir(version_dir):
            os.makedirs(version_dir)

        with open(filepath, "w+") as target_file:
            target_file.write(content)


class WebDAVWriter(DataWriter):
    def __init__(self, target_url_base: str, api_key: str):
        self.written_files = {}
        self.target_url_base = target_url_base
        self.api_key = api_key
        self.webdav_handler = WebDAVHandler(target_url_base, api_key)

    def __write_data(self, content: str, db_file_metadata: DatabusFileMetadata) -> None:
        new_file_uri = f"{self.target_url_base}/{db_file_metadata}"

        self.webdav_handler.upload_file(new_file_uri, content, create_parent_dirs=True)
