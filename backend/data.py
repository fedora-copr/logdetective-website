"""
This is a temporary file with hardcoded build log and other data before we
implement an actual code for fetching logs from Copr/Koji/Packit/etc.
"""


LOG_OUTPUT="""INFO: chroot_scan: 3 files copied to /var/lib/copr-rpmbuild/results/chroot_scan
INFO: /var/lib/mock/fedora-37-x86_64-1692181166.067366/root/var/log/dnf.rpm.log
/var/lib/mock/fedora-37-x86_64-1692181166.067366/root/var/log/dnf.librepo.log
/var/lib/mock/fedora-37-x86_64-1692181166.067366/root/var/log/dnf.log
ERROR:
Exception(/var/lib/copr-rpmbuild/results/copr-rpmbuild-0.69-1.fc37.src.rpm)
Config(fedora-37-x86_64) 0 minutes 28 seconds
INFO: Results and/or logs in: /var/lib/copr-rpmbuild/results
INFO: Cleaning up build root ('cleanup_on_failure=True')
Start: clean chroot
INFO: unmounting tmpfs.
Finish: clean chroot
ERROR: Command failed:
# /usr/bin/systemd-nspawn -q -M
15916d5fd0524fe090a40cbc09f15279 -D
/var/lib/mock/fedora-37-x86_64-bootstrap-1692181166.067366/root
-a --capability=cap_ipc_lock --rlimit=RLIMIT_NOFILE=10240
--capability=cap_ipc_lock
--bind=/tmp/mock-resolv.0pyv_f8p:/etc/resolv.conf
/var/lib/mock/fedora-37-x86_64-1692181166.067366/root/
--releasever 37 --setopt=deltarpm=False
--setopt=allow_vendor_change=yes --allowerasing
--disableplugin=local --disableplugin=spacewalk
--disableplugin=versionlock
/var/lib/mock/fedora-37-x86_64-1692181166.067366/root//builddir/build/SRPMS/
copr-rpmbuild-0.69-1.fc37.src.rpm
--setopt=tsflags=nocontexts --setopt=tsflags=nocontexts
--setopt=tsflags=nocontexts
No matches found for the following disable plugin patterns: local, spacewalk, versionlock
Copr repository                                  55 kB/s | 1.8 kB     00:00
fedora                                          299 kB/s |  26 kB     00:00
updates                                         403 kB/s |  19 kB     00:00
No matching package to install: 'python3-specfile >= 0.21.0'
Not all dependencies satisfied
Error: Some packages could not be found.

Copr build error: Build failed
"""
