#! /bin/bash

# Copyright (C) 2023-2026 rapidPROX contributors
# SPDX-License-Identifier: Apache-2.0

set -ex

docker run -d --restart always -p 5000:5000 --name local-registry registry:3
