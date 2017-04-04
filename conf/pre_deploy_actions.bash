#!/bin/bash

# abort on any errors
set -e

# check that we are in the expected directory
cd "$(dirname $BASH_SOURCE)"/..

# Some env variables used during development seem to make things break - set
# them back to the defaults which is what they would have on the servers.
PYTHONDONTWRITEBYTECODE=""

# create the virtual environment; we always want system packages
virtualenv_args="--system-site-packages"
virtualenv_dir='.venv'
virtualenv_activate="$virtualenv_dir/bin/activate"

if [ ! -f "$virtualenv_activate" ]
then
    virtualenv $virtualenv_args $virtualenv_dir
fi

source $virtualenv_activate

# Upgrade pip to a secure version
curl --silent --location https://bootstrap.pypa.io/get-pip.py | python - 'pip<9'
pip install distribute==0.7.3
# Improve SSL behaviour
pip install pyOpenSSL ndg-httpsclient pyasn1

# Install all the packages
pip install -r requirements.txt

# make sure that there is no old code (the .py files may have been git deleted)
find . -name '*.pyc' -delete

# Compile CSS
mapit_make_css

# gather all the static files in one place
python manage.py collectstatic --noinput --link
