#!/bin/bash

# Make sure we error out if a command fails
set -e

# Specify what Git IDs we want from various repos
SETUPTOOLS_VERSION=cb9e3a35bfc07136c44d942698fc45fc3f12192b # v36.6.0
PIP_VERSION=022248f6484fe87dc0ef5aec3437f4c7971fd14b #9.0.1
SYNCREPL_CLIENT_VERSION=master
WGLURP_VERSION=master

PYTHON_DISTUTILS_EXTRA=https://launchpad.net/python-distutils-extra/trunk/2.39/+download/python-distutils-extra-2.39.tar.gz
PYTHON_DISTUTILS_EXTRA_SIG=https://launchpad.net/python-distutils-extra/trunk/2.39/+download/python-distutils-extra-2.39.tar.gz.asc


# These are the packages we need to install.  There are packages to keep
# around (like Python), and packages that we can purge before we wrap up.
PERMANENT_PACKAGES=(
krb5-user # Kerberos utilities
kstart # For Kerberos credentials caches
ldap-utils # Helpful LDAP utilities
libsasl2-modules-gssapi-mit # Needed for LDAP GSSAPI auth
postgresql-client-9.6 # For Postgres client libs
python3.6 # Python 3.6!
)
TEMPORARY_PACKAGES=(
build-essential # Misc. build tools
libapt-pkg-dev # For building python-apt
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

# Install python-distutils-extra, needed by python-apt.
mkdir /root/python-distutils-extra
cd /root/python-distutils-extra
curl -L -o python-distutils-extra.tar.gz $PYTHON_DISTUTILS_EXTRA
curl -L -o python-distutils-extra.tar.gz.asc $PYTHON_DISTUTILS_EXTRA_SIG

tar -xzf python-distutils-extra.tar.gz 
cd python-distutils-extra-*
python3.6 ./setup.py build
python3.6 ./setup.py install

# Install python-apt
mkdir /root/python-apt
apt-get source --download-only python-apt
tar -xJf python-apt*.tar.xz
cd python-apt-*
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


# Environment Setup

# Set up a run directory
cat - > /etc/systemd/system/wglurp-run-dir.service <<EOF
[Unit]
Description=Create the /run/wglurp directory.
DefaultDependencies=true

[Service]
Type=oneshot
ExecStart=/bin/mkdir /run/wglurp
RemainAfterExit=true
ExecStopPost=/bin/rm -rf /run/wglurp
EOF

# Set up a service that outputs environment variablaes
cat - > /usr/sbin/wglurp-env.sh <<EOF
#!/bin/bash

touch /run/wglurp/env
for var in $(/usr/bin/curl --silent -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/attributes/); do
    if [ $var = 'startup-script' ]; then continue; fi
    echo "WGLURP_METADATA_${var}=$(/usr/bin/curl --silent -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/attributes/${var})" >> /run/wglurp/env
done
EOF
chmod a+x /usr/sbin/wglurp-env.sh
cat - > /etc/systemd/system/wglurp-environment.service <<EOF
[Unit]
Description=Populate /run/wglurp/env
DefaultDependencies=true
Requires=wglurp-run-dir.service
After=wglurp-run-dir.service

[Service]
Type=oneshot
ExecStart=/usr/sbin/wglurp-env.sh
RemainAfterExit=true
ExecStopPost=/bin/rm /run/wglurp/env
EOF

# Trigger systemd to pick up changes
# NOTE: We don't have any services to enable here; they'll be
# loaded automatically as needed by other services.
systemctl daemon-reload

# Read in our metadata-based environment variables,
# just in case we need them later!
systemctl start wglurp-environment.service
. /run/wglurp/env

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
cat - > /etc/systemd/system/cloud-sql-symlink.service <<EOF
[Unit]
Description=Makes a symlink for the Postgres client to connect to the right socket.
Requires=network-online.target wglurp-environment.service
After=network-online.target wglurp-environment.service
DefaultDependencies=true

[Service]
Type=oneshot
EnvironmentFile=/run/wglurp/env
ExecStart=/bin/mkdir /run/postgresql
ExecStart=/bin/ln -s /run/cloudsql/${WGLURP_METADATA_DB} /run/postgresql/.s.PGSQL.5432
RemainAfterExit=true
ExecStopPost=/bin/rm -f /run/postgresql/.s.PGSQL.5432
ExecStopPost=/bin/rmdir /run/postgresql

[Install]
WantedBy=wglurp-sql.target
EOF

# Trigger systemd and enable services
systemctl daemon-reload
systemctl enable cloud-sql-proxy.service
systemctl enable cloud-sql-symlink.service

# Data file mount setup

# Set up fstab entries for our data mount, and the key mount
# NOTE: Only the key mount can be mounted automatically;
# the data mount has to be decrypted first.
mkdir /mnt/data
mkdir /mnt/data-key
cat - >> /etc/fstab <<EOF
LABEL=data-key    /mnt/data-key  ext4  ro      0 1
LABEL=wglurp-data /mnt/data      xfs   noauto  0 1
EOF

# Link to the unencrypted config files
rm /usr/etc/wglurp.conf /usr/etc/wglurp.d/example
rmdir /usr/etc/wglurp.d
ln -s /mnt/data/wglurp.conf /usr/etc/wglurp.conf
ln -s /mnt/data/wglurp.conf.d /usr/etc/wglurp.d

cat - > /etc/systemd/system/wglurp-data-unlock.service <<EOF
[Unit]
Description=Unlock the encrypted data partition
Requires=network-online.target wglurp-environment.service
After=network-online.target wglurp-environment.service
DefaultDependencies=true

[Service]
Type=oneshot
EnvironmentFile=/run/wglurp/env
ExecStart=/usr/bin/gcloud kms decrypt --ciphertext-file=/mnt/data-key/key --plaintext-file=/run/wglurp/data-key --key=${WGLURP_METADATA_DATA_KEY}
ExecStart=/sbin/cryptsetup --key-file=/run/wglurp/data-key luksOpen /dev/sdb2 wglurp-data
RemainAfterExit=true
ExecStopPost=/sbin/cryptsetup luksClose wglurp-data
ExecStopPost=/bin/rm /run/wglurp/data-key
EOF
cat - > /etc/systemd/system/wglurp-data-mount.service <<EOF
[Unit]
Description=Mount the encrypted data partition
Requires=wglurp-data-unlock.service
After=wglurp-data-unlock.service
DefaultDependencies=true

[Service]
Type=oneshot
EnvironmentFile=/run/wglurp/env
ExecStart=/bin/mount /mnt/data
RemainAfterExit=true
ExecStopPost=/bin/umount -f /mnt/data

[Install]
WantedBy=wglurp-sql.target
EOF

# Enable the services from this section.
# (Again, other services will call us as needed!)
systemctl daemon-reload

# Keytab setup

cat - > /etc/systemd/system/wglurp-ldap-keytab.service <<EOF
[Unit]
Description=Maintain a Krb5 credentials cache for LDAP
Requires=network-online.target wglurp-data-mount.service wglurp-run-dir.service
After=network-online.target wglurp-data-mount.service wglurp-run-dir.service
DefaultDependencies=true

[Service]
Type=forking
ExecStart=/usr/bin/k5start -r stanford.edu -p /run/wglurp/k5start_ldap.pid -K 10 -x -b -f /mnt/data/ldap.keytab -U -k /run/wglurp/k5start_ldap.cache
PIDFile=/run/wglurp/k5start_ldap.pid
EOF
systemctl daemon-reload
systemctl enable wglurp-ldap-keytab.service

# Clean Up and Reboot!

# Clean up temporary packages
apt-get -y purge ${TEMPORARY_PACKAGES[@]}
apt-get -y autoremove
apt-get -y clean

# Clean up Git repos
cd /root
rm -rf /root/git
rm -rf /root/python-distutils-extra
rm -rf /root/python-apt

# If the NO_REBOOT metadata variable is defined, then just exit.
# Otherwise, reboot so patches can take effect, and to start services!
if [ ${WGLURP_METADATA_NO_REBOOT:-z} = 'z' ]; then
    exit 0
else
    exec shutdown -r now
fi
