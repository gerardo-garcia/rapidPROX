# prox

Deploys `replicaCount` (default 2) PROX dataplane pods on a dedicated
[Multus](https://github.com/k8snetworkplumbingwg/multus-cni) network -- SR-IOV
or PCI passthrough -- and a "rapid" controller pod already wired up to drive
a [rapidPROX](https://github.com/rapidPROX/rapidPROX) peak-throughput test
between them.

Resources deployed: a `StatefulSet` (ordinal identity -- `prox-0`, `prox-1`,
...) for the PROX replicas, one `NetworkAttachmentDefinition`, a headless
governing `Service`, a `ConfigMap` with the dataplane base IP, and (unless
`controller.enabled=false`) a controller `Deployment` plus a `ConfigMap`
holding a ready-to-use `rapid.env` generated from the StatefulSet's ordinal
DNS names -- no manual environment/machine-map authoring needed. See
`templates/NOTES.txt` (`helm get notes` after install, or `helm install
--dry-run` locally) for the exact command to trigger a run.

## How a test run actually works

`rapid_parser.py`'s `RapidConfigParser.parse_config` only strictly needs
`admin_ip`/`admin_port`/`socket_port` per machine in `rapid.env` -- dataplane
IPs and machine names both come from elsewhere (the `START_DP_IP` env var
and the `.test` file's `[TestMx]` sections, respectively). Because the
StatefulSet gives each replica a deterministic DNS name
(`<release>-0.<release>.<namespace>.svc.cluster.local`, `-1`, ...), this
chart renders the whole `rapid.env` at install time -- no in-cluster
discovery, no RBAC. The shipped `rapid/machine.map` already maps
`TestM1→1`, `TestM2→2`, ... which lines up with ordinals 0, 1, ... directly.

## Prerequisites

- A Kubernetes cluster with [Multus CNI](https://github.com/k8snetworkplumbingwg/multus-cni)
  installed.
- A device plugin advertising the resource named in `network.resourceName`
  on your worker nodes -- e.g. the
  [SR-IOV Network Device Plugin](https://github.com/k8snetworkplumbingwg/sriov-network-device-plugin)
  for both `network.mode: sriov` and `network.mode: hostDevice`.
- 1Gi (or 2Mi, if you change `resources`/`hugepagesMedium`) hugepages
  available on the nodes that will run these pods.
- If `network.ipam.enabled: true`: the [whereabouts](https://github.com/k8snetworkplumbingwg/whereabouts)
  CNI IPAM plugin installed.

See the top-level repo's `rapid/README.k8s` and `README.md` for background on
the overall rapidPROX Kubernetes setup this chart is part of.

## Installing

```
helm install prox oci://ghcr.io/<owner>/charts/prox --version <version> \
  --namespace prox --create-namespace \
  --set network.resourceName=intel.com/intel_sriov_vfio \
  --set network.vlan=100
```

Or from a local checkout:

```
helm install prox ./charts/prox -n prox --create-namespace
```

## Values

| Key | Default | Description |
|---|---|---|
| `replicaCount` | `2` | Number of PROX replicas. The test runs between two of them; see chart NOTES. |
| `image.repository` | `ghcr.io/gerardo-garcia/prox` | prox image, published by `.github/workflows/docker-publish.yml` as `ghcr.io/<repository_owner>/prox`. Override to point at your own fork/registry. |
| `image.tag` | `latest` | Image tag. |
| `image.pullPolicy` | `IfNotPresent` | |
| `network.mode` | `sriov` | `sriov` (SR-IOV VF via sriov-cni, supports VLAN tagging) or `hostDevice` (whole PCI device via host-device CNI, no CNI-level VLAN tagging). |
| `network.resourceName` | `intel.com/intel_sriov_vfio` | Device-plugin resource backing the dataplane NIC. Used for both the Multus `resourceName` annotation and the pod's resource request/limit. |
| `network.vlan` | `0` | 802.1Q VLAN id. Only applied when `network.mode=sriov`; `0` disables tagging. In `hostDevice` mode the VLAN must already be configured on the device/switch port out of band. |
| `network.mtu` | `""` | Optional MTU override for the CNI plugin. |
| `network.spoofchk` | `off` | sriov-cni anti-spoofing (`sriov` mode only). |
| `network.trust` | `on` | sriov-cni VF trust (`sriov` mode only). |
| `network.ipam.enabled` | `false` | Enable CNI-level (whereabouts) IPAM. Leave disabled for DPDK/vfio-pci use (the usual case): the interface never appears in the pod's kernel netns, so kernel IPAM is moot. |
| `network.ipam.subnet` | `""` | CIDR for whereabouts, required if `ipam.enabled`. |
| `network.ipam.rangeStart` / `rangeEnd` | `""` | Optional address range within `subnet`. |
| `network.ipam.gateway` | `""` | Optional gateway for whereabouts. |
| `dataplane.startIP` | `10.10.10.100/24` | Base address rapidPROX itself hands out sequentially to each machine it configures (`START_DP_IP`, see `rapid/runrapid.py`), independent of any CNI IPAM above. |
| `resources` | 4 CPU / 2Gi mem / 1Gi hugepages, req=lim | Per-replica resources. See the repo's node-sizing guidance for how to size this for your traffic target. |
| `hugepagesMedium` | `HugePages-1Gi` | Must match whichever `hugepages-<size>` key you use under `resources`. |
| `securityContext.privileged` | `true` | PROX needs privileged + `IPC_LOCK`/`SYS_ADMIN` for hugepages/DPDK. |
| `spreadAcrossNodes` | `true` | Best-effort `topologySpreadConstraints` so replicas land on different nodes. |
| `nodeSelector` / `tolerations` / `affinity` | `{}` / `[]` / `{}` | Standard pod scheduling overrides for the PROX StatefulSet. |
| `podAnnotations` / `podLabels` | `{}` | Extra metadata merged onto PROX pods. |
| `controller.enabled` | `true` | Deploy the "rapid" controller pod + its generated `rapid.env` ConfigMap. Set `false` to deploy PROX infrastructure only (see NOTES for the manual flow). |
| `controller.image.repository` / `tag` / `pullPolicy` | `ghcr.io/gerardo-garcia/rapid` / `latest` / `IfNotPresent` | rapid image, published by `.github/workflows/docker-publish.yml` as `ghcr.io/<repository_owner>/rapid`. |
| `controller.test` | `tests/basicrapid.test` | Default `.test` file (path inside the rapid image) used for manual runs and for `runOnStart`. |
| `controller.runtime` | `10` | Seconds per test iteration, maps to `runrapid.py --runtime`. |
| `controller.runOnStart` | `false` | If `true`, the controller runs `controller.test` once on start (and again on every pod restart/upgrade) instead of idling for a manual `kubectl exec`. |
| `controller.extraTestFiles` | `{}` | Map of `filename: content` for custom `.test` files mounted under `tests/` in the controller pod -- e.g. for `replicaCount > 2`, which the shipped tests don't cover. |
| `controller.resources` | 200m/256Mi req, 500m/512Mi lim | Controller pod resources (pure control-plane, no DPDK/hugepages). |

## Ports

- `8474/tcp` -- PROX's own command socket (only responds once PROX has been
  started via the control sidecar).
- `9090/tcp` -- HTTP control sidecar (`start.py`, always up), used to upload
  configs and start/stop PROX without SSH.

## Triggering a test

```
kubectl -n <namespace> exec -it deploy/<release>-controller -- \
  ./runrapid.py --test tests/basicrapid.test --runtime 10
```

`rapid.env` and `machine.map` are already correct in the controller pod, so
no flags beyond `--test`/`--runtime` are needed. This is deliberately kept
to `kubectl exec` rather than a network-triggerable API for now -- a small
HTTP wrapper around `runrapid.py` (exposed via a `Service`) is a natural
follow-up if you want tests triggerable without cluster exec access; the
controller's file layout (`rapid.env` at the default location, test files
under `tests/`) is already compatible with that.
