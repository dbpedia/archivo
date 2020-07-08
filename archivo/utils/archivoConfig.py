
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

# groupDoc for archivo, {} is the domain
groupDoc=("## All DBpedia Archivo ontologies from $groupid domain\n\n"

            "Each artifact in this group deals as the archive for snapshots of one ontology of the [DBpedia Archivo](https://databus.dbpedia.org/ontologies) -  A Web-Scale Interface for Ontology Archiving under Consumer-oriented Aspects. Find out more at [http://archivo.dbpedia.org](http://archivo.dbpedia.org). The description for the individual files in the artifact can be found [here](http://dev.dbpedia.org/DBpedia_Archvio#files)." 
            )

description = (
    "## DBpedia Archivo Ontology Snapshot\n\n"
    "| Attribute |  Value |\n"
    "| - | - |\n" 
    "| Ontology URI | <$non_information_uri>\n"
    "| Archivo Ontology Factsheet| [Link](http://archivo.dbpedia.org/info?o=$ontology_uri)"
    "| Snapshot File URL | <$snapshot_url>\n"
    "| Snapshot OWL Version IRI | <$owl_version_iri>\n"
    "| Snapshot Time | $date\n"
    "\n"
    "The [DBpedia Archivo Databus agent](https://databus.dbpedia.org/ontologies) generates only basic, static documentation for the archived snapshots of the ontologies."
)

description_intro = (
    "## Ontology Metadata\n\n"
    "DBpedia Archivo extracts metadata from the ontology for well known properties (e.g. dct:description). This subsection shows the content of every property individually using a separate heading."
)

# explaination for the md-File
default_explaination="Archvio Ontology Snapshot for $non_information_uri"

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

