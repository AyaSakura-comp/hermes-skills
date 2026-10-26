#!/bin/sh
# Enable/disable the AMD XDNA NPU on Strix Halo by switching the saved GRUB entry.
#   enable  -> npu-mode : IOMMU on, amdxdna probes, /dev/accel/accel0 (GPU ~5% slower)
#   disable -> gpu-max  : amd_iommu=off, max GPU, NPU unusable
# usage: npu-toggle.sh {enable|disable|status} [--once] [--reboot]
set -e
GRUBD=/etc/grub.d/41_boot_modes
CFG=/boot/grub/grub.cfg

status() {
  echo "saved GRUB entry : $(sudo -n grub-editenv list | grep -E 'saved_entry|next_entry' | tr '\n' ' ')"
  if grep -q 'amd_iommu=off' /proc/cmdline; then echo "running kernel   : gpu-max (amd_iommu=off, NPU disabled)"
  else echo "running kernel   : npu-mode (IOMMU on)"; fi
  if [ -e /dev/accel/accel0 ]; then echo "NPU device       : /dev/accel/accel0 present (enabled)"
  else echo "NPU device       : absent (disabled or amdxdna failed)"; fi
}

check_setup() {
  sudo -n test -x "$GRUBD" || { echo "ERROR: $GRUBD missing - boot-mode entries not installed" >&2; exit 2; }
  grep -q '^GRUB_DEFAULT=saved' /etc/default/grub || { echo "ERROR: /etc/default/grub needs GRUB_DEFAULT=saved" >&2; exit 2; }
  if ! sudo -n grep -q -- "--id $1" "$CFG"; then
    echo "entry $1 missing from grub.cfg -> running update-grub"
    sudo -n update-grub >/dev/null 2>&1
    sudo -n grep -q -- "--id $1" "$CFG" || { echo "ERROR: $1 still missing after update-grub" >&2; exit 2; }
  fi
}

mode=${1:-status}; [ $# -gt 0 ] && shift
once=0; rb=0
for a in "$@"; do case $a in --once) once=1;; --reboot) rb=1;; *) echo "unknown flag $a" >&2; exit 1;; esac; done
case $mode in
  enable|on|npu)    id=npu-mode ;;
  disable|off|gpu)  id=gpu-max ;;
  status)           status; exit 0 ;;
  *) echo "usage: $0 {enable|disable|status} [--once] [--reboot]" >&2; exit 1 ;;
esac

check_setup $id
if [ $once = 1 ]; then sudo -n grub-reboot $id; echo "next boot only -> $id"
else sudo -n grub-set-default $id; echo "default boot -> $id"; fi
status
if [ $rb = 1 ]; then echo "rebooting in 1 minute (cancel: sudo shutdown -c)"; sudo -n shutdown -r +1 "npu-toggle: switching to $id"
else echo "takes effect on next reboot"; fi
