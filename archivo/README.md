# Archivo Website

## Setup

```
# Clone the repository:
git clone https://github.com/dbpedia/archivo.git
# Install python virtualenv:
sudo apt-get install python3-venv virtualenv
# Change directory:
cd archivo
# Create virtualenv and activate it:
python3 -m venv venv
# or virtualenv venv
source venv/bin/activate
# Change directory:
cd archivo
# Install requirements:
pip install -r requirements.txt
# Run the dev server:
# Note: comment the cronjob decorators in archivo.py to NOT run the cronjobs fro development
python archivo.py
```
