shopt -s expand_aliases
alias pc='tee >(wc -l >&2)'
alias psum=$'tee >(awk \'BEGIN {FS=",";OFMT = "%.0f"}{count+=$NF} END{print count}\' >&2)' #use $'' and then escape single quotes only
#alias grepc='pc | grep' # switch between count
alias grepc='psum | grep' # and sum
#awk 'BEGIN { FS = "," } {print $NF,$0}' c-distrib.csv |  sort -nr | cut -f2- -d' ' > c-distrib-sorted.csv

cat c-distrib.tsv | grepc -P "^https?://" |  grepc -vP "dbpedia.org/resource/" | grepc -v "http://rdf.freebase.com/ns/" | grepc -vP "dbpedia.org/class/yago" | grepc -v "www.wikidata.org" | grepc -P "\t\d\d+$" > c-distrib-min10.tsv
wc -l c-distrib-min10.tsv
cat p-distrib.csv | grepc -P "^https?://" |  grepc -v "dbpedia.org/resource/" | grepc -v "http://rdf.freebase.com/ns/" | grepc -v "dbpedia.org/property/" | grepc -v "www.wikidata.org" | grepc -v "http://www.w3.org/1999/02/22-rdf-syntax-ns#_" |grepc -P ",\d\d+$" > p-distrib-min10.csv
wc -l p-distrib-min10.csv
echo "class" && cat c-distrib.tsv |  awk 'BEGIN {FS="\t";OFMT = "%.0f"}{count+=$NF} END{print count}'
cat c-distrib-min10.tsv |  awk 'BEGIN {FS="\t";OFMT = "%.0f"}{count+=$NF} END{print count}'
echo "prop"  && cat p-distrib.csv |  awk 'BEGIN {FS=",";OFMT = "%.0f"}{count+=$NF} END{print count}'
cat p-distrib-min10.csv |  awk 'BEGIN {FS=",";OFMT = "%.0f"}{count+=$NF} END{print count}'

#generate RDF
awk 'BEGIN { FS = "\t" } {print "<http://c.2.de/""> <"$1"> "$2" ." }' c-distrib-min10.tsv > c-distrib-min10.ttl
awk 'BEGIN { FS = "," } {print "<http://p.2.de/""> <"$1"> "$2" ." }' p-distrib-min10.csv > p-distrib-min10.ttl
