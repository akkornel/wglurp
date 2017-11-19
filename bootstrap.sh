#!/bin/bash

# Make sure we error out if a command fails
set -e

# Specify what Git IDs we want from various repos
SETUPTOOLS_VERSION=cb9e3a35bfc07136c44d942698fc45fc3f12192b # v36.6.0
PIP_VERSION=022248f6484fe87dc0ef5aec3437f4c7971fd14b #9.0.1
PYASN1_VERSION=c22b813b9251c35347eace1ea3189d9cbfadfa24 # v0.2.2
PYLDAP_VERSION=544b1e38f4b790d7e93448ed0d19f5906c0be31f # pyldap-2.4.37
SYNCREPL_CLIENT_VERSION=e2925b9cc1219b338364b919d9e59c65e1b1337d # v0.95.1
WGLURP_VERSION=master

# These are the packages we need to install.  There are packages to keep
# around (like Python), and packages that we can purge before we wrap up.
PERMANENT_PACKAGES=(
ldap-utils # Helpful LDAP utilities
libsasl2-modules-gssapi-mit # Needed for LDAP GSSAPI auth
python3.6 # Python 3.6!
)
TEMPORARY_PACKAGES=(
build-essential # Misc. build tools
libldap2-dev # For building pyldap
libsasl2-dev # For building pyldap
python3.6-dev # For building pyldap
)

# Make sure we won't be prompted for stuff on install.
export DEBIAN_FRONTEND=noninteractive

# Set up 3rd-party repositories
add-apt-repository -y ppa:jonathonf/python-3.6

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

# Clean up temporary packages
apt-get -y purge ${TEMPORARY_PACKAGES[@]}
apt-get -y autoremove
apt-get -y clean

# Clean up Git repos
cd /root
rm -rf /root/git

exit 0
