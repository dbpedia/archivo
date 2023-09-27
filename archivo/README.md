# Setting Up Archivo

## Setup

There are two modes available for archivo: **Develop** for working on the server and **Deploy** for deploying the service with docker+gunicorn.


### Develop

Archivo uses [poetry](https://python-poetry.org/docs/), so please install it beforehand.

```bash
# Clone the repository:
git clone https://github.com/dbpedia/archivo.git
# Go into the repo
cd archivo
# Install the dependencies with poetry
poetry install
# Change directory to the actual source code
cd archivo
# Run the dev server:
# Note: this only starts the webservice, cronjobs (update, discovery, etc.) are only run if it is started in deployment mode with gunicorn
# If those services are tested just import the archivo python file in the interactive shell and execute the required functions
poetry run python archivo.py
```
### Deploy
It is assumed that docker is correctly installed, if not try [this](https://docs.docker.com/engine/install/).

Steps for running the service with docker:
#### 1. Setup

Just clone the repository as it is
```bash
git clone https://github.com/dbpedia/archivo.git
cd archivo
```

#### 2. Configuration

You need to configure multiple points:

1. Configure your local nginx (or any other similar software) to make a local directory (and all its possible subdirectories) `LOCAL_DIR` (e.g. `/home/myuser/www/archivo-data`) available to the public under a certain URL `PUBLIC_URL` (e.g. `https://mydomain.org/myuser/archivo-data`) 
2. Now configure the two necessary files:
   1. The [archivo config](utils/archivo_config.py), here you need to set at least the `PUBLIC_URL_BASE` constant to your `PUBLIC_URL`
   2. The [docker run script](../run.sh), here you need to mount your local directory `LOCAL_DIR` to `/usr/local/archivo-data` (see the example given)
   3. You can also change the preset configs in the `archivo_config.py`, but it is not necessary for the first start

#### 3. Running the Docker Container

First, you need to build the container with the following command:
```commandline
docker build -t archivo-build .
```
Since this downloads and builds the pellet reasoner, the first time this is executed will take quite a while. But since it is cached it won't do it again (on the same machine).

Then just run the configured script:
```commandline
chmod -x run.sh
./run.sh
```