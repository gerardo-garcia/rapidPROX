#! /bin/bash

# Copyright (C) 2023-2026 rapidPROX contributors
# SPDX-License-Identifier: Apache-2.0

set -ex

source config

if [[ -z "${IMAGEREPOUSER}" ]]; then
    echo "Set env var IMAGEREPOUSER. Exiting..."
    exit
fi

for i in "${PROXIMAGENAME}" "${RAPIDIMAGENAME}"; do
    docker rmi -f "${IMAGEREPOUSER}/${i}"
    docker tag "${i}" "${IMAGEREPOUSER}/${i}"
    docker push "${IMAGEREPOUSER}/${i}"
done
