#!/bin/bash

# Make sure we error out if a command fails
set -e

# Specify what Git IDs we want from various repos
SETUPTOOLS_VERSION=cb9e3a35bfc07136c44d942698fc45fc3f12192b # v36.6.0
PIP_VERSION=022248f6484fe87dc0ef5aec3437f4c7971fd14b #9.0.1
SYNCREPL_CLIENT_VERSION=master
WGLURP_VERSION=master

# These are the packages we need to install.  There are packages to keep
# around (like Python), and packages that we can purge before we wrap up.
PERMANENT_PACKAGES=(
ldap-utils # Helpful LDAP utilities
libsasl2-modules-gssapi-mit # Needed for LDAP GSSAPI auth
postgresql-client-9.6 # For Postgres client libs
python3.6 # Python 3.6!
)
TEMPORARY_PACKAGES=(
build-essential # Misc. build tools
libldap2-dev # For building pyldap
libpq-dev # For building psycopg2
libsasl2-dev # For building pyldap
libssl-dev # For building psycopg2
python3.6-dev # For building pyldap
)

# Make sure we won't be prompted for stuff on install.
export DEBIAN_FRONTEND=noninteractive

# Set up 3rd-party repositories
add-apt-repository -y ppa:jonathonf/python-3.6
cat - > /etc/apt/sources.list.d/pgdg.list <<EOF
deb http://apt.postgresql.org/pub/repos/apt/ xenial-pgdg main
EOF
curl https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -

# Update package lists, bring current packages up-to-date, and install stuff.
apt-get update
apt-get -y dist-upgrade
apt-get -y install ${PERMANENT_PACKAGES[@]} ${TEMPORARY_PACKAGES[@]}

# Make a space for Git clones
mkdir /root/git

# Get setuptools, and build for Python 3.6
git clone https://github.com/pypa/setuptools.git /root/git/setuptools
cd /root/git/setuptools
git checkout -q ${SETUPTOOLS_VERSION}
python3.6 ./bootstrap.py
python3.6 ./setup.py build
python3.6 ./setup.py install

# Get pip, and build for Python 3.6
git clone https://github.com/pypa/pip.git /root/git/pip
cd /root/git/pip
git checkout -q ${PIP_VERSION}
python3.6 ./setup.py build
python3.6 ./setup.py install

# Bring in Python stuff, using pip's hash checking
pip3.6 install --require-hashes -r /root/bootstrap/requirements/ldap-client.txt

# Get syncrepl_client, and build for Python 3.6
git clone git://github.com/akkornel/syncrepl.git /root/git/syncrepl
cd /root/git/syncrepl
git checkout -q ${SYNCREPL_CLIENT_VERSION}
python3.6 ./setup.py build
python3.6 ./setup.py install

# Get wglurp, and build for Python 3.6
git clone git://github.com/akkornel/wglurp.git /root/wglurp
cd /root/wglurp
git checkout -q ${WGLURP_VERSION}
python3.6 ./setup.py build
python3.6 ./setup.py install

# Clean up temporary packages
apt-get -y purge ${TEMPORARY_PACKAGES[@]}
apt-get -y autoremove
apt-get -y clean

# Install the Cloud SQL Proxy
wget https://dl.google.com/cloudsql/cloud_sql_proxy.linux.amd64 \
     -O /usr/sbin/cloud_sql_proxy
chmod a+x /usr/sbin/cloud_sql_proxy

# Clean up Git repos
cd /root
rm -rf /root/git

exit 0
