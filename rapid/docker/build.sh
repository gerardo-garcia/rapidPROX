#! /bin/bash

# Copyright (C) 2023-2026 rapidPROX contributors
# SPDX-License-Identifier: Apache-2.0

set -ex

source config

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RAPID_VERSION="0.0.0+$(git -C "${REPO_ROOT}" rev-parse --short HEAD)"

docker build -f prox/Dockerfile -t "${PROXIMAGENAME}" "${REPO_ROOT}"
docker build -f rapid/Dockerfile --build-arg RAPID_VERSION="${RAPID_VERSION}" \
        -t "${RAPIDIMAGENAME}" "${REPO_ROOT}"
