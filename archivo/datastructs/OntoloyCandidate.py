"""Class for the candidate of an ontology. Provides the evaluation"""
from datetime import datetime
from typing import Tuple
from urllib.parse import urlparse

import rdflib

from archivo.utils.ArchivoExceptions import InvalidNIRException


class OntologyCandidate:
    initial_uri: str
    source: str
    issued_date: datetime
    nir: str
    graph: rdflib.Graph

    def __init__(self, uri: str, source: str):
        self.versionID: str = None
        self.initial_uri: str = uri
        self.source: str = source
        self.issued_date: datetime = datetime.now()

    def get_group_and_artifact(self) -> Tuple[str, str]:

        parsed_obj = urlparse(self.nir)
        # replacing the port with --
        group = parsed_obj.netloc.replace(":", "--")
        artifact = parsed_obj.path + "#" + parsed_obj.fragment
        artifact = artifact.strip("#/~:")

        # replace forbidden chars with --
        for forbidden_char in ["/", "_", ".", "#", "~", ":"]:
            artifact = artifact.replace(forbidden_char, "--")

        if artifact == "":
            artifact = "defaultArtifact"

        if group.startswith("www."):
            group = group.replace("www.", "", 1)
        # none of them can be the empty string or all breaks
        if group == "" or artifact == "":
            raise InvalidNIRException(f"Invalid NIR: {self.nir}")
        else:
            return group, artifact

    def getVersionID(self) -> str:

        if not self.versionID:
            self.versionID = datetime.now().strftime("%Y.%m.%d-%H%M%S")
        return self.versionID
