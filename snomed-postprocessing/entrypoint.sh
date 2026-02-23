#! /bin/bash

if [[ $# -eq 0 ]] ; then
    program-entry --help
    exit 0
fi

"$1" "${@:2}"