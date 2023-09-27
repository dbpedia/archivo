from dataclasses import dataclass
from typing import List


@dataclass
class BooleanTestResult:

    conforms: bool
    databus_report_url: str


@dataclass
class SeverityTestResult:

    severity: str
    databus_report_url: str


@dataclass
class ContentTestResult:

    conforms: bool
    content: str


@dataclass
class Link:
    label: str
    url: str


@dataclass
class VersionInformation:

    min_license: BooleanTestResult
    good_license: BooleanTestResult
    lode_conformity: SeverityTestResult
    archivo_conformity: SeverityTestResult
    consistency: SeverityTestResult
    parsing: ContentTestResult
    version: Link
    triples: int
    semantic_version: str
    stars: int
    documentation_url: str


@dataclass
class ArtifactInformation:

    version_infos: List[VersionInformation]
    title: str
    description: str
