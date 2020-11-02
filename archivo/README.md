# Archivo Website

## Setup

```
# Clone the repository:
git clone https://github.com/dbpedia/Archivo.git
# Install python virtualenv:
sudo apt-get install python3-venv virtualenv
# Change directory:
cd Archivo
# Create virtualenv and activate it:
virtualenv venv
source venv/bin/activate
# Change directory:
cd archivo
# Install requirements:
pip install -r requirements.txt
# Run the dev server:
# Note: comment the cronjob decorators in archivo.py to NOT run the cronjobs fro development
python archivo.py
```
