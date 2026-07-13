# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

rapidPROX has two components that work together:

- **PROX** (`src/`, also reachable via the symlink `VNFs/DPPD-PROX`) — a DPDK-based C packet-processing engine ("Packet pROcessing eXecution"), formerly Intel DPPD-BNG. It implements configurable dataplane behaviors (generator, swap/loopback, BNG, routing, QoS, NAT, CG-NAT, ACL, impair, IPsec, etc.) driven by `.cfg`/`.lua` config files, and exposes a TCP command socket (port 8474) plus a curses/CLI UI for control and stats.
- **rapid** (`rapid/`) — a Python control-plane package ("Rapid Automated Performance Indication for Dataplane") that orchestrates two or more PROX instances (one as traffic Generator, one as SUT/Swap, optionally Impair gateways) to run automated peak-throughput (saturation) tests: it ramps traffic, uses a binary-search-like algorithm to find the max rate within packet-loss/latency bounds, and reports results to screen, Prometheus Pushgateway, or OPNFV Xtesting.

`VNFs/DPPD-PROX` is a plain symlink to `../src` — there's only one copy of the C source.

## Building PROX (the C engine, in `src/`)

Requires DPDK installed via meson/ninja (make support was dropped in DPDK 20.11). Set `PKG_CONFIG_PATH` to wherever DPDK's `.pc` files landed (e.g. `/usr/local/lib/x86_64-linux-gnu/pkgconfig` on Ubuntu, `/usr/local/lib64/pkgconfig` on RHEL/CentOS).

```
cd src/            # (or VNFs/DPPD-PROX, same directory)
meson setup build
ninja -C build/
```

Produces `build/prox`. Build options are in `src/meson_options.txt` (e.g. `-Dbng_qinq=disabled`, `-Ddbg=true`, `-Dcrc=soft`) — pass with `meson configure build/ -Doption=value`.

Run standalone with a config file, e.g.:
```
./build/prox -f ./config/nop.cfg
```
`-s` checks config syntax only, `-i` checks the init sequence only, `-n` uses NULL devices instead of real PCI (handy for `-i`/`-s` without hardware). See `src/README` for the full CLI and a description of the example configs under `src/config/` and `src/gen/`.

There is no unit test suite for the C code; validation is done by running full rapid test scenarios against a built `prox` binary.

## The `rapid` Python package (`rapid/`)

Installed as a package (`setup.py`/`setup.cfg`, PBR-based) exposing top-level modules like `runrapid`, `rapid_cli`, `rapid_test`, `prox_ctrl`, etc. (see `rapid/setup.cfg` `py_modules` for the full list — every new top-level script must be added there to be installed).

```
cd rapid/
pip install .              # or: pip install -e .
./runrapid.py --help
```

No formal test suite for the Python side either (no pytest/unittest dir); correctness is verified by actually running a test scenario end-to-end (see "Running a test" below), or the OPNFV Xtesting flow under `rapid/xtesting/`.

### Control-plane architecture

Entry point `runrapid.py`:
1. `RapidDefaults.test_params` supplies defaults, `RapidCli.process_cli` overlays CLI flags (`--env`, `--test`, `--map`, `--runtime`, `--configonly`, `--log`, `--screenlog`).
2. `RapidConfigParser.parse_config` (`rapid_parser.py`) reads three files: the **environment file** (default `rapid.env`, machine admin/dataplane IPs+MACs, SSH key, produced by `createrapid.py` for OpenStack or hand-written for other VIMs), the **test file** (default `tests/basicrapid.test`, INI-style — see `rapid/tests/*.test` and `rapid/tests/README`), and the **machine map** (`machine.map`, maps logical `TestMx` names in the test file to machine indices in the env file, so the same `.test` can run against different `.env` layouts).
3. `RapidTestManager.run_tests()` (`runrapid.py`) instantiates one `RapidMachine` (or `RapidGeneratorMachine` if the machine has `gencores`) per configured machine, starts PROX on all of them concurrently via a thread pool, connects to each PROX TCP socket, then for each test entry in the test file dispatches to a test class: `FlowSizeTest`/TST009/fixed_rate/increment_till_fail → `rapid_flowsizetest.py`, `corestatstest` → `rapid_corestatstest.py`, `portstatstest` → `rapid_portstatstest.py`, `impairtest` → `rapid_impairtest.py`, `irqtest` → `rapid_irqtest.py`, `warmuptest` → `rapid_warmuptest.py`. All test classes subclass `RapidTest` (`rapid_test.py`), which implements the shared per-iteration measurement loop (`run_iteration`): start latency cores, ramp speed, sample core/latency stats over `runtime` seconds, compute pps/latency-percentile/drop-rate, and report/push results.
4. Result formatting/publishing is data-driven by `rapid/format.yaml`, which maps each test class's internal field names to either a Prometheus Pushgateway payload or an OPNFV Xtesting JSON payload (`RapidTest.post_data`).

### Talking to a PROX instance: `prox_ctrl.py`

`prox_ctrl` abstracts *how* the controller reaches a machine, branching on `vim_type`:
- **SSH-based VIMs** (OpenStack, bare metal, generic k8s pods with SSH) — uses `rapid_sshclient.SSHClient` to run remote commands / scp files, and connects directly to the PROX TCP socket (`prox_sock`, port 8474) for the actual data-plane commands (`start`, `stop`, `speed`, `lat all stats`, `dp core stats`, `multi port stats`, ...).
- **`vim_type == "kubernetes"`** — no SSH; instead talks HTTP to a small control-plane sidecar (`rapid/start.py`, the ENTRYPOINT of the `prox` container, listening on port 9090) that exposes `GET /status`, `GET|PUT /file?path=...`, and `POST /cmd`. This lets the controller upload configs/scripts and run shell commands inside the PROX pod without SSH. The actual PROX dataplane socket (8474) is still used directly for stats/control once PROX is running.

`prox_sock` in `prox_ctrl.py` is the line-based text protocol client for the PROX TCP socket itself (distinct from the HTTP sidecar) — this is what the `RapidTest` iteration loop calls into for `core_stats()`, `lat_stats()`, `speed()`, etc.

### Dynamic dataplane IPs on Kubernetes

When running under k8s, machines don't have static dataplane IPs baked into `rapid.env`. Instead `RapidTestManager.__init__` (`runrapid.py`) reads `START_DP_IP` from the environment (a CIDR like `10.0.12.200/8`, injected via the `ip-config` ConfigMap, see `k8s/1-ip-cm.yaml`) and `run_tests()` assigns sequential IPs from that base to each machine's `dp_ip1` as it's configured.

## Running a test

Typical local/VM/OpenStack flow (see `rapid/README` for the full OpenStack/Packer/Heat walkthrough):
```
cd rapid/
./runrapid.py --env rapid.env --test tests/basicrapid.test --map machine.map
```

Kubernetes flow (see top-level `README.md`, or `README-host-device.md` for host-device-plugin instead of SR-IOV):
```
cd k8s/
kubectl apply -f 0-ns.yaml
kubectl apply -f 1-ip-cm.yaml -f 2-swap.yaml -f 3-gen.yaml -f 4-pushgateway.yaml -f 5-controller.yaml
kubectl logs -f -n prox controller
```
This deploys a `swap` pod (SUT/loopback), a `gen` pod (traffic generator), a Prometheus `pushgateway`, and a `controller` pod that runs `runrapid.py` against `swap`/`gen` over the HTTP sidecar on port 9090 and pushes results to Pushgateway (`curl http://<pushgateway-svc>/metrics | grep rapid` to read them back). Both `swap` and `gen` pods run the `prox` image (built from `rapid/docker/prox/Dockerfile`, entrypoint `rapid/start.py`); `controller` runs the `rapid` image (`rapid/docker/rapid/Dockerfile`, just `pip install`s this package from GitHub).

Older SR-IOV-only k8s flow (`rapid/README.k8s`, `createrapidk8s.py`, `pod-rapid.yaml`, `rapid.pods`, `rapid_k8s_deployment.py`/`rapid_k8s_pod.py`) predates the `k8s/` manifests above and is SSH-based rather than HTTP-sidecar-based — treat `k8s/` + `start.py` as the current path.

There's also a Helm chart at `rapid/rapid_helm_chart/` (Deployment + ServiceAccount) as an alternative to raw manifests.

## Building/publishing container images

Both `rapid/docker/prox/Dockerfile` and `rapid/docker/rapid/Dockerfile` build from the **repository root** as their Docker build context (they `COPY` local sources rather than `git clone` GitHub), so the image always reflects the working tree/commit actually being built. `prox`'s builder stage keeps `.git` around (via `COPY . `) because `src/meson.build` derives PROX's own version string from `git describe`; `rapid`'s image instead pins `pbr`'s version via a `RAPID_VERSION`/`PBR_VERSION` build-arg so it doesn't need `.git` at all.

```
cd rapid/docker/
./build.sh    # builds $PROXIMAGENAME (Ubuntu 24.04 + DPDK + prox binary) and $RAPIDIMAGENAME (python:3.12-slim + rapid package), context = repo root
./push.sh     # pushes to the registry configured in ./config (for local/dev use)
```
Image names/repo are set in `rapid/docker/config`. `./registry.sh` can spin up a local registry; `./clean.sh` removes local images.

The `prox` image DPDK version is pinned via `DPDK_VERSION` build-arg in `rapid/docker/prox/Dockerfile` (currently DPDK 24.11.2).

### CI-published images and Helm chart

`.github/workflows/docker-publish.yml` builds and pushes both images to GHCR on every push to `master` (tags: `latest`, `sha-<short>`) and on `vX.Y.Z` tags (adds `X.Y.Z`/`X.Y` tags) — `ghcr.io/<owner>/prox` and `ghcr.io/<owner>/rapid`. `.github/workflows/helm-publish.yml` does the same for the Helm chart at `charts/prox/`, pushing it as an OCI artifact to `oci://ghcr.io/<owner>/charts/prox` and, on tags, also attaching the packaged `.tgz` to a GitHub Release. GHCR packages are private on first publish — an owner needs to flip visibility to Public once per package (GITHUB_TOKEN can't do this).

`charts/prox/` deploys the actual PROX dataplane pods for performance testing: a `StatefulSet` (replica count configurable, default 2 — ordinal identity, not a plain `Deployment`, specifically so pod DNS names are deterministic) with each pod attached via Multus to one templated `NetworkAttachmentDefinition` (SR-IOV or PCI passthrough/host-device, VLAN and IPAM configurable through `values.yaml`), plus a headless governing `Service` and a `START_DP_IP` `ConfigMap`. It also deploys a `rapid` controller pod (`controller.enabled`, default true) with a `rapid.env` auto-rendered from the StatefulSet's ordinal DNS names (`<release>-0`, `-1`, ... → `[M1]`, `[M2]`, ... matching the shipped `rapid/machine.map` defaults) — see `charts/prox/README.md`'s "How a test run actually works" for why no in-cluster discovery/RBAC is needed for this. Tests are triggered via `kubectl exec` into the controller (or automatically on install via `controller.runOnStart`); a network-triggerable HTTP API is an intentionally-deferred follow-up, not yet built. This chart is independent of, and serves a different purpose than, `rapid/rapid_helm_chart/` (a minimal, older scaffold that deploys just the `rapid` controller image with pod-management RBAC — no NAD, no dataplane pods). See `charts/prox/README.md` for the full values reference.

## Test scenario files (`rapid/tests/*.test`)

INI files with a `[TestParameters]` section (test name, `lat_percentile`, number of machines) and one `[TestMx]` section per machine (`config_file` pointing at a `rapid/configs/*.cfg`, `cores`/`gencores`/`latcores`/`mcore` CPU assignments, `dest_machine` for generators), followed by one or more `[testN]` sections defining the actual test type (`flowsizetest`, `TST009test`, `fixed_rate`, `increment_till_fail`, `corestatstest`, `portstatstest`, `impairtest`, `irqtest`, `warmuptest`) and its parameters (flow counts, packet size lists/imix, thresholds for drop rate / latency, ramp step, etc). See `rapid/tests/README` for the full field reference. `rapid/configs/*.cfg` are the PROX-side configs referenced by these tests; `src/config/` and `src/gen/` contain the much larger library of PROX example configs unrelated to the rapid test harness.

## Licensing note

Apache 2.0, with copyright headers combining "rapidPROX contributors" (2023+) and original "Intel Corporation" (2010-2020ish) attribution — keep both when editing files that already carry this dual header, and use the rapidPROX-only header for genuinely new files.
