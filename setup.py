from setuptools import setup, find_packages

setup(name='DBpedia Archivo',
      version='1.0',
      description='DBpedia Archivo (backronym for Ontology Archive) is an online ontology interface and augmented archive that discovers, crawls, versions and archives ontologies on the DBpedia Databus.',
      author='Denis Streitmatter',
      author_email='streitmatter@informatik.uni-leipzig.de',
      url='http://archivo.dbpedia.org/',
      packages=find_packages(),
      include_package_data=True
     )