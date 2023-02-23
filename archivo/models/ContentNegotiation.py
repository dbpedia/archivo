from enum import Enum


class RDF_Type(Enum):
    RDF_XML = 1
    TURTLE = 2
    N_TRIPLES = 3


def get_accept_header(rdf_type: RDF_Type) -> str:
    """Returns the HTTP header for the supported RDF types"""
    match rdf_type:
        case RDF_Type.RDF_XML:
            return "application/rdf+xml"
        case RDF_Type.TURTLE:
            return "text/turtle"
        case RDF_Type.N_TRIPLES:
            return "application/ntriples"


def get_rapper_name(rdf_type: RDF_Type) -> str:
    """Returns the RaptorRDF name for the supported RDF types"""
    match rdf_type:
        case RDF_Type.RDF_XML:
            return "rdfxml"
        case RDF_Type.TURTLE:
            return "turtle"
        case RDF_Type.N_TRIPLES:
            return "ntriples"


def get_file_extension(header: str) -> str:
    """Returns the RaptorRDF name for the supported RDF types"""
    match header:
        case "application/rdf+xml":
            return "owl"
        case "application/ntriples":
            return "nt"
        case "text/turtle":
            return "ttl"
        case "application/xhtml":
            return "html"
        case "*/*":
            return "file"
        case _:
            return "file"
