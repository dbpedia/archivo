# here we go with python 3.9
FROM python:3.9

# add archivo user
RUN rm /bin/sh && ln -s /bin/bash /bin/sh

# the required deploy directory for databus data and the directory for the data
RUN mkdir -p /home/dstreitmatter/www/archivo/
RUN mkdir -p /usr/local/archivo-data/

# install rapper and maven
RUN apt-get update
RUN apt-get install -y raptor2-utils maven git zip unzip

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
CMD ["python", "archivo.py"]