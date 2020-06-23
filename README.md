# Databus Archivo

## Information

Archivo is an online ontology interface and augmented archive, that discovers, crawls, versions and archives ontologies on the [DBpedia Databus](https://databus.dbpedia.org/ontologies/). Each Databus Artifact represents one certain ontology and each version represents a new version of the ontology.

## Usage

### Finding a ontology on Databus Archivo

There are a few options to find a ontology:
- If you know the URI of the ontology you can enter it at <http://archivo.dbpedia.org/info> and you get the databus artifact of the ontology, for example for [foaf](http://xmlns.com/foaf/0.1/) its <https://databus.dbpedia.org/ontologies/xmlns.com/foaf--0--1>
- If you don't know the URI you can try searching feature of the databus at <https://databus.dbpedia.org/ontologies/>

### Accessing a Archivo Ontology

Generally Ontologies on Archivo can be accessed by querying the Databus SPARQL endpoint at <https://databus.dbpedia.org/repo/sparql>. You can test your query at <https://databus.dbpedia.org/yasgui/>.

**The latest version of an ontology ([example](https://databus.dbpedia.org/yasgui/#query=PREFIX+dataid%3A+%3Chttp%3A%2F%2Fdataid.dbpedia.org%2Fns%2Fcore%23%3E%0APREFIX+dct%3A++++%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0APREFIX+dcat%3A+++%3Chttp%3A%2F%2Fwww.w3.org%2Fns%2Fdcat%23%3E%0APREFIX+db%3A+++++%3Chttps%3A%2F%2Fdatabus.dbpedia.org%2F%3E%0APREFIX+rdf%3A++++%3Chttp%3A%2F%2Fwww.w3.org%2F1999%2F02%2F22-rdf-syntax-ns%23%3E%0APREFIX+rdfs%3A+++%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F01%2Frdf-schema%23%3E%0APREFIX+dataid-cv%3A+%3Chttp%3A%2F%2Fdataid.dbpedia.org%2Fns%2Fcv%23%3E%0APREFIX+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E%0A%0ASELECT+DISTINCT+%3Ffile+WHERE+%7B%0A++VALUES+%3Fart+%7B+%3Chttps%3A%2F%2Fdatabus.dbpedia.org%2Fontologies%2Fxmlns.com%2Ffoaf--0--1%3E+%7D+.%0A++%09%3Fdataset+dataid%3Aaccount+db%3Aontologies+.+%0A++%09%3Fdataset+dataid%3Aartifact+%3Fart+.%0A++%09%3Fdataset+dcat%3Adistribution+%3Fdistribution+.%0A++%09%3Fdistribution+dataid-cv%3Atype+'parsed'%5E%5Exsd%3Astring+.+%09%0A++%09%3Fdistribution+dataid%3AformatExtension+'owl'%5E%5Exsd%3Astring+.+%0A++%09%3Fdistribution+dcat%3AdownloadURL+%3Ffile+.%0A++%09%3Fdataset+dct%3AhasVersion+%3FlatestVersion+.%0A++%09%7B%0A++++%09SELECT+DISTINCT+%3Fart+(MAX(%3Fv)+as+%3FlatestVersion)+WHERE+%7B%0A++++++%09%09%3Fdataset+dataid%3Aaccount+db%3Aontologies+.%0A%09%09++++%3Fdataset+dataid%3Aartifact+%3Fart+.%0A%09%09++++%3Fdataset+dct%3AhasVersion+%3Fv+.%0A++++%09%7D%0A++++%7D%0A%7D&contentTypeConstruct=text%2Fturtle&contentTypeSelect=application%2Fsparql-results%2Bjson&endpoint=https%3A%2F%2Fdatabus.dbpedia.org%2Frepo%2Fsparql&requestMethod=POST&tabTitle=Query+2&headers=%7B%7D&outputFormat=table)):**

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
- ONTOLOGY-ARTIFACT as the artifact of your choosen ontology, e.g https://databus.dbpedia.org/ontologies/xmlns.com/foaf--0--1
- FORMAT as the desired format. Archivo provides the ontologies as Turtle (**ttl**), XML-RDF (**owl**) and N-Triples (**nt**).



## Archivo Documentation


### Files

Archivo provides for each version different files:
- type=orig: The original snapshot of the ontology, unparsed
- type=parsed: The parsed (by [rapper](http://librdf.org/raptor/rapper.html)) ontology in the formats Turtle, RDF-XML and N-Triples
- type=shaclReport: Files containing the SHACL-reports of the [Archivo-SHACL-Tests](https://github.com/dbpedia/Archivo/tree/master/shacl-library), testing the license and the metadata of the ontology
- type=OOPS: A RDF-XML file with a [OOPS-Report](http://oops.linkeddata.es/) of the ontology
- type=generatedDocu: A human-readable documentation of the ontology by the [LODE](https://essepuntato.it/lode/) service
- type=meta: Some meta information about the ontology, e.g access-date, last-modiefied date, a semantic version, errors during parsing etc
- type=pellet[Info, Consistency]: Files containing the output of the [pellet](https://github.com/stardog-union/pellet) info/consistency command (with and without ontology imports).

### Stars

Archivo provides a basic star-rating (not to be confused with the 5 stars of linked data).

Baseline:
- ★: The Ontology parses (Errors and warnings are ok, but rapper must be able to retrieve at least some triples)
- ★★: The Ontology contains some form of license, given by the most popular properties: dct:license, cc:license or xhv:license

If the ontology fulfills the baseline, it can earn two further stars by using good practises:
- ★★★: The license is given by dct:license and is an IRI.
- ★★★★: The ontology is consistent (tested by pellet, with or without imports).


### Ontology Sources

Archivo uses four different sources of potential ontologies:

1. Ontology Repositories: e.g ontologies listed in [LOV](https://lov.linkeddata.es/dataset/lov/)
2. Subjects, Predicates and Objects of Ontologies: Every SPO in an Ontology can lead to a potential new ontology, so Archivo can discover new vocabularies by analyzing already listed ontologies
3. [VOID](https://www.w3.org/TR/void/) Data: Search new ontologies by looking for `rdfs:isDfinedBy` triples in classes and properties used in the whole Databus
4. [User Suggestions](http://archivo.dbpedia.org/add


**Prefixes**
The prefixes used in this description:
`PREFIX dct: <http://purl.org/dc/terms/>`  
`PREFIX dc: <http://purl.org/dc/elements/1.1/>`  
`PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>`  
`PREFIX cc: <http://creativecommons.org/ns#>`  
`PREFIX xhv: <http://www.w3.org/1999/xhtml/vocab#>`  


