import rdflib

from archivo.validation.reports import Severity


def check_highest_severity_of_graph(shacl_report_graph: rdflib.Graph) -> Severity:
    """checks a shacl report graph for the highest occurring severity"""

    sh = rdflib.Namespace("http://www.w3.org/ns/shacl#")

    violation = rdflib.URIRef("http://www.w3.org/ns/shacl#Violation")
    warning = rdflib.URIRef("http://www.w3.org/ns/shacl#Warning")
    info = rdflib.URIRef("http://www.w3.org/ns/shacl#Info")

    highest_severity: Severity = Severity.INFO

    for o in shacl_report_graph.objects(predicate=sh.resultSeverity):

        if o == violation:
            return Severity.ERROR
        elif o == warning and highest_severity.value < Severity.WARNING.value:
            highest_severity = Severity.WARNING

    return highest_severity
