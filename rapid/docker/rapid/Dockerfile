##
## Copyright (c) 2026 rapidPROX contributors
## Copyright (c) 2019 Intel Corporation
##
## Licensed under the Apache License, Version 2.0 (the "License");
## you may not use this file except in compliance with the License.
## You may obtain a copy of the License at
##
##     http://www.apache.org/licenses/LICENSE-2.0
##
## Unless required by applicable law or agreed to in writing, software
## distributed under the License is distributed on an "AS IS" BASIS,
## WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
## See the License for the specific language governing permissions and
## limitations under the License.
##
##
## Build context for this Dockerfile is the REPOSITORY ROOT, not this
## directory, e.g.:
##   docker build -f rapid/docker/rapid/Dockerfile -t rapid .
## (rapid/docker/build.sh already does this.) That's so the image is built
## from the local working tree/commit being built, instead of re-fetching
## the upstream repo from GitHub.
##
FROM python:3.12-slim

WORKDIR /opt/rapidPROX

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl netcat-openbsd iputils-ping vim \
    && rm -rf /var/lib/apt/lists/*

# rapid's setup.py uses pbr, which otherwise derives the package version from
# git history; pin it explicitly so the build doesn't need .git at all.
ARG RAPID_VERSION=0.0.0+unknown
ENV PBR_VERSION=${RAPID_VERSION}

COPY rapid/ ./rapid/

WORKDIR /opt/rapidPROX/rapid

# Install Python package with your dependencies
RUN pip install --no-cache-dir .

RUN ln -s /usr/local/bin/python3 /usr/bin/python3

CMD ["sleep", "infinity"]
