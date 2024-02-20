from owlready2 import *
import requests

def get_imports(ontology):
    """
    Given an OWL ontology object, returns a list of its imported ontologies.
    """
    return [onto for onto in ontology.imported_ontologies()]

def check_availability(url):
    """
    Given a URL for an ontology, checks its availability by sending a HEAD request.
    Returns True if the ontology is available, False otherwise.
    """
    try:
        response = requests.head(url)
        return response.status_code == 200
    except:
        return False

def display_dependency_tree(ontology, depth=0):
    """
    Recursively displays a dependency tree for the given OWL ontology object,
    showing its imported ontologies and their availability status.
    """
    print(" " * depth + ontology.name)

    for imported_ontology in get_imports(ontology):
        url = imported_ontology.metadata.owlDocumentURI
        status = "Available" if check_availability(url) else "Unavailable"
        print(" " * (depth+2) + "- " + imported_ontology.name + " (" + status + ")")

        display_dependency_tree(imported_ontology, depth+4)

if __name__ == '__main__':
    # Load the main ontology
    onto = get_ontology("http://purl.obolibrary.org/obo/go.owl").load()

    # Display the dependency tree
    display_dependency_tree(onto)
