This document contains the list of steps that need to be run when you are
setting up a new environment.

# 

Set the following custom metadata:

* `SLACK_URL`: A Slack webhook URL.  Notifications will go here.

* `DB`: The ID of the Cloud SQL PostgreSQL to use.

* `DATA_KEY`: The ID of the KMS key which is used for data drive decryption.

* `NO_REBOOT`: Optional.  If set (to anything), then do not reboot after
  initial setup.

# Set up the data drive

Your new 10G data drive should be attached at `/dev/sdb`.

1. Partition the data drive

       parted /dev/sdb mklabel gpt
       parted /dev/sdb mkpart ext4 4M 128M
       parted /dev/sdb mkpart luks 128M 100%

1. Make a new ext4 partition, with label `data-key`, and mount it read-write.
   (The bootstrap script will have taken care of directory creation and
   `/etc/fstab` modification.)

       mkfs.ext4 -L data-key /dev/sdb1
       mount -o rw /mnt/data-key

1. Create an encryption key (in `/run`, which is kept in RAM), format the
   encrypted partition, open it for the first time, and set up a filesystem on
   it.

       dd if=/dev/urandom of=/run/zzkey bs=1K count=32
       cryptsetup -c aes-xts-essiv:sha256 --key-size=256 --key-file=/run/zzkey --use-urandom luksFormat /dev/sdb2
       cryptsetup --key-file=/run/zzkey luksOpen /dev/sdb2 wglurp-data
       mkfs.xfs -L wglurp-data /dev/mapper/wglurp-data
       mount /mnt/data
       mkdir /mnt/data/wglurp.conf.d

   At this point, we have a partition, but the key is only in RAM.

1. Encrypt the key file using the appropriate data key, whose resource ID you
   provided via instance metadata.

       gcloud kms encrypt --plaintext-file=/run/zzkey --ciphertext-file=/mnt/data-key/key --key=$(/usr/bin/curl -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/attributes/DATA_KEY)

   At this point, the raw key remains at `/run/zzkey` (for now), and the
   KMS-encrypted key is now at `/mnt/data-key/key`.

1. Try decrypting the just-encrypted key, and make sure that the key matches
   the one you generated.

       gcloud kms decrypt --ciphertext-file=/mnt/data-key/key --plaintext-file=/run/zzkey2 --key=$(/usr/bin/curl -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/attributes/DATA_KEY)
       cmp /run/zzkey /run/zzkey2

    If everything worked, then the final `cmp` command should not output
    anything, and its exit code should be zero.  That means our KMS-encrypted
    key is correctly decrypting.

1. Unmount everything, and make sure the data partition can mount
   automatically.

       umount /mnt/data
       cryptsetup luksClose wglurp-data
       systemctl start wglurp-data-mount

   If everything worked, then running `mount | grep /mnt/data` should show that
   `/mnt/data` is mounted!

1. Clean up the remaining key files in RAM.

       rm /run/zzkey /run/zzkey2
