#!/usr/bin/env python3

import os
import subprocess
import time
import stat
import logging
import re
import uuid

def run_cmd(cmd, shell=True):
    """Run a shell command and return (returncode, stdout, stderr)."""
    result = subprocess.run(cmd, shell=shell, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def create_tun():
    """Create /dev/net/tun device if it does not exist."""
    try:
        os.makedirs("/dev/net", exist_ok=True)

        tun_path = "/dev/net/tun"

        if not os.path.exists(tun_path):
            # Create character device node (major 10, minor 200)
            mode = stat.S_IFCHR | 0o600
            os.mknod(tun_path, mode, os.makedev(10, 200))
        else:
            # Ensure correct permissions
            os.chmod(tun_path, 0o600)

    except PermissionError:
        print("Permission denied while creating /dev/net/tun (requires root)")
    except Exception as e:
        print(f"Error creating tun device: {e}")


def setup_ssh():
    """Ensure SSH runtime directory exists and start SSH service."""
    try:
        os.makedirs("/var/run/sshd", exist_ok=True)
    except Exception as e:
        print(f"Error creating /var/run/sshd: {e}")
        return

    rc, out, err = run_cmd("service ssh start")
    if rc != 0:
        print(f"Failed to start SSH service: {err}")


def setup_sudoers():
    """Add passwordless sudo access for 'rapid' user."""
    sudoers_line = "rapid ALL=(ALL) NOPASSWD:ALL\n"

    try:
        # Check if entry already exists to avoid duplicates
        with open("/etc/sudoers", "r") as f:
            if sudoers_line.strip() in f.read():
                return

        with open("/etc/sudoers", "a") as f:
            f.write(sudoers_line)

    except PermissionError:
        print("Permission denied while modifying /etc/sudoers (requires root)")
    except Exception as e:
        print(f"Error updating sudoers: {e}")

class Pod:
    """Class which represents test pods.
    For example with traffic gen, forward/swap applications, etc
    """
    def __init__(self, name):
        self._name = name
        self._log = logging.getLogger(__name__)
        self.allow_parameter = "allow"

    def expand_list_format(self, list):
        """Expand cpuset list format provided as comma-separated list of
        numbers and ranges of numbers. For more information please see
        https://man7.org/linux/man-pages/man7/cpuset.7.html
        """
        list_expanded = []
        for num in list.split(','):
            if '-' in num:
                num_range = num.split('-')
                list_expanded += range(int(num_range[0]), int(num_range[1]) + 1)
            else:
                list_expanded.append(int(num))
        return list_expanded

    def read_cpuset(self):
        """Read list of cpus on which we allowed to execute
        """
        cmd = "cat /proc/1/task/1/status | grep Cpus_allowed_list | awk '{print $2}'"
        cpuset_cpus = self._client.run_cmd(cmd).decode().rstrip()
        RapidLog.debug('{} ({}): Allocated cpuset: {}'.format(self.name, self.ip, cpuset_cpus))
        self.cpu_mapping = self.expand_list_format(cpuset_cpus)
        RapidLog.debug('{} ({}): Expanded cpuset: {}'.format(self.name, self.ip, self.cpu_mapping))

        # Log CPU core mapping for user information
        cpu_mapping_str = ''
        for i in range(len(self.cpu_mapping)):
            cpu_mapping_str = cpu_mapping_str + '[' + str(i) + '->' + str(self.cpu_mapping[i]) + '], '
        cpu_mapping_str = cpu_mapping_str[:-2]
        RapidLog.debug('{} ({}): CPU mapping: {}'.format(self.name, self.ip, cpu_mapping_str))

    def remap_cpus(self, cpus):
        """Convert relative cpu ids provided as function parameter to match
        cpu ids from allocated list
        """
        cpus_remapped = []
        for cpu in cpus:
            cpus_remapped.append(self.cpu_mapping[cpu])
        return cpus_remapped

    def remap_all_cpus(self):
        """Convert relative cpu ids for different parameters (mcore, cores)
        """
        if self.cpu_mapping is None:
            RapidLog.debug('{} ({}): cpu mapping is not defined! Please check the configuration!'.format(self.name, self.ip))
            return
        for key in self.machine_params.keys():
            if 'core' in key:
                cpus_remapped = self.remap_cpus(self.machine_params[key])
                RapidLog.debug('{} ({}): {} {} remapped to {}'.format(self.name, self.ip, key, self.machine_params[key], cpus_remapped))
                self.machine_params[key] = cpus_remapped
        return

    def extract_first_pci_address(self, text):
        # PCI-address pattern: 4 hex numbers : 2 hex numbers : 2 hex numbers . 1 number
        pattern = r'\b[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]\b'
        match = re.search(pattern, text)
        return match.group(0) if match else None

    def version_tuple(self, version):
        """Convert version string (e.g. '20.11.0') to a tuple of integers."""
        return tuple(int(part) for part in version.split('.') if part.isdigit())


    def get_sriov_dev_mac(self):
        """Get the SRIOV VF device assigned by the Kubernetes SRIOV network device plugin.

        The function reads the PCI device assignment from local environment variables,
        reads the local DPDK version from /opt/rapid/dpdk_version, runs the local
        port_info_app utility, and extracts the MAC address for the assigned VF.

        Return 0 in case of successful configuration.
        Otherwise return -1.
        """
        self._log.info("Checking assigned SRIOV VF for POD %s", self._name)

        # Read PCIDEVICE environment variables
        pci_envs = [f"{key}={value}" for key, value in os.environ.items() if "PCIDEVICE" in key]
        if not pci_envs:
            self._log.error("No PCIDEVICE environment variables found")
            return -1

        env_output = "\n".join(pci_envs)
        self._log.debug("Environment variable %s", env_output)

        # Extract first PCI address using existing helper
        self._sriov_vf = self.extract_first_pci_address(env_output)

        if self._sriov_vf is None:
            self._log.error("Failed to parse SRIOV VF PCI address from environment variables")
            return -1

        self._log.debug("Using first SRIOV VF %s", self._sriov_vf)

        # Read DPDK version
        self._log.info("Checking DPDK version for POD %s", self._name)
        try:
            with open("/opt/rapid/dpdk_version", "r", encoding="utf-8") as file_handle:
                dpdk_version = file_handle.read().strip()
        except Exception as exc:
            self._log.error("Failed to check DPDK version. Error %s", exc)
            return -1

        self._log.debug("DPDK version %s", dpdk_version)

        # Correct version comparison
        try:
            if self.version_tuple(dpdk_version) >= self.version_tuple("20.11.0"):
                self.allow_parameter = "allow"
            else:
                self.allow_parameter = "pci-whitelist"
        except Exception as exc:
            self._log.error("Failed to compare DPDK version %s: %s", dpdk_version, exc)
            return -1

        # Run port_info_app
        self._log.info("Getting MAC address for assigned SRIOV VF %s", self._sriov_vf)

        result = subprocess.run(
            [
                "/opt/rapid/port_info_app",
                "-n",
                "4",
                f"--{self.allow_parameter}",
                self._sriov_vf,
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            error_text = result.stderr.strip() or result.stdout.strip()
            self._log.error("Failed to get MAC address! Error %s", error_text)
            return -1

        cmd_output = result.stdout.strip()
        self._log.debug(cmd_output)

        # Parse MAC address
        self._sriov_vf_mac = None
        for line in cmd_output.splitlines():
            if line.startswith("Port 0 MAC: "):
                self._sriov_vf_mac = line[12:]
                break

        if self._sriov_vf_mac is None:
            self._log.error("Failed to parse MAC address from port_info_app output")
            return -1

        self._log.debug("MAC %s", self._sriov_vf_mac)
        return 0

    def generate_lua(self, appendix = ''):
        self.LuaFileName = 'parameters.lua'
        with open(self.LuaFileName, "w") as LuaFile:
            LuaFile.write('require "helper"\n')
            LuaFile.write('name="%s"\n'% self._name)
#           for index, dp_port in enumerate(self.dp_ports, start = 1):
#               LuaFile.write('local_ip{}="{}"\n'.format(index, dp_port['ip']))
#               LuaFile.write('local_hex_ip{}=convertIPToHex(local_ip{})\n'.format(index, index))
            eal_line = 'eal=\"--file-prefix {}{} --{} {} --force-max-simd-bitwidth=512\n'.format(
                        self._name, str(uuid.uuid4()), self.allow_parameter,
                        self._sriov_vf)
            LuaFile.write(eal_line)
            return 0
            for key in self.machine_params.keys():
                if 'core' in key:
                    cores = ','.join(map(str,self.machine_params[key]))
                    cores = (f'"{cores}"') 
                    LuaFile.write('{}={}\n'.format(key,cores))
            if 'ports' in self.machine_params.keys():
                LuaFile.write('ports="%s"\n'% ','.join(map(str,
                    self.machine_params['ports'])))
            if 'dest_ports' in self.machine_params.keys():
                for index, dest_port in enumerate(self.machine_params['dest_ports'], start = 1):
                    LuaFile.write('dest_ip{}="{}"\n'.format(index, dest_port['ip']))
                    LuaFile.write('dest_hex_ip{}=convertIPToHex(dest_ip{})\n'.format(index, index))
                    if dest_port['mac']:
                        LuaFile.write('dest_hex_mac{}="{}"\n'.format(index ,
                            dest_port['mac'].replace(':',' ')))
            if 'gw_vm' in self.machine_params.keys():
                for index, gw_ip in enumerate(self.machine_params['gw_ips'],
                        start = 1):
                    LuaFile.write('gw_ip{}="{}"\n'.format(index, gw_ip))
                    LuaFile.write('gw_hex_ip{}=convertIPToHex(gw_ip{})\n'.
                            format(index, index))
#            LuaFile.write(appendix)

    def expand_list_format(self, list):
        """Expand cpuset list format provided as comma-separated list of
        numbers and ranges of numbers. For more information please see
        https://man7.org/linux/man-pages/man7/cpuset.7.html
        """
        list_expanded = []
        for num in list.split(','):
            if '-' in num:
                num_range = num.split('-')
                list_expanded += range(int(num_range[0]), int(num_range[1]) + 1)
            else:
                list_expanded.append(int(num))
        return list_expanded

    def read_cpuset(self):
        """Read list of cpus on which we allowed to execute
        """
        cmd = "cat /proc/1/task/1/status | grep Cpus_allowed_list | awk '{print $2}'"
        cpuset_cpus = self._client.run_cmd(cmd).decode().rstrip()
        RapidLog.debug('{} ({}): Allocated cpuset: {}'.format(self.name, self.ip, cpuset_cpus))
        self.cpu_mapping = self.expand_list_format(cpuset_cpus)
        RapidLog.debug('{} ({}): Expanded cpuset: {}'.format(self.name, self.ip, self.cpu_mapping))

        # Log CPU core mapping for user information
        cpu_mapping_str = ''
        for i in range(len(self.cpu_mapping)):
            cpu_mapping_str = cpu_mapping_str + '[' + str(i) + '->' + str(self.cpu_mapping[i]) + '], '
        cpu_mapping_str = cpu_mapping_str[:-2]
        RapidLog.debug('{} ({}): CPU mapping: {}'.format(self.name, self.ip, cpu_mapping_str))

    def remap_cpus(self, cpus):
        """Convert relative cpu ids provided as function parameter to match
        cpu ids from allocated list
        """
        cpus_remapped = []
        for cpu in cpus:
            cpus_remapped.append(self.cpu_mapping[cpu])
        return cpus_remapped

    def remap_all_cpus(self):
        """Convert relative cpu ids for different parameters (mcore, cores)
        """
        if self.cpu_mapping is None:
            RapidLog.debug('{} ({}): cpu mapping is not defined! Please check the configuration!'.format(self.name, self.ip))
            return
        for key in self.machine_params.keys():
            if 'core' in key:
                cpus_remapped = self.remap_cpus(self.machine_params[key])
                RapidLog.debug('{} ({}): {} {} remapped to {}'.format(self.name, self.ip, key, self.machine_params[key], cpus_remapped))
                self.machine_params[key] = cpus_remapped
        return

def main():
    """Main entry point equivalent to the bash script."""

    # Create TUN device
    #create_tun()
    logging.basicConfig(level=logging.DEBUG)
    pod = Pod("rapid_pod")
    if pod.get_sriov_dev_mac() != 0:
        sys.exit(1)

    if pod.generate_lua() != 0:
        sys.exit(1)
    # Indicate system is ready
    try:
        open("/opt/rapid/system_ready_for_rapid", "a").close()
    except Exception as e:
        print(f"Error creating readiness file: {e}")

    # Setup SSH service
    #setup_ssh()

    # Configure sudoers
    #setup_sudoers()

    # Sleep indefinitely (equivalent to 'sleep infinity')
    #while True:
    #    time.sleep(3600)


if __name__ == "__main__":
    main()
