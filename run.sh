#! /bin/bash
# mounts:
#       the archivo directory as it is (with its local code and database)
#       the webid bundle
#       the volume the data is stored in (needs to be mapped to )



docker run --name archivo-discovery-dummy \
    -v $(pwd):/usr/local/src/webapp/archivo/ \
    -v /home/denis/testdir:/usr/local/archivo-data/ \
    archivo-build:latest
