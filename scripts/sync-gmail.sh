#!/usr/bin/env sh
set -eu

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <account> <destination>" >&2
  exit 2
fi

mailvault sync \
  --account "$1" \
  --host imap.gmail.com \
  --provider gmail \
  --auth app-password \
  --destination "$2" \
  --scope all \
  --soft-cap 1GiB \
  --hard-cap 1.25GiB
