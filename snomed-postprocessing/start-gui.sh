#!/bin/bash

CURRENT_VERSION="0.9.9"
DEFAULT_PORT="8501"

if [[ $# -eq 0 ]]; then
    VERSION=$CURRENT_VERSION
    PORT=$DEFAULT_PORT
elif [[ $# -eq 1 ]]; then
    VERSION=$CURRENT_VERSION
    PORT=$1
elif [[ $# -eq 2 ]]; then
    VERSION=$2
    PORT=$1
fi

docker run \
--rm \
-p "${PORT}":8501 \
ghcr.io/medizininformatik-initiative/gemtex/snomed-postprocessing:"${VERSION}" \
start-gui
