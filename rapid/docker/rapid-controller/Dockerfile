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
FROM python:3.12-slim

WORKDIR /opt

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl netcat-openbsd iputils-ping vim \
    && rm -rf /var/lib/apt/lists/*

# Clone repo from GitHub
RUN git clone https://github.com/rapidPROX/rapidPROX.git

WORKDIR /opt/rapidPROX/rapid

# Install Python package with your dependencies
RUN pip install --no-cache-dir .

RUN ln -s /usr/local/bin/python3 /usr/bin/python3

CMD ["sleep", "infinity"]
