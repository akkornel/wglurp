#!/bin/bash
# 

# This is the list of trusted GPG keys.  One per line.
TRUSTED_KEYS=(
FC411D5BA332BE922D2CE7F1A2BF8503E5E5AFC8
)

# This is the Git repo and tag to pull
GIT_REPO=https://github.com/akkornel/wglurp.git
GIT_TAG=bootstrap_gcp-latest

# Do the bootstrap
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y git gnupg gnupg-curl
gpg --recv-keys ${TRUSTED_KEYS[@]}
for key in ${TRUSTED_KEYS[@]}; do
    gpg --edit-key $key trust 5 save
git clone ${GIT_REPO} /root/bootstrap
cd /root/bootstrap
git tag -v ${GIT_TAG}
git checkout ${GIT_TAG}
exec /root/bootstrap/bootstrap.sh
