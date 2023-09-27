# # first install java 8 for compiling pellet
FROM openjdk:8 as pellet-build

# update apt-get
RUN apt-get update

# install rapper and maven
RUN apt-get install -y maven git zip 

# download and compile pellet
RUN mkdir /usr/lib/pellet/
RUN mvn --version
RUN git clone https://github.com/stardog-union/pellet.git /usr/lib/pellet/
RUN mvn clean install -f /usr/lib/pellet/pom.xml -DskipTests=true

# here we go with python 3.10
FROM python:3.10

# Configure Poetry
ENV POETRY_VERSION=1.6.1
ENV POETRY_HOME=/opt/poetry
ENV POETRY_VENV=/opt/poetry-venv
ENV POETRY_CACHE_DIR=/opt/.cache

# add archivo user
RUN rm /bin/sh && ln -s /bin/bash /bin/sh

# the required deploy directory for databus data and the directory for the data
RUN mkdir -p /home/dstreitmatter/www/archivo/
RUN mkdir -p /usr/local/archivo-data/

# install rapper and maven
RUN apt-get update
RUN apt-get install -y raptor2-utils git zip unzip

# copy pellet to new image and make it executeable
COPY --from=pellet-build /usr/lib/pellet/ /usr/lib/pellet/
RUN chmod +x /usr/lib/pellet/cli/target/pelletcli/bin/pellet


# Install poetry separated from system interpreter
RUN python3 -m venv $POETRY_VENV \
    && $POETRY_VENV/bin/pip install -U pip setuptools \
    && $POETRY_VENV/bin/pip install poetry==${POETRY_VERSION}

# Add `poetry` to PATH
ENV PATH="${PATH}:${POETRY_VENV}/bin"



# copy local directory
COPY poetry.lock pyproject.toml /usr/local/src/webapp/archivo/

# set up project directory

ENV WDIR /usr/local/src/webapp/archivo/archivo

ENV REPO_DIR /usr/local/src/webapp/archivo

# set repo dir as working dir for installation
WORKDIR ${REPO_DIR}

# install packages
RUN poetry install --no-dev

# set WDIR as working dir for execution
WORKDIR ${WDIR}

#Expose the required port
EXPOSE 5000

#Run the command
# CMD ["./startup.sh"]
CMD ["poetry", "run", "gunicorn","--bind", "0.0.0.0:5000", "--workers=6", "archivo:app", "--access-logfile", "./logs/gunicorn-access.log", "--log-file", "./logs/gunicorn-errors.log", "--timeout", "1200", "--preload"]