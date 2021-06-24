# some defaults for the pom generation
default_parentArtifact = "common-metadata"
default_repo = "https://databus.dbpedia.org/repo"
default_version = "0.0.0-notRelevant"

# agent name for crawling
archivo_agent = "dbpedia-archivo-robot"

# add here properties that should be ignored
# pls use the full URI and no prefixes since the diff takes place as ntriples
ignore_props = ["http://purl.org/dc/terms/modified"]

# archivo trackthis uri
track_this_uri = "http://archivo.dbpedia.org/trackThis"

# the properties pointing to classes/props defined by a ontology
# all the objects of triples with these properties are considered a defined resource
# use full uris and no prefixes
defines_properties = ["http://open.vocab.org/terms/defines", "https://archivo.dbpedia.org/onto#defines"]


# edit for your dataset
downloadUrl="https://akswnc7.informatik.uni-leipzig.de/dstreitmatter/archivo/${project.groupId}/${project.artifactId}/${project.version}/"
packDir="/home/dstreitmatter/www/archivo/${project.groupId}/${project.artifactId}/"
pub="https://yum-yab.github.io/webid.ttl#onto"


# paths for external services
pelletPath = (
    "/usr/lib/pellet/cli/target/pelletcli/bin/pellet"
)
profileCheckerJar = "/data/home/dstreitmatter/profilechecker-1.1.0.jar"


# local paths
localPath = "./data"
