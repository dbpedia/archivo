import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator, Dict, List, Optional

from archivo.models.DatabusIdentifier import DatabusFileMetadata


class DataWriter(ABC):
    """Wrapper Class for handling the writing of Files and keeping track of the written files"""

    written_files: Dict[DatabusFileMetadata, Optional[str]]

    @abstractmethod
    def __write_data(self, content: str, db_file_metadata: DatabusFileMetadata) -> None:
        """Writing the data to the resource identifier"""
        pass

    def write_databus_file(self, content: str, db_file_metadata: DatabusFileMetadata) -> None:

        try:
            self.__write_data(content, db_file_metadata)
            self.written_files[db_file_metadata] = None
        except Exception as e:
            self.written_files[db_file_metadata] = str(e)


class FileWriter(DataWriter):

    def __init__(self, path_base: Path, create_parent_dirs: bool = False):
        self.path_base = path_base
        self.create_parent_dirs = create_parent_dirs
        self.written_files = {}

    def __write_data(self, content: str, db_file_metadata: DatabusFileMetadata) -> None:
        version_dir = os.path.join(self.path_base,
                                   db_file_metadata.version_identifier.group,
                                   db_file_metadata.version_identifier.artifact,
                                   db_file_metadata.version_identifier.version,
                                   )

        filepath = os.path.join(version_dir, db_file_metadata.get_file_name())

        if self.create_parent_dirs and not os.path.isdir(version_dir):
            os.makedirs(version_dir)

        with open(filepath, "w+") as target_file:
            target_file.write(content)
