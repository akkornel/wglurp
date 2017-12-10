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
krb5-user # Kerberos utilities
kstart # For Kerberos credentials caches
ldap-utils # Helpful LDAP utilities
libsasl2-modules-gssapi-mit # Needed for LDAP GSSAPI auth
postgresql-client-9.6 # For Postgres client libs
python3.6 # Python 3.6!
)
TEMPORARY_PACKAGES=(
build-essential # Misc. build tools
intltool # For building python-apt
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

# Get the Slack URL, for notifications
export SLACK_URL=$(curl -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/attributes/SLACK_URL)

# Packaged Software Installation

# Set up 3rd-party repositories
echo 'Adding apt repos'
add-apt-repository -y ppa:jonathonf/python-3.6
cat - > /etc/apt/sources.list.d/pgdg.list <<EOF
deb http://apt.postgresql.org/pub/repos/apt/ xenial-pgdg main
EOF
curl https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -

# Update package lists, bring current packages up-to-date, and install stuff.
curl -X POST --data-urlencode 'payload={"text": "Package Install..."}' ${SLACK_URL}
echo 'Updating package lists'
apt-get -q -q update
echo 'Upgrading existing packages'
apt-get -q -q -y dist-upgrade
echo 'Installing packages'
apt-get -q -q -y install ${PERMANENT_PACKAGES[@]} ${TEMPORARY_PACKAGES[@]}

# Make a space for Git clones and other sources
mkdir /root/git /root/src

# Python Prerequisite Software Installation

# Get setuptools, and build for Python 3.6
curl -X POST --data-urlencode 'payload={"text": "SW install 1..."}' ${SLACK_URL}
echo 'Installing Python 3.6 setuptools'
git clone https://github.com/pypa/setuptools.git /root/git/setuptools
cd /root/git/setuptools
git checkout -q ${SETUPTOOLS_VERSION}
python3.6 ./bootstrap.py
python3.6 ./setup.py -q build
python3.6 ./setup.py -q install

# Get pip, and build for Python 3.6
echo 'Installing Python 3.6 pip'
git clone https://github.com/pypa/pip.git /root/git/pip
cd /root/git/pip
git checkout -q ${PIP_VERSION}
python3.6 ./setup.py -q build
python3.6 ./setup.py -q install

# Install python-distutils-extra, needed by python-apt.
cd /root/src
echo 'Installing python-distutils-extra from apt source'
apt-get -q -q source --download-only python-distutils-extra
tar -xzf python-distutils-extra*.tar.gz
cd python-distutils-extra-*
python3.6 ./setup.py -q build
python3.6 ./setup.py -q install

# Install python-apt
cd /root/src
echo 'Installing python-apt from apt source'
apt-get -q -q source --download-only python-apt
tar -xJf python-apt*.tar.xz
cd python-apt-*
python3.6 ./setup.py -q build
python3.6 ./setup.py -q install

# Python Software Installation

# Bring in Python stuff, using pip's hash checking
curl -X POST --data-urlencode 'payload={"text": "SW install 2..."}' ${SLACK_URL}
echo 'Installing Python packages from PyPi'
pip3.6 install --require-hashes -r /root/bootstrap/requirements/ldap-client.txt

# Get syncrepl_client, and build for Python 3.6
curl -X POST --data-urlencode 'payload={"text": "SW install 3..."}' ${SLACK_URL}
echo "Installing syncrepl_client from GitHub (version ${SYNCREPL_CLIENT_VERSION})"
git clone git://github.com/akkornel/syncrepl.git /root/git/syncrepl
cd /root/git/syncrepl
git checkout -q ${SYNCREPL_CLIENT_VERSION}
python3.6 ./setup.py -q build
python3.6 ./setup.py -q install

# Get wglurp, and build for Python 3.6
echo "Installing WGLURP from GitHub (version ${WGLURP_VERSION})"
git clone git://github.com/akkornel/wglurp.git /root/wglurp
cd /root/wglurp
git checkout -q ${WGLURP_VERSION}
python3.6 ./setup.py -q build
python3.6 ./setup.py -q install

# Environment Setup

# Set up a run directory
curl -X POST --data-urlencode 'payload={"text": "Service install..."}' ${SLACK_URL}
echo 'Setup wglurp-run-dir'
cat - > /etc/systemd/system/wglurp-run-dir.service <<EOF
[Unit]
Description=Create the /run/wglurp directory tree
DefaultDependencies=true

[Service]
Type=oneshot
ExecStart=/bin/mkdir /run/wglurp /run/wglurp/metrics
RemainAfterExit=true
ExecStopPost=/bin/rm -rf /run/wglurp
EOF

# Set up a service that outputs environment variablaes
echo 'Setup wglurp-env'
cat - > /usr/sbin/wglurp-env.sh <<'EOF'
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

# Cloud SQL Setup

# Install and set up the Cloud SQL Proxy service
echo 'Setup cloud_sql_proxy and cloud-sql-proxy'
wget https://dl.google.com/cloudsql/cloud_sql_proxy.linux.amd64 \
     -O /usr/sbin/cloud_sql_proxy
chmod a+x /usr/sbin/cloud_sql_proxy
cat - > /etc/systemd/system/cloud-sql-proxy.service <<'EOF'
[Unit]
Description=Proxies connections to Google Cloud SQL
Documentation=https://github.com/GoogleCloudPlatform/cloudsql-proxy
Requires=network-online.target wglurp-environment.service
After=network-online.target wglurp-environment.service
DefaultDependencies=true
ConditionPathExists=/usr/sbin/cloud_sql_proxy

[Service]
Type=simple
EnvironmentFile=/run/wglurp/env
ExecStart=/usr/sbin/cloud_sql_proxy -verbose -instances=${WGLURP_METADATA_DB}=tcp:5432
EOF

# Data file mount setup

# Set up fstab entries for our data mount, and the key mount
# NOTE: Only the key mount can be mounted automatically;
# the data mount has to be decrypted first.
echo 'Prep data mount'
mkdir /mnt/data
mkdir /mnt/data-key
cat - >> /etc/fstab <<EOF
LABEL=data-key    /mnt/data-key  ext4  ro      0 1
# The mount for /mnt/data is defined as a native systemd mount, because
# we need to unlock the volume before it can be used.
EOF

# Link to the unencrypted config files
rm /usr/etc/wglurp.conf /usr/etc/wglurp.d/example
rmdir /usr/etc/wglurp.d
ln -s /mnt/data/wglurp.conf /usr/etc/wglurp.conf
ln -s /mnt/data/wglurp.conf.d /usr/etc/wglurp.d

echo 'Setup wglurp-data-unlock and wglurp-data-mount'
cat - > /etc/systemd/system/wglurp-data-unlock.service <<'EOF'
[Unit]
Description=Unlock the encrypted data partition
RequiresMountsFor=/mnt/data-key
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
cat - > /etc/systemd/system/mnt-data.mount <<EOF
[Unit]
Description=Mount the encrypted data partition
Requires=wglurp-data-unlock.service
After=wglurp-data-unlock.service
DefaultDependencies=true

[Mount]
What=LABEL=wglurp-data
Where=/mnt/data
Type=xfs
Options=noauto
EOF

# Keytab setup

echo 'Setup wglurp-keytab'
cat - > /etc/systemd/system/wglurp-ldap-keytab.service <<EOF
[Unit]
Description=Maintain a Krb5 credentials cache for LDAP
RequiresMountsFor=/mnt/data
Requires=network-online.target wglurp-run-dir.service
After=network-online.target wglurp-run-dir.service
DefaultDependencies=true

[Service]
Type=forking
ExecStart=/usr/bin/k5start -r stanford.edu -p /run/wglurp/k5start_ldap.pid -K 10 -x -b -f /mnt/data/ldap.keytab -U -k /run/wglurp/k5start_ldap.cache
PIDFile=/run/wglurp/k5start_ldap.pid
EOF

# Clean Up and Reboot!

# Trigger systemd reload, and enable appropriate services
curl -X POST --data-urlencode 'payload={"text": "Notify and cleanup..."}' ${SLACK_URL}
echo 'Notify Systemd and enable services'
systemctl daemon-reload
systemctl enable wglurp-sql.target

# Clean up temporary packages
echo 'Remove named temporary packages'
apt-get -q -q -y purge ${TEMPORARY_PACKAGES[@]}
echo 'Remove other temporary packages'
apt-get -q -q -y autoremove

# Clean up Git repos
echo 'Clean up downloads'
cd /root
rm -rf /root/git
rm -rf /root/src
apt-get -q -q -y clean

# If the NO_REBOOT metadata variable is defined, then just exit.
# Otherwise, reboot so patches can take effect, and to start services!
echo 'Complete!'
curl -X POST --data-urlencode 'payload={"text": "Bootstrap complete!"}' ${SLACK_URL}
if [ ${WGLURP_METADATA_NO_REBOOT:-z} = 'z' ]; then
    exit 0
else
    exec shutdown -r now
fi
