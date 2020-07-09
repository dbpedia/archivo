
# some defaults for the pom generation
default_parentArtifact="common-metadata"
default_repo="https://databus.dbpedia.org/repo"
default_version="0.0.0-notRelevant"

# agent name for crawling
archivo_agent = "dbpedia-archivo-robot"

# edit for your dataset
downloadUrl="http://akswnc7.informatik.uni-leipzig.de/dstreitmatter/archivo/${project.groupId}/${project.artifactId}/${project.version}/"
packDir="/home/dstreitmatter/www/archivo/${project.groupId}/${project.artifactId}/"
pub="https://yum-yab.github.io/webid.ttl#onto"


# paths for external services
pelletPath = "/data/home/dstreitmatter/workspace/repos/pellet/cli/target/pelletcli/bin/pellet"
profileCheckerJar="/data/home/dstreitmatter/profilechecker-1.0.0.jar"

# iri sources
voidResults = "/home/denis/Downloads/voidResults"



# indices
ontoIndexPath = "./indices/vocab_index.json"
falloutIndexPath = "./indices/fallout_index.csv"

# local paths
localPath = "/data/home/dstreitmatter/data/archivo-ontologies"

