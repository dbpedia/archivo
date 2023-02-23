from dataclasses import dataclass
from typing import Dict


@dataclass
class DatabusVersionIdentifier:
    user: str
    group: str
    artifact: str
    version: str


@dataclass
class DatabusFileMetadata:
    """A databus-agnostic representation of Databus file metadata"""

    version_identifier: DatabusVersionIdentifier
    content_variants: Dict[str, str]
    file_extension: str

    sha_256_sum: str
    content_length: int

    def content_variants_to_string(self):
        return "_".join([f"{k}={v}" for k, v in self.content_variants.items()])

    def get_file_name(self):
        return f"{self.version_identifier.artifact}_{self.content_variants_to_string()}.{self.file_extension}"
