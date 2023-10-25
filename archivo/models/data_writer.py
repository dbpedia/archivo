import os
from abc import ABC, abstractmethod
from logging import Logger
from pathlib import Path
from typing import List, Optional, Tuple

import databusclient  # type: ignore

from models.databus_identifier import DatabusFileMetadata
from utils.WebDAVUtils import WebDAVHandler


class DataWriter(ABC):
    """Wrapper Class for handling the writing of Files and keeping track of the written files"""

    written_files: List[Tuple[DatabusFileMetadata, Optional[str]]]
    target_url_base: str
    logger: Logger

    @abstractmethod
    def write_data(self, content: str, db_file_metadata: DatabusFileMetadata) -> None:
        """Writing the data to the resource identifier"""
        raise NotImplementedError

    def clear_history(self):
        self.written_files = []

    def write_databus_file(
        self, content: str, db_file_metadata: DatabusFileMetadata, log_file: bool = True
    ) -> None:

        try:
            self.write_data(content, db_file_metadata)
            if log_file:
                self.written_files.append((db_file_metadata, None))
        except Exception as e:
            self.logger.error(f"Error writing file {db_file_metadata}:", e)
            if log_file:
                self.written_files.append((db_file_metadata, str(e)))

    def generate_distributions(self) -> List[str]:

        distributions = []

        for metadata, error in self.written_files:

            dst = databusclient.create_distribution(
                url=f"{self.target_url_base}/{metadata}",
                cvs=metadata.content_variants,
                file_format=metadata.file_extension,
                compression=metadata.compression,
                sha256_length_tuple=(metadata.sha_256_sum, metadata.content_length),
            )
            distributions.append(dst)

        return distributions


class FileWriter(DataWriter):
    def __init__(
        self,
        path_base: Path,
        target_url_base: str,
        logger: Logger,
        create_parent_dirs: bool = True,
    ):
        self.path_base = path_base
        self.create_parent_dirs = create_parent_dirs
        self.written_files = []
        self.target_url_base = target_url_base
        self.logger = logger

    def write_data(self, content: str, db_file_metadata: DatabusFileMetadata) -> None:
        version_dir = os.path.join(
            self.path_base, str(db_file_metadata.version_identifier)
        )

        filepath = os.path.join(version_dir, db_file_metadata.get_file_name())

        if self.create_parent_dirs and not os.path.isdir(version_dir):
            os.makedirs(version_dir)

        with open(filepath, "w+") as target_file:
            target_file.write(content)


class WebDAVWriter(DataWriter):
    def __init__(self, target_url_base: str, api_key: str):
        self.written_files = []
        self.target_url_base = target_url_base
        self.api_key = api_key
        self.webdav_handler = WebDAVHandler(target_url_base, api_key)

    def write_data(self, content: str, db_file_metadata: DatabusFileMetadata) -> None:
        new_file_uri = f"{self.target_url_base}/{db_file_metadata}"

        self.webdav_handler.upload_file(new_file_uri, content, create_parent_dirs=True)
