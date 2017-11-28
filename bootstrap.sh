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
libsystemd-dev # For building systemd-python
pkg-config # For building systemd-python
python3.6-dev # For building pyldap and systemd-python
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


# Cloud SQL Setup

# Define a target for Cloud SQL
cat - > /etc/systemd/system/wglurp-sql.target <<EOF
[Unit]
Description=Represents WGLURP ready to make SQL connections.
DefaultDependencies=true

[Install]
WantedBy=multi-user.target
EOF

# Install and set up the Cloud SQL Proxy service
wget https://dl.google.com/cloudsql/cloud_sql_proxy.linux.amd64 \
     -O /usr/sbin/cloud_sql_proxy
chmod a+x /usr/sbin/cloud_sql_proxy
cat - > /etc/systemd/system/cloud-sql-proxy.service <<EOF
[Unit]
Description=Proxies connections to Google Cloud SQL
Documentation=https://github.com/GoogleCloudPlatform/cloudsql-proxy
Requires=network-online.target
After=network-online.target
DefaultDependencies=true
ConditionPathExists=/usr/sbin/cloud_sql_proxy

[Service]
Type=simple
ExecStartPre=/bin/mkdir /run/cloudsql
ExecStartPre=/bin/chown root:root /run/cloudsql
ExecStart=/usr/sbin/cloud_sql_proxy -dir=/run/cloudsql -fuse

[Install]
WantedBy=wglurp-sql.target
EOF

# Install and set up a service to make a PostgreSQL symlink
cat - > /usr/sbin/cloud-sql-symlink.sh <<EOF
#!/bin/sh

SQL_INSTANCE=\$(/usr/bin/curl -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/attributes/DB)
if [ ! -d /run/postgresql ]; then
    mkdir /run/postgresql
fi
exec ln -s /run/cloudsql/\${SQL_INSTANCE} /run/postgresql/.s.PGSQL.5432
EOF
chmod a+x /usr/sbin/cloud-sql-symlink.sh

cat - > /etc/systemd/system/cloud-sql-symlink.service <<EOF
[Unit]
Description=Makes a symlink for the Postgres client to connect to the right socket.
Requires=network-online.target
After=network-online.target
DefaultDependencies=true

[Service]
Type=oneshot
ExecStart=/usr/sbin/cloud-sql-symlink.sh
RemainAfterExit=true
ExecStopPost=/bin/rm -f /run/.s.PGSQL.5432

[Install]
WantedBy=wglurp-sql.target
EOF

# Trigger systemd and enable services
systemctl daemon-reload
systemctl enable cloud-sql-proxy.service
systemctl enable cloud-sql-symlink.service

# Clean Up and Reboot!

# Clean up temporary packages
apt-get -y purge ${TEMPORARY_PACKAGES[@]}
apt-get -y autoremove
apt-get -y clean

# Clean up Git repos
cd /root
rm -rf /root/git

# Reboot so that patches can take effect, and to start services!
exec shutdown -r now
