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

# here we go with python 3.9
FROM python:3.9

# add archivo user
RUN rm /bin/sh && ln -s /bin/bash /bin/sh


# the required deploy directory for databus data
RUN mkdir -p /home/dstreitmatter/www/archivo/

# install rapper and maven
RUN apt-get update
RUN apt-get install -y raptor2-utils maven git zip unzip

# copy pellet to new image and make it executeable
COPY --from=pellet-build /usr/lib/pellet/ /usr/lib/pellet/
RUN chmod +x /usr/lib/pellet/cli/target/pelletcli/bin/pellet

# load pipenv
RUN pip install pipenv



# copy local directory
COPY ./Pipfile /usr/local/src/webapp/archivo/Pipfile
COPY ./Pipfile.lock /usr/local/src/webapp/archivo/Pipfile.lock
# COPY . /usr/local/src/webapp/archivo

# set up project directory
ENV PROJECT_DIR /usr/local/src/webapp/archivo/archivo

# set workdir as the project dir
WORKDIR ${PROJECT_DIR}

# install packages
# --system -> dont create venv but install them in containers system python
# --deploy -> die if Pipfile.lock is out of date
RUN pipenv install --system --deploy

#Expose the required port
EXPOSE 5000

#Run the command
# CMD ["./startup.sh"]
CMD ["/usr/local/bin/gunicorn","--bind", "0.0.0.0:5000", "--workers=6", "archivo:app", "--access-logfile", "./logs/gunicorn-access.log", "--log-file", "./logs/gunicorn-errors.log", "--timeout", "1200", "--preload"]