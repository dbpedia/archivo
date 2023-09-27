# Databus 2.0 API config
from typing import List

DATABUS_API_KEY: str = "blablubb"
DATABUS_BASE: str = "https://databus.dbpedia.org"
DATABUS_USER: str = "ontologies"

# agent name for crawling
ARCHIVO_AGENT: str = "dbpedia-archivo-robot"

# deployment config for server

# path the data should be written to NOTE: It's in the admins job to make this path public by the URL base noted
# below. Archivo will take care of the proper structure. Per default, it is set to the correct docker path,
# so all you have to do ist mount the correct local path and set the PUBLIC_URL_BASE
LOCAL_PATH: str = "/usr/local/archivo-data/"

# The URL the LOCAL_PATH above should be available. Configure your nginx (or whatever) to make it public
PUBLIC_URL_BASE: str = "https://akswnc7.informatik.uni-leipzig.de/dstreitmatter/archivo"

# add here properties that should be ignored
# pls use the full URI and no prefixes since the diff takes place as ntriples
DIFF_IGNORE_PROPERTIES: List[str] = [
    "http://purl.org/dc/terms/modified",
    "http://www.w3.org/2002/07/owl#versionInfo",
]

# archivo trackthis uri
ARCHIVO_TRACK_THIS_PROPERTY: str = "https://archivo.dbpedia.org/onto#trackThis"

# the properties pointing to classes/props defined by a ontology
# all the objects of triples with these properties are considered a defined resource
# use full uris and no prefixes
ONTOLOGY_BACKLINK_PROPERTIES: List[str] = [
    "http://open.vocab.org/terms/defines",
    "https://archivo.dbpedia.org/onto#defines",
]


# max. recursion depth of discovery
# recursion depth of 2 means: uri -> rdf-content -> uri -> rdf-content STOP
DISCOVERY_MAXIMUM_RECURSION_DEPTH: int = 5

# All the ontologies in this list will not be skipped during update due to performance reasons
# NOTE: These problems should be investigated, not ignored, so a GitHub issue should be opened to name and shame myself
DIFF_SKIP_ONTOLOGY_URLS: List[str] = ["http://purl.obolibrary.org/obo/dron.owl"]


# path to the pellet binary
# only needs to be configured if not run in the docker env, the default is set to that
PELLET_BINARY_PATH = "/usr/lib/pellet/cli/target/pelletcli/bin/pellet"
