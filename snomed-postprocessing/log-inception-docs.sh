#!/bin/bash

CURRENT_VERSION="0.9.5"

if [[ ! -d ./data ]]; then
  echo "This script assumes that a './data' folder exists here that will be mounted into the docker container."
  echo "All files (project zip, blacklist/whitelist hdf5) need to be stored there as well."
  echo "The log will be accessible there after the script has finished processing."
fi

if [[ $# -eq 0 ]]; then
  echo "Please provide at least the name of the INCEpTION Project zip file in the 'data' folder as first argument!"
  echo "Second argument is optional and can be the version of the script (default: ${CURRENT_VERSION})."
  exit 0
fi

if [[ $# -gt 1 ]]; then
  VERSION=$2
else
  VERSION=$CURRENT_VERSION
fi

ZIP=$1
if [[ "${ZIP: -4}" != ".zip" ]]; then
  ZIP="$1.zip"
fi

docker run \
--volume ./data:/app/data \
--rm \
ghcr.io/medizininformatik-initiative/gemtex/snomed-postprocessing:"${VERSION}" \
log-critical-documents /app/data/"$(basename "${ZIP}")"