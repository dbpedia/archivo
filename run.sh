#! /bin/bash
# mounts:
#       the archivo directory as it is (with its local code and database)
#       the volume the data is stored in (needs to be mapped to a public directory corresponding to the configured PUBLIC_URL)



docker run --restart always -p 5000:5000 --name archivo \
    -v $(pwd):/usr/local/src/webapp/archivo/ \
    -v /data/home/dstreitmatter/www/archivo:/usr/local/archivo-data/ \
    archivo-build
