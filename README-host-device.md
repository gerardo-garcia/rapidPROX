# rapid PROX with host-device

This is to be used on systems with [host-device plugin](https://www.cni.dev/plugins/current/main/host-device/), without SR-IOV device plugin, and replaces relevant parts in [README.md](./README.md).

Because of difference between host-device plugin and SR-IOV Device Plugin, we use config files and deployment descriptors in [k8s/host-device/](./k8s/host-device/).

## Setup

Tor those PCI Eth devices where you bound DPDK driver to, appropriately update the IDs in [k8s/host-device/host-device-nad.yaml](./k8s/host-device/host-device-nad.yaml), [k8s/host-device/2-swap.yaml](./k8s/host-device/2-swap.yaml) and [k8s/host-device/3-gen.yaml](./k8s/host-device/3-gen.yaml).

## Start test

Create prox namespace with
```
cd k8s/host-device
kubectl apply -f 0-ns.yaml
```

Create NADs with
```
kubectl apply -f host-device-nad.yaml
```

Create test pods and services, and do the test run with
```
kubectl apply -f 1-ip-cm.yaml -f 2-swap.yaml -f 3-gen.yaml -f 4-pushgateway.yaml -f 5-controller.yaml
```
