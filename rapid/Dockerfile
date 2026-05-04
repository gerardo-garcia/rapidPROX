##
## Copyright (c) 2023-2025 rapidPROX contributors
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

##################################################
# Build all components in separate builder image #
##################################################

FROM ubuntu:24.04 AS builder
ENV DEBIAN_FRONTEND=noninteractive

### ---------------------------------------------------------------
### Install all required packages (ARM-friendly)
### Must combine update + install in ONE layer
### Must remove apt lists afterwards to keep image small
### libibverbs-dev is to support Mellanox cards (no OFED installation needed) 
### ---------------------------------------------------------------
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get install -y \
	git wget gcc unzip libpcap-dev libncurses5-dev \
	libedit-dev liblua5.3-dev linux-headers-generic iperf3 pciutils \
	libnuma-dev vim tuna make driverctl openssh-server sudo \
	meson python3-pyelftools pkg-config nasm libssl-dev libibverbs-dev \
    && rm -rf /var/lib/apt/lists/*

ARG DPDK_VERSION=24.11.2
ENV DPDK_VERSION=${DPDK_VERSION}

ARG BUILD_DIR="/opt/rapid"
ENV BUILD_DIR=${BUILD_DIR}
WORKDIR ${BUILD_DIR}

# Define the version of Multi Buffer Library by selecting one of the following lines
ARG MULTI_BUFFER_LIB_VER='None'
#ARG MULTI_BUFFER_LIB_VER=1.3
#ARG MULTI_BUFFER_LIB_VER=1.5
# End of the Multi Buffer version selection

# Install multi-buffer library
RUN if [ ${MULTI_BUFFER_LIB_VER} != None ] ; then \
	wget https://github.com/01org/intel-ipsec-mb/archive/v${MULTI_BUFFER_LIB_VER}.zip \
	&& unzip v${MULTI_BUFFER_LIB_VER}.zip \
	&& cd ${BUILD_DIR}/intel-ipsec-mb-${MULTI_BUFFER_LIB_VER} \
	&& make \
	&& make install \ 
	&& cd ${BUILD_DIR};\ 
    fi

# Install DPDK
RUN git clone https://github.com/DPDK/dpdk.git
WORKDIR ${BUILD_DIR}/dpdk
RUN git checkout v${DPDK_VERSION}
RUN meson setup build \
    --buildtype=release \
    -Denable_driver_sdk=true \
    -Ddefault_library=shared \
    -Dcpu_instruction_set=generic \
#    -Dlibdir=lib/aarch64-linux-gnu \
#    -Dlibdir=lib/x86_64-linux-gnu \
    && ninja -C build install

WORKDIR ${BUILD_DIR}

# Install Prox
RUN git clone https://github.com/rapidPROX/rapidPROX.git \
	&& cd rapidPROX/src \
	&& COMMIT_ID=$(git rev-parse HEAD) \
	&& echo "${COMMIT_ID}" > ${BUILD_DIR}/commit_id \
	&& meson build \
	&& ninja -C build \
	&& cp ${BUILD_DIR}/rapidPROX/rapid/start.py ${BUILD_DIR}/start.py \
	&& cp ${BUILD_DIR}/rapidPROX/rapid/rapid_rsa_key.pub ${BUILD_DIR}/rapid_rsa_key.pub \
	&& cp ${BUILD_DIR}/rapidPROX/src/build/prox ${BUILD_DIR}/prox

# Build and copy port info app
WORKDIR ${BUILD_DIR}/rapidPROX/rapid/port_info
RUN meson build \
	&& ninja -C build \
	&& cp ${BUILD_DIR}/rapidPROX/rapid/port_info/build/port_info_app ${BUILD_DIR}/port_info_app

RUN ldconfig && pkg-config --modversion libdpdk > ${BUILD_DIR}/dpdk_version

# Create Minimal Install
RUN ldd ${BUILD_DIR}/prox | awk '$2 ~ /=>/ {print $3}' >> ${BUILD_DIR}/list_of_install_components \
	&& echo "${BUILD_DIR}/prox" >> ${BUILD_DIR}/list_of_install_components \
	&& echo "${BUILD_DIR}/port_info_app" >> ${BUILD_DIR}/list_of_install_components \
	&& echo "${BUILD_DIR}/commit_id" >> ${BUILD_DIR}/list_of_install_components \
	&& echo "${BUILD_DIR}/dpdk_version" >> ${BUILD_DIR}/list_of_install_components \
	&& echo "${BUILD_DIR}/start.py" >> ${BUILD_DIR}/list_of_install_components \
	&& echo "${BUILD_DIR}/rapid_rsa_key.pub" >> ${BUILD_DIR}/list_of_install_components \
	&& LIBDIR=$(pkg-config --variable=libdir libdpdk) \
	&& find "$LIBDIR" -not -path '*/\.*' >> ${BUILD_DIR}/list_of_install_components \
	&& tar -czvhf ${BUILD_DIR}/install_components.tgz -T ${BUILD_DIR}/list_of_install_components

################################
# Create smaller runtime image #
################################
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

### ---------------------------------------------------------------
### Install all required packages (ARM-friendly)
### Must combine update + install in ONE layer
### Must remove apt lists afterwards to keep image small
### ---------------------------------------------------------------
RUN apt-get update && \
	DEBIAN_FRONTEND=noninteractive \
	apt-get install -y \
		unzip sudo openssh-server liblua5.3-dev libibverbs-dev busybox curl vim \
	&& rm -rf /var/lib/apt/lists/*

ARG BUILD_DIR="/opt/rapid"
ENV BUILD_DIR=${BUILD_DIR}

COPY --from=builder ${BUILD_DIR}/install_components.tgz ${BUILD_DIR}/install_components.tgz
WORKDIR /
RUN tar -xvf ${BUILD_DIR}/install_components.tgz --skip-old-files
RUN ldconfig
RUN rm ${BUILD_DIR}/install_components.tgz

# Expose SSH and PROX ports
EXPOSE 22 8474
#RUN useradd -rm -d /home/rapid -s /bin/bash -g root -G sudo -u 1000 rapid \
RUN useradd -rm -d /home/rapid -s /bin/bash -g root -G sudo rapid \
	&& chmod 777 ${BUILD_DIR} \
	&& echo 'rapid:rapid' | chpasswd \
	&& mkdir /home/rapid/.ssh \
# Copy SSH keys
	&& cp ${BUILD_DIR}/rapid_rsa_key.pub /home/rapid/.ssh/authorized_keys \
	&& chown rapid:root /home/rapid/.ssh/authorized_keys \
	&& chmod 600 /home/rapid/.ssh/authorized_keys \
# Copy startup script
##	&& cp ${BUILD_DIR}/start.py /start.py \
	&& chmod +x ${BUILD_DIR}/start.py
WORKDIR ${BUILD_DIR}
ENTRYPOINT ["/opt/rapid/start.py"]
