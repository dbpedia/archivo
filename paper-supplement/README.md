# Supplementary information for the paper

## FOAF analysis
Retrieved on April 23rd, 2020

```
rapper -i rdfxml http://xmlns.com/foaf/spec/ | sort -u  > foaf/foaf_2020.04.23.xml.nt
rapper: Parsing URI http://xmlns.com/foaf/spec/ with parser rdfxml
rapper: Serializing with serializer ntriples
rapper: Parsing returned 635 triples

rapper -i rdfa http://xmlns.com/foaf/spec/ | sort -u  > foaf/foaf_2020.04.23.rdfa.nt
rapper: Parsing URI http://xmlns.com/foaf/spec/ with parser rdfa
rapper: Serializing with serializer ntriples
rapper: Parsing returned 348 triples
```
