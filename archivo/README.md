# Setting Up Archivo

## Setup

There are two modes available for archivo: **Develop** for working on the server and **Deploy** for deploying the service with docker+gunicorn

### Develop
```
# It is assumend that pip3 and python3.8 are installed on the machine
# Clone the repository:
git clone https://github.com/dbpedia/archivo.git
# Install pipenv for user:
pip3 install pipenv --user
# Install from Pipfile
# Sometimes it can be possible that /home/<user>/.local/bin needs to be added to PATH:
# Add the follwing line to .bashrc or .zshrc or similar while replacing your user name
# export PATH=/home/<user>/.local/bin:$PATH
pipenv install
# Set enviroment shell
pipenv shell
# Change directory:
cd archivo
# Run the dev server:
# Note: comment the cronjob decorators in archivo.py to NOT run the cronjobs for development
python archivo.py
```
### Deploy
It is assumed that docker is correctly installed, if not try [this](https://docs.docker.com/engine/install/).

Steps for running the service with docker:
- Clone the repository: `git clone https://github.com/dbpedia/archivo.git`
- Edit the `../run.sh` script:
    - create a docker volume named archivo-data: `docker volume create archivo-data`
    - change the destined path of packaged Databus files to your desire in the line `-v /data/home/dstreitmatter/www/archivo:/home/dstreitmatter/www/archivo/ \` (left part of ":") **NOTE:** if you do this you need to also change the variables `downloadUrl` and `packDir` in `utils/archivoConfig`
- Start in the directory with the file `Dockerfile` and run:
    - `docker build -t archivo-system .` for building the docker image
    - `chmod +x run.sh`
    - `./run.sh`