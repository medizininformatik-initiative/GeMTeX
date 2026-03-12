#! /bin/bash

if [[ $# -eq 0 ]] ; then
    program-entry --help
    exit 0
fi

if [[ $1 = "log-critical-documents" ]] ; then
    log-critical-documents "${@:2}" --forbid-prompt
else
    "$1" "${@:2}"
fi