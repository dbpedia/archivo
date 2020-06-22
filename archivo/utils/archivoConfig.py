
# some defaults for the pom generation
default_license="http://archivo.dbpedia.org/sys/licenses#notSpecified"
license_literal_uri="http://archivo.dbpedia.org/sys/licenses#notAnIRI"
default_parentArtifact="common-metadata"
default_repo="https://databus.dbpedia.org/repo"
default_version="0.0.0-notRelevant"

# agent name for crawling
archivo_agent = "dbpedia-archivo-robot"

# edit for your dataset
downloadUrl="http://akswnc7.informatik.uni-leipzig.de/dstreitmatter/timebased-ontologies/${project.groupId}/${project.artifactId}/${project.version}/"
packDir="/home/dstreitmatter/www/timebased-ontologies/${project.groupId}/${project.artifactId}/"
pub="https://yum-yab.github.io/webid.ttl#onto"

# groupDoc for archivo, %s is the domain
groupDoc=("# All vocabularies hosted on {}\n\n"
            "Each artifact in this group refers to one ontology, deployed in different formats.\n"
            "The ontologies are part of the Databus Archivo - A Web-Scale Ontology Interface for Time-Based and Semantic Archiving and Developing Good Ontologies.\n"
            "More at <http://dev.dbpedia.org/DBpedia_Archvio> and <http://archivo.dbpedia.org/>."
            )

# explaination for the md-File
default_explaination="This ontology is part of the Databus Archivo - A Web-Scale OntologyInterface for Time-Based and SemanticArchiving and Developing Good Ontologies"

# paths for external services
pelletPath = "/data/home/dstreitmatter/workspace/repos/pellet/cli/target/pelletcli/bin/pellet"
profileCheckerJar="/data/home/dstreitmatter/profilechecker-1.1.0.jar"

# iri sources
voidResults = "/home/denis/Downloads/voidResults"


# indices
ontoIndexPath = "/data/home/dstreitmatter/workspace/repos/Archivo/archivo/indices/vocab_index.json"
falloutIndexPath = "/data/home/dstreitmatter/workspace/repos/Archivo/archivo/indices/fallout_index.csv"

# local paths
localPath = "/data/home/dstreitmatter/data/archivo-ontologies"

