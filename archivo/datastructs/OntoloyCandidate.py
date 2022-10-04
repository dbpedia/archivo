"""Class for the candidate of an ontology. Provides the evaluation"""
from datetime import datetime

import rdflib


class OntologyCandidate:

    initial_uri: str
    source: str
    issued_date: datetime
    nir: str
    graph: rdflib.Graph

    def __init__(self, uri: str, source: str):
        self.initial_uri = uri
        self.source = source
        self.issued_date = datetime.now()
