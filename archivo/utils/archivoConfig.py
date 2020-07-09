
# some defaults for the pom generation
default_parentArtifact="common-metadata"
default_repo="https://databus.dbpedia.org/repo"
default_version="0.0.0-notRelevant"

# agent name for crawling
archivo_agent = "dbpedia-archivo-robot"

# edit for your dataset
downloadUrl="http://akswnc7.informatik.uni-leipzig.de/dstreitmatter/timebased-ontologies/${project.groupId}/${project.artifactId}/${project.version}/"
packDir="/home/dstreitmatter/www/timebased-ontologies/${project.groupId}/${project.artifactId}/"
pub="https://yum-yab.github.io/webid.ttl#onto"



# paths for external services
pelletPath = "/home/denis/Workspace/Job/pellet/cli/target/pelletcli/bin/pellet"
profileCheckerJar="/home/denis/Downloads/profilechecker-1.1.0.jar"

# iri sources
voidResults = "/home/denis/Downloads/voidResults"



# indices
ontoIndexPath = "./indices/vocab_index.json"
falloutIndexPath = "./indices/fallout_index.csv"

# local paths
localPath = "/home/denis/Workspace/Job/Archivo/testdir"

