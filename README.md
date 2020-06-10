# Archivo

Archivo is an online ontology interface and augmented archive, that discovers, crawls, versions and archives ontologies on the [DBpedia Databus](https://dataus.dbpedia.org/ontologies). [more](https://svn.aksw.org/papers/2020/semantics_archivo/public.pdf)

## Archivo Features

### Discovery

Archivo uses four different sources of potential ontologies:

1. Ontology Repositories: e.g ontologies listed in [LOV](https://lov.linkeddata.es/dataset/lov/)
2. Subjects, Predicates and Objects of Ontologies: Every SPO in an Ontology can lead to a potential new ontology, so Archivo can discover new vocabularies by analyzing already listed ontologies
3. [VOID](https://www.w3.org/TR/void/) Data: Search new ontologies by looking for `rdfs:isDfinedBy`triples in classes and properties used in the whole Databus    
4. [User Suggestions](http://archivo.dbpedia.org/)


### Updates
Three times a day Archivo looks for new versions of the ontology and uses a `http-head request` to compare the the http-headers E-Tag, Last-Modified and Content-Length. With a new update a new semantic version based on the axioms of the ontology is generated.

## Archivo-Ready Ontologies

### Baseline (Stars 1-2)

There are a few minimum requirements for ontologies listed in Archivo:

1. Non-information URI: has a URI defined by `rdf:type owl:Ontology` in the ontology
2. Machine Readable Format: The ontology must be accessible as a machine readable format (rdf+xml, turtle, ntriples, rdfa, rdf+json; parsed by [rapper](http://librdf.org/raptor/)) at the non-information URI 
3. License: Has some form of license defined by either `dct:license`, `cc:license` or `xhv:license` (Still optional)

### Good Practices (Stars 3-4)
1. The license should be given by the property `dct:license` and the value should be an IRI
2. The ontology should be logical consistent (checked by [pellet](https://github.com/stardog-union/pellet))

### Metadata
Archivo tries to use the metadata given in the ontology source as the databus-metadata to make it compatible with databus-features such as search etc. (hierarchy given by order):

+ `dct:title`: Chosen from `rdfs:label, dct:title or dc:title`of the Ontology
+ `rdfs:comment`: First sentence of `dct:abstract dct:description or dc:description` of Ontology
+ `dataid:groupdocu`: TODO (right now: fixed string)
+ `dct:description`: Chosen from `rdfs:description, dct:description, dc:description, rdfs:comment, dct:abstract` of Ontology

Another part of a good metadata coverage are the metadata requirements of the [LODE](https://essepuntato.it/lode) service tested by a [SHACL-Test](https://github.com/dbpedia/Archivo/blob/master/shacl-library/LODE.ttl)
Properties used by LODE are:
-   dc:contributor
    
-   dc:creator
    
-   dc:date
    
-   dc:description, used with a literal as object, if you want to add a textual description to the ontology, or with a resource as object, if you want to trasclude that resource (e.g., a picture) as description of an entity.
    
-   dc:publisher
    
-   dc:rights
    
-   dc:title
    
-   owl:backwardCompatibleWith
    
-   owl:incompatibleWith
    
-   owl:versionInfo
    
-   owl:versionIRI
    
-   rdfs:comment
    
-   rdfs:isDefinedBy
    
-   rdfs:label


## Prefixes
The prefixes used in this description:
`PREFIX dct: <http://purl.org/dc/terms/>`
`PREFIX dc: <http://purl.org/dc/elements/1.1/>`
`PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>`
`PREFIX cc: <http://creativecommons.org/ns#>`
`PREFIX xhv: <http://www.w3.org/1999/xhtml/vocab#>`
