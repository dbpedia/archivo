from dataclasses import dataclass
from typing import Dict


@dataclass
class DatabusFileMetadata:
    """A databus-agnostic representation of Databus file metadata"""

    group: str
    artifact: str
    version: str

    content_variants: Dict[str, str]
    file_ending: str

    sha_256_sum: str
    content_length: int

    def content_variants_to_string(self):
        return "_".join([f"{k}={v}" for k, v in self.content_variants.items()])

    def get_file_name(self):
        return f"{self.artifact}_{self.content_variants_to_string()}.{self.file_ending}"
