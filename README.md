# DBpedia Archivo


Archivo is an online ontology interface and augmented archive, that discovers, crawls, versions and archives ontologies on the [DBpedia Databus](https://databus.dbpedia.org/ontologies/). Each Databus Artifact represents one certain ontology and each version represents a new version of the ontology.

## Use Cases

* **Ontology-Backup:** From time to time ontologies are unavailable at their usual location in the web. In this case Archivo can be used as a simple backup to prevent failure of services.
* **Testing & Rating:** Archivo runs some test to check the usability of a ontology, for example parsing, licenses or consistency. For this Archivo introduced a [star-rating](#Stars). 
Check out <http://archivo.dbpedia.org/info> for a detailed view of the versions of each ontology with the test results.

## Accessing an Ontology on Archivo

### Simple
To download the latest version use 

`http://archivo.dbpedia.org/download?o={ontology-URI}&f={file-extension}`

and Archivo redirects to the latest version.

The format can be set by using `f={ttl,owl,nt}` (optional, default: owl) or by setting the Accept-Header (first one overwrites the latter).

**Example:**
`curl -L "http://archivo.dbpedia.org/download?o=http://advene.org/ns/cinelab/ld&f=ttl"`
downloads the latest version of the Cinelab ontology as Turtle file.

### Advanced

By using a GET request with the implemented formats (`application/rdf+xml`, `application/n-triples` or `text/turtle`) as Accept-Headers returns all information about all versions of this URI as RDF.

## Ontologies included in Archivo

There are multiple options to find an ontology (snapshot):

* [Here](http://archivo.dbpedia.org/list) is a complete list of all ontologies in Archivo with their Databus Artifact and the URL of the latest Turtle-File of each.
* Enter your ontology-URI [here](http://archivo.dbpedia.org/info) and you get information about all the versions of the ontology archived in Archivo.
* Check out the the handy collections on the DBpedia Databus:
    * A collection of the latest original files: [here](https://databus.dbpedia.org/jfrey/collections/archivo-latest-original-ontology-snapshots)
    * A collecttion of the latest parsed files: [here](https://databus.dbpedia.org/jfrey/collections/archivo-latest-ontology-snapshots)

## Adding a ontology to Archivo

Ontologies can be added to Archivo using the [add-service](http://archivo.dbpedia.org/add) of the frontend. But the ontology must fulfill two requirements to be added:
* The URI must be accessible and the RDF content of the ontology must be reachable via content negotiation from there in any of these formats: RDF+XML, N-Triples, Turtle
* The URI defined in the a owl:Ontology (or skos:ConceptScheme) triple must be the same as the one provided here. If that's not the case Archivo tries to handle the new URI just like the one entered.

## Stars

Archivo provides a basic star-rating (not to be confused with the 5 stars of linked data).

Baseline: The minimum requirements a Ontology should fulfill.

* All  of  the  following  criteria  have  to  be  fulfilled:
    1) The non-information URI resolves to a machine readable format or a machine readable version of the ontology is deterministically discoverable by other common means. 
    2) Download was successful 
    3) Uses a common format implemented by Archivo (rdf+xml, turtle or n-triples)
    4) At least one format was found that parses with no or few (negligible) syntactical warnings

* A proper ontology declaration was found using `rdf:type owl:Ontology` and some form of license could be detected. A high degree of heterogeneity is permissible for this star regarding the used property/subproperty as well as  object:license  URI  (resolvable  linked  data  or  web  link),xsd:stringorxsd:anyURI

If the ontology fulfills the baseline, it can earn two further stars by using good practises:

* We require a homogenized license declaration using `dct:license` as object property with a URI (not string or anyURI). 

* We measure the compatibility with currently available reasoners such as Pellet/Stardog (more to follow) and run available tasks such as consistency checks and classification.

## Archivo Documentation


### Files

Archivo provides for each version different files:

| type-values | sub-cvs | Explaination |
| -------- | -------- | -------- |
| orig     |      | Snapshot of the original ontology file |
| parsed   |      | Files parsed by rapper, available as owl, nt and ttl |
| OOPS     |      | OOPS-report |
| generatedDocu | | human readable documentation by LODE |
| profile | | a profile check done by [profilechecker](https://github.com/stain/profilechecker)|
| shaclReport | validates={minLicense, goodLicense, lodeMetadata} | shacl-report as turtle file|
| meta | | a JSON file containing some meta info |
| pelletInfo | imports={FULL,NONE} | the pellet info report, with and without imports |
| pelletConsistency | imports={FULL,NONE} | the pellet consistency report, with and without imports |
| diff | axioms={old,new} | These file contain the added/deleted triples | 




### Ontology Sources

Archivo uses four different sources of potential ontologies:

1. Ontology Repositories: e.g ontologies listed in [LOV](https://lov.linkeddata.es/dataset/lov/)
2. Subjects, Predicates and Objects of Ontologies: Every SPO in an Ontology can lead to a potential new ontology, so Archivo can discover new vocabularies by analyzing already listed ontologies
3. [VOID](https://www.w3.org/TR/void/) Data: Search for new ontologies by looking at VoID metadata summaries describing used classes and properties (on the DBpedia Databus) 
4. [User Suggestions](http://archivo.dbpedia.org/add)
