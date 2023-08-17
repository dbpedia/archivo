from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class DatabusVersionIdentifier:
    user: str
    group: str
    artifact: str
    version: str

    def __str__(self) -> str:
        return f"{self.user}/{self.group}/{self.artifact}/{self.version}"


@dataclass
class DatabusFileMetadata:
    """A databus-agnostic representation of Databus file metadata"""

    version_identifier: DatabusVersionIdentifier
    content_variants: Dict[str, str]
    file_extension: str
    compression: Optional[str]

    sha_256_sum: str
    content_length: int

    def content_variants_to_string(self):
        return "_".join([f"{k}={v}" for k, v in self.content_variants.items()])

    def get_file_name(self):

        if self.compression:
            return f"{self.version_identifier.artifact}_{self.content_variants_to_string()}.{self.file_extension}.{self.compression}"
        else:
            return f"{self.version_identifier.artifact}_{self.content_variants_to_string()}.{self.file_extension}"

    def __str__(self) -> str:
        return f"{self.version_identifier}/{self.get_file_name()}"
