#! /bin/bash

# Copyright (C) 2023-2026 rapidPROX contributors
# SPDX-License-Identifier: Apache-2.0

set -ex

source config

for i in "${PROXIMAGENAME}" "${RAPIDIMAGENAME}"; do
    docker rmi -f "${i}"
    docker rmi -f "${IMAGEREPOUSER}/${i}"
    echo "Manually delete remote repo image ${IMAGEREPOUSER}/${i}"
done
