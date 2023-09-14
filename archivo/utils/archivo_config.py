# Databus 2.0 API config
DATABUS_API_KEY: str = "blablubb"
DATABUS_BASE: str = "https://databus.dbpedia.org"
DATABUS_USER: str = "ontologies"

# agent name for crawling
archivo_agent: str = "dbpedia-archivo-robot"

# deployment config for server

LOCAL_PATH = "/usr/local/archivo-data/"

PUBLIC_URL_BASE = "https://akswnc7.informatik.uni-leipzig.de/dstreitmatter/archivo"

# add here properties that should be ignored
# pls use the full URI and no prefixes since the diff takes place as ntriples
ignore_props = [
    "http://purl.org/dc/terms/modified",
    "http://www.w3.org/2002/07/owl#versionInfo",
]

# archivo trackthis uri
track_this_uri = "https://archivo.dbpedia.org/onto#trackThis"

# the properties pointing to classes/props defined by a ontology
# all the objects of triples with these properties are considered a defined resource
# use full uris and no prefixes
defines_properties = [
    "http://open.vocab.org/terms/defines",
    "https://archivo.dbpedia.org/onto#defines",
]


# max. recursion depth of discovery
# recursion depth of 2 means: uri -> rdf-content -> uri -> rdf-content STOP
max_recursion_depth = 5

# All the ontologies in this list will not be skipped during update due to performance reasons
# NOTE: These problems should be investigated, not ignored, so a github issue should be opened to name and shame myself
diff_skip_onts = ["http://purl.obolibrary.org/obo/dron.owl"]

# edit for your dataset
downloadUrl = "https://akswnc7.informatik.uni-leipzig.de/dstreitmatter/archivo/${project.groupId}/${project.artifactId}/${project.version}/"
packDir = "/home/dstreitmatter/www/archivo/${project.groupId}/${project.artifactId}/"
pub = "https://yum-yab.github.io/webid.ttl#onto"

# new databus

DOWNLOAD_URL_BASE = "https://downloads.dbpedia.org/archivo"

# paths for external services
pelletPath = "/usr/lib/pellet/cli/target/pelletcli/bin/pellet"
profileCheckerJar = "/data/home/dstreitmatter/profilechecker-1.1.0.jar"


# local paths
localPath = "/usr/local/archivo-data/"
