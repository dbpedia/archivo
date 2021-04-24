#! /bin/bash
# mounts:
#       the archivo directory as it is (with its local code and database)
#       the webid bundle
#       the volume the data is stored in (needs to be mapped to )



docker run -p 5000:5000 --name archivo-system \
    -v $(pwd):/usr/local/src/webapp/archivo/ \
    -v ~/.m2/onto_webid_bundle.p12:/root/.m2/onto_webid_bundle.p12 \
    -v archivo-data:$(pwd)/data/ \
    -v /data/home/dstreitmatter/www/archivo:/home/dstreitmatter/www/archivo/ \
    archivo-system