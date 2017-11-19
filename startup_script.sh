#!/bin/bash
#

# Make sure we error out if a command fails.
set -e

# This is the list of trusted GPG key fingerprints.  One per line.
TRUSTED_KEYS=(
FC411D5BA332BE922D2CE7F1A2BF8503E5E5AFC8
)

# This is the Git repo and tag to pull
GIT_REPO=https://github.com/akkornel/wglurp.git
GIT_TAG=bootstrap_gcp-latest

# We'll be sending messages to Slack, so get our post URL.
export SLACK_URL=$(curl -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/attributes/SLACK_URL)

# Notify and start the early script
curl -X POST --data-urlencode 'payload={"text": "Builder bootstrap early script running!"}' ${SLACK_URL}

# Start by pulling in Git, GPG, and GPG's curl support
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y curl git gnupg gnupg-curl

# Pull in, and trust, each key.
gpg --keyserver keys.gnupg.net --recv-keys ${TRUSTED_KEYS[@]}
for key in ${TRUSTED_KEYS[@]}; do
    echo "${key}:6:" | gpg --import-ownertrust
done
gpg --batch --update-trustdb

# Clone our repo, check our tag's signature, and check out the tag.
git clone ${GIT_REPO} /root/bootstrap
cd /root/bootstrap
git tag -v ${GIT_TAG}
git checkout -q ${GIT_TAG}

# Notify and hand off to the actual bootstrap script
curl -X POST --data-urlencode 'payload={"text": "Builder early bootstrap handing off..."}' ${SLACK_URL}
exec /root/bootstrap/bootstrap.sh
