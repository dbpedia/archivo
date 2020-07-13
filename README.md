# Databus Archivo

## Information

Archivo is an online ontology interface and augmented archive, that discovers, crawls, versions and archives ontologies on the [DBpedia Databus](https://databus.dbpedia.org/ontologies/). Each Databus Artifact represents one certain ontology and each version represents a new version of the ontology.

## Usage

### Finding a ontology on Databus Archivo

There are multiple options to find an ontology (snapshot):

* If you know the URI of the ontology you can enter it at <http://archivo.dbpedia.org/info> and you get the Databus artifact of the ontology, for example for [foaf](http://xmlns.com/foaf/0.1/) its <https://databus.dbpedia.org/ontologies/xmlns.com/foaf--0--1>

* If you don't know the URI you can try Databus search index (over ontologie metadata) <https://databus.dbpedia.org/ontologies/>

* A GET request to http://archivo.dbpedia.org/info?o=ONTOLOGY-URL with Accept-Headers `application/rdf+xml`, `application/n-triples` or `text/turtle` redirects to RDF (DataID) information about the release(s) on the databus.   
Example: `curl -L -H "Accept: text/turtle"  "http://archivo.dbpedia.org/info?o=http://mmoon.org/core/"`

### Accessing an Archivo Ontology

Generally Ontologies on Archivo can be accessed by querying the Databus SPARQL endpoint at <https://databus.dbpedia.org/repo/sparql>. You can test your query at <https://databus.dbpedia.org/yasgui/>.

Moreover there are two handy [Databus collection](https://wiki.dbpedia.org/blog/new-prototype-databus-collection-feature) allowing you to easily build an [**index of all latest original ontology versions**](https://databus.dbpedia.org/jfrey/collections/archivo-latest-original-ontology-snapshots) or an [**index of all latest parsed ontology versions**](https://databus.dbpedia.org/jfrey/collections/archivo-latest-ontology-snapshots)

**Retrieving the latest version of an ontology ([example](https://databus.dbpedia.org/yasgui/#query=PREFIX+dataid%3A+%3Chttp%3A%2F%2Fdataid.dbpedia.org%2Fns%2Fcore%23%3E%0APREFIX+dct%3A++++%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0APREFIX+dcat%3A+++%3Chttp%3A%2F%2Fwww.w3.org%2Fns%2Fdcat%23%3E%0APREFIX+db%3A+++++%3Chttps%3A%2F%2Fdatabus.dbpedia.org%2F%3E%0APREFIX+rdf%3A++++%3Chttp%3A%2F%2Fwww.w3.org%2F1999%2F02%2F22-rdf-syntax-ns%23%3E%0APREFIX+rdfs%3A+++%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F01%2Frdf-schema%23%3E%0APREFIX+dataid-cv%3A+%3Chttp%3A%2F%2Fdataid.dbpedia.org%2Fns%2Fcv%23%3E%0APREFIX+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E%0A%0ASELECT+DISTINCT+%3Ffile+WHERE+%7B%0A++VALUES+%3Fart+%7B+%3Chttps%3A%2F%2Fdatabus.dbpedia.org%2Fontologies%2Fxmlns.com%2Ffoaf--0--1%3E+%7D+.%0A++%09%3Fdataset+dataid%3Aaccount+db%3Aontologies+.+%0A++%09%3Fdataset+dataid%3Aartifact+%3Fart+.%0A++%09%3Fdataset+dcat%3Adistribution+%3Fdistribution+.%0A++%09%3Fdistribution+dataid-cv%3Atype+'parsed'%5E%5Exsd%3Astring+.+%09%0A++%09%3Fdistribution+dataid%3AformatExtension+'owl'%5E%5Exsd%3Astring+.+%0A++%09%3Fdistribution+dcat%3AdownloadURL+%3Ffile+.%0A++%09%3Fdataset+dct%3AhasVersion+%3FlatestVersion+.%0A++%09%7B%0A++++%09SELECT+DISTINCT+%3Fart+(MAX(%3Fv)+as+%3FlatestVersion)+WHERE+%7B%0A++++++%09%09%3Fdataset+dataid%3Aaccount+db%3Aontologies+.%0A%09%09++++%3Fdataset+dataid%3Aartifact+%3Fart+.%0A%09%09++++%3Fdataset+dct%3AhasVersion+%3Fv+.%0A++++%09%7D%0A++++%7D%0A%7D&contentTypeConstruct=text%2Fturtle&contentTypeSelect=application%2Fsparql-results%2Bjson&endpoint=https%3A%2F%2Fdatabus.dbpedia.org%2Frepo%2Fsparql&requestMethod=POST&tabTitle=Query+2&headers=%7B%7D&outputFormat=table)):**

    PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>
    PREFIX dct:    <http://purl.org/dc/terms/>
    PREFIX dcat:   <http://www.w3.org/ns/dcat#>
    PREFIX db:     <https://databus.dbpedia.org/>
    PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>    
    PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX dataid-cv: <http://dataid.dbpedia.org/ns/cv#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

    SELECT DISTINCT ?file WHERE {
      VALUES ?art { <ONTOLOGY-ARTIFACT> } .
  	    ?dataset dataid:account db:ontologies . 
  	    ?dataset dataid:artifact ?art .
  	    ?dataset dcat:distribution ?distribution .
  	    ?distribution dataid-cv:type 'parsed'^^xsd:string . 	
  	    ?distribution dataid:formatExtension 'FORMAT'^^xsd:string . 
  	    ?distribution dcat:downloadURL ?file .
  	    ?dataset dct:hasVersion ?latestVersion .
  	        {
    	    SELECT DISTINCT ?art (MAX(?v) as ?latestVersion) WHERE {
      		    ?dataset dataid:account db:ontologies .
		        ?dataset dataid:artifact ?art .
		        ?dataset dct:hasVersion ?v .
    	    }
            }
    }

This query retrieves the URL of a parsed ontology, with the parameters:

* ONTOLOGY-ARTIFACT as the artifact of your choosen ontology, e.g https://databus.dbpedia.org/ontologies/xmlns.com/foaf--0--1

* FORMAT as the desired format. Archivo provides the ontologies as Turtle (**ttl**), XML-RDF (**owl**) and N-Triples (**nt**).



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

### Stars

Archivo provides a basic star-rating (not to be confused with the 5 stars of linked data).

Baseline:

* ★: All  of  the  following  criteria  have  to  be  fulfilled:1) The non-information URI resolves to a machine readable format or a machine readable version of the ontology is deterministically discoverable by other common means. 2) download was successful 3) uses a common format implemented by Archivo 4) at least one format was found that parses with no or few (negligible) syntactical warnings

* ★★: A proper ontology declaration was found using `rdf:type owl:Ontology` and some form of license could be detected. A high degree of heterogeneity is permissible for this star regarding the used property/subproperty as well as  object:license  URI  (resolvable  linked  data  or  web  link),xsd:stringorxsd:anyURI

If the ontology fulfills the baseline, it can earn two further stars by using good practises:

* ★★★: We require a homogenized license declaration using `dct:license` as object property with a URI (not string or anyURI). 

* ★★★★: We measure the compatibility with currently available reasoners suchas Pellet/Stardog (more to follow) and run available tasks such as consistency checks and classification.


### Ontology Sources

Archivo uses four different sources of potential ontologies:

1. Ontology Repositories: e.g ontologies listed in [LOV](https://lov.linkeddata.es/dataset/lov/)
2. Subjects, Predicates and Objects of Ontologies: Every SPO in an Ontology can lead to a potential new ontology, so Archivo can discover new vocabularies by analyzing already listed ontologies
3. [VOID](https://www.w3.org/TR/void/) Data: Search new ontologies by looking for `rdfs:isDfinedBy` triples in classes and properties used in the whole Databus
4. [User Suggestions](http://archivo.dbpedia.org/add)


**Prefixes**
The prefixes used in this description:

* `PREFIX dct: <http://purl.org/dc/terms/>`  

* `PREFIX dc: <http://purl.org/dc/elements/1.1/>`

* `PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>`  

* `PREFIX cc: <http://creativecommons.org/ns#>`

* `PREFIX xhv: <http://www.w3.org/1999/xhtml/vocab#>`  


