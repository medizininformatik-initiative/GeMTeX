#! /bin/bash

if [[ $# -eq 0 ]] ; then
    program-entry --help
    echo
    echo
    echo "Additionally, you can start a gui for document logging with 'start-gui'."
    exit 0
fi

if [[ $1 = "start-gui" ]] ; then
  uv run streamlit run ./src/snomed_postprocessing/streamlit_app.py
elif [[ $1 = "log-critical-documents" ]] ; then
    log-critical-documents "${@:2}" --forbid-prompt
else
    "$1" "${@:2}"
fi