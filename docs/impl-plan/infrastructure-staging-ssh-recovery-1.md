---
goal: Restore reliable multi-user SSH access to akasha-staging and prevent recurrence
version: 1.0
date_created: 2026-06-23
last_updated: 2026-06-23
owner: Akasha Infrastructure
---

# Introduction

This plan restores SSH access to the Azure VM `akasha-staging` at `20.219.3.35`, identifies the failed guest/SSHD state after the LISS-4 ingestion workload, and implements durable access, storage, and observability controls so multiple team members can use the VM without repeated SSH banner failures.

Evidence gathered on 2026-06-23 from Azure CLI and local SSH:

- Local SSH alias `akasha-staging` resolves to `akashaadmin@20.219.3.35:22` with `IdentityFile ~/.ssh/id_ed25519_thaarei`.
- TCP connection to port 22 succeeds, but SSH times out before server banner: `Connection timed out during banner exchange`.
- VM `akasha-staging` is running in resource group `RG-AKASHA-SELFHOSTED`, location `centralindia`, private IP `10.10.2.4`, public IP `20.219.3.35`.
- Effective NSG allows SSH from `0.0.0.0/0` via rule `Allow-SSH-Temporary-Any` priority `1000`.
- Azure instance view reports `ProvisioningState/updating` and VM Agent `Not Ready` with message `VM Agent is unresponsive`.
- Extension `AADSSHLoginForLinux` is present and has no healthy status in instance view.
- VM OS profile has `disablePasswordAuthentication: true`.
- OS disk `osdisk-akasha-staging` is `Premium_LRS`, 30 GB, `120` IOPS, `25` MB/s.
- Data disk `datadisk-akasha-staging-001` is `Premium_LRS`, 512 GB, `2300` IOPS, `150` MB/s.
- Azure metrics show OS disk queue depth around `146` to `295` and OS disk read pressure around `252 MB/s`, which is consistent with an overloaded OS disk and can make SSHD accept TCP but fail to serve banners.
- Boot diagnostics were enabled on 2026-06-23 and produced a boot log after recovery.
- Repository notes in `docs/impl-plan/data-resourcesat-liss4-awifs-productionization-1.md` record that a broad LISS-4 sync was terminated and SSH banner timeout started immediately afterward.

Recovery execution notes from 2026-06-23:

- Created rollback snapshots `snap-akasha-staging-osdisk-20260623` and `snap-akasha-staging-datadisk-20260623` successfully.
- A normal restart request did not restore SSH or the VM Agent; Azure still reported VM Agent `Not Ready` and SSH still timed out during banner exchange.
- Azure VM redeploy completed successfully. The static public IP remained `20.219.3.35`; VM Agent returned to `Ready`; `AADSSHLoginForLinux` returned to `Provisioning succeeded`; SSH login succeeded.
- `/srv/akasha` is mounted on the 512 GB data disk `/dev/sdb`; Docker data-root is `/srv/akasha/runtime/docker`; `/data/coolify` is on the OS disk but only ~212 KB.
- Installed the restricted ingestion job wrappers under `/opt/akasha/bin`, fixed `akasha-ingesters` group permissions, and installed Ubuntu package `python-is-python3` so wrapper subcommands work on Ubuntu 24.04.
- Added `/etc/ssh/sshd_config.d/00-akasha-team.conf` to keep key-only auth, disable root login, and raise SSH concurrency limits.
- Final validation passed: local SSH smoke, 20 concurrent SSH sessions, Azure Run Command smoke, Azure VM Agent Ready, and `python scripts/staging_ingestion_job.py doctor --host akasha-staging`.

Recurrence notes from 2026-06-23 later incident:

- A direct/ad hoc `akasha-ingestion-worker` Docker container was observed running `python worker.py verify-composite --source resourcesat-2a-liss4-mx70-l2 ... --require-catalog-item` immediately after recovery. This command path bypassed the staging wrapper and coincided with renewed high read I/O and SSH banner timeouts.
- Azure again reported VM Agent `Not Ready` and provisioning `Updating`; SSH timed out during banner exchange; redeploy recovered the VM again without changing static IP `20.219.3.35`.
- The official wrapper path had three defects discovered during dry-run validation: request JSON stdin was consumed by a Python here-doc, `systemd-run` failed in non-interactive SSH with `Interactive authentication required`, and the installer used `2750` on the job root so `akasha-ingesters` could not write job state.
- Fixed wrapper artifacts in `infra/selfhosted/systemd/`: request stdin is spooled to a temp file, `systemd-run` falls back to `setsid`/`nohup`, job root install mode is `2770`, wrapper preflight no longer creates the same worker lock file that `worker.py` treats as authoritative, and worker commands are prefixed with `ionice -c 2 -n 7 nice -n 10`.
- Reinstalled the fixed wrappers on `akasha-staging`, added non-secret priority defaults to `/etc/akasha/ingestion-jobs.env`, cleared one stale queued job and one stale unheld worker lock, and verified a no-download dry-run job succeeded through `scripts/staging_ingestion_job.py`.
- Upgraded `akasha-staging` OS disk from 30 GiB Premium SSD to 256 GiB Premium SSD on 2026-06-23. Azure now reports `diskSizeGB=256`, `diskIOPSReadWrite=1100`, and `diskMBpsReadWrite=125`; Linux `/` auto-expanded to 247 GiB usable after restart.

## 1. Requirements & Constraints

- **REQ-001**: Restore SSH access to `akasha-staging` without changing the reserved public IP `20.219.3.35`.
- **REQ-002**: Preserve the VM role as the centralized Bhoonidhi/Bhuvan whitelisted staging runner.
- **REQ-003**: Allow multiple team members to connect concurrently without SSH banner failures.
- **REQ-004**: Keep long-running ingestion workloads bounded and recoverable through the existing staging job wrapper instead of ad hoc interactive shell sessions.
- **REQ-005**: Keep staging paths `/srv/akasha/data/raw/bhoonidhi`, `/srv/akasha/data/work/bhoonidhi`, `/srv/akasha/data/seed/rasters`, and `/srv/akasha/ingestion` on the large data disk.
- **SEC-001**: Do not distribute Bhoonidhi credentials to developer laptops.
- **SEC-002**: Do not keep SSH open to `0.0.0.0/0` after recovery.
- **SEC-003**: Prefer per-user SSH keys or Azure Entra ID SSH over shared passwords.
- **SEC-004**: If password login is temporarily enabled for development, it must be limited to per-user accounts, restricted source IP ranges, `PermitRootLogin no`, `MaxAuthTries 3`, and fail2ban or equivalent lockout.
- **CON-001**: Azure VM Run Command currently cannot be relied upon because VM Agent is unresponsive.
- **CON-002**: Restart, redeploy, deallocate, disk resize, and SSHD configuration changes require a maintenance window because staging services can be interrupted.
- **CON-003**: The public IP is static and must remain attached to the VM or replacement VM.
- **GUD-001**: Heavy Docker, Coolify, raw raster, work, and generated COG data must not run on the 30 GB OS disk.
- **GUD-002**: Interactive shell access should be limited to operators; developer ingestion access should use `scripts/staging_ingestion_job.py` and the forced-command wrapper.
- **PAT-001**: Follow the existing staging ingestion workflow documented in `docs/impl-plan/process-staging-ingestion-workflow-1.md` and `infra/selfhosted/README.md`.

## 2. Implementation Steps

### Implementation Phase 1 — Immediate recovery and evidence preservation

- GOAL-001: Recover SSH and guest-agent access without losing staging data or changing the static public IP.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Record current Azure state with `az vm get-instance-view -g RG-AKASHA-SELFHOSTED -n akasha-staging --query "{statuses:instanceView.statuses,vmAgent:instanceView.vmAgent.statuses,extensions:instanceView.extensions}" -o json`. Save output in the incident notes. | ✅ | 2026-06-23 |
| TASK-002 | Record SSH failure with `ssh -o BatchMode=yes -o NumberOfPasswordPrompts=0 -o ConnectTimeout=10 akasha-staging true`. Expected current result before recovery: `Connection timed out during banner exchange`. | ✅ | 2026-06-23 |
| TASK-003 | Record disk pressure with Azure metrics: `OS Disk Queue Depth`, `OS Disk Read Bytes/Sec`, `OS Disk Read Operations/Sec`, and `Percentage CPU` for the last 2 hours. Expected current result before recovery: queue depth above `100`. | ✅ | 2026-06-23 |
| TASK-004 | Verify boot diagnostics are enabled with `az vm show -g RG-AKASHA-SELFHOSTED -n akasha-staging --query 'diagnosticsProfile.bootDiagnostics' -o json`. Expected: `{ "enabled": true, "storageUri": null }`. | ✅ | 2026-06-23 |
| TASK-005 | Create crash-consistent snapshots before disruptive recovery: snapshot OS disk `osdisk-akasha-staging` and data disk `datadisk-akasha-staging-001` in `RG-AKASHA-SELFHOSTED` with names `snap-akasha-staging-osdisk-20260623` and `snap-akasha-staging-datadisk-20260623`. Completion: both snapshots show `provisioningState: Succeeded`. | ✅ | 2026-06-23 |
| TASK-006 | Restart the VM during an approved maintenance window with `az vm restart -g RG-AKASHA-SELFHOSTED -n akasha-staging`. Completion: command exits `0`, VM returns to `PowerState/running`, and public IP remains `20.219.3.35`. Attempted; restart did not restore SSH/VM Agent, so TASK-010 was required. | ⚠️ | 2026-06-23 |
| TASK-007 | After restart, fetch boot diagnostics with `az vm boot-diagnostics get-boot-log -g RG-AKASHA-SELFHOSTED -n akasha-staging`. Completion: command returns serial console text instead of `BlobNotFound`. | ✅ | 2026-06-23 |
| TASK-008 | After restart, verify VM Agent recovery with `az vm get-instance-view -g RG-AKASHA-SELFHOSTED -n akasha-staging --query 'instanceView.vmAgent.statuses' -o json`. Expected: status is not `ProvisioningState/Unavailable`; display status is `Ready`. | ✅ | 2026-06-23 |
| TASK-009 | After restart, verify SSH banner/auth path with `ssh -o BatchMode=yes -o ConnectTimeout=10 akasha-staging 'hostname && whoami && uptime'`. Expected: output includes `akasha-staging`, the remote user, and uptime. | ✅ | 2026-06-23 |
| TASK-010 | If TASK-006 through TASK-009 fail, redeploy the VM to a new Azure host with `az vm redeploy -g RG-AKASHA-SELFHOSTED -n akasha-staging`, then repeat TASK-007 through TASK-009. Completion: SSH works and VM Agent is ready. | ✅ | 2026-06-23 |
| TASK-011 | If restart and redeploy both fail, use Azure VM repair: create a repair VM, attach the OS disk, inspect `/var/log/auth.log`, `/var/log/syslog`, `/etc/ssh/sshd_config*`, `/var/lib/waagent`, disk mounts, and Docker data-root, then detach and reattach the repaired OS disk. Completion: root cause is recorded and SSH works after boot. | | |

### Implementation Phase 2 — Guest inspection after SSH returns

- GOAL-002: Identify the exact workload/process that saturated the OS disk and confirm all heavy paths are on the data disk.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-012 | Run `ssh akasha-staging 'systemctl is-active ssh || systemctl is-active sshd; systemctl status ssh --no-pager -l | sed -n "1,80p"'`. Completion: SSHD service is `active` and has no repeated fatal errors. | ✅ | 2026-06-23 |
| TASK-013 | Run `ssh akasha-staging 'journalctl -u ssh -u sshd --since "6 hours ago" --no-pager | tail -n 200'`. Completion: auth/service errors around the incident are captured in incident notes. | ✅ | 2026-06-23 |
| TASK-014 | Run `ssh akasha-staging 'systemctl status walinuxagent --no-pager -l | sed -n "1,80p"; journalctl -u walinuxagent --since "6 hours ago" --no-pager | tail -n 200'`. Completion: VM Agent status and errors are captured. | ✅ | 2026-06-23 |
| TASK-015 | Run `ssh akasha-staging 'findmnt /srv/akasha /data /var/lib/docker 2>/dev/null || true; df -h / /srv/akasha /data /var/lib/docker 2>/dev/null || df -h'`. Completion: `/srv/akasha` is confirmed on the 512 GB data disk; any heavy path on `/` is listed as a defect. | ✅ | 2026-06-23 |
| TASK-016 | Run `ssh akasha-staging 'docker info --format "DockerRootDir={{.DockerRootDir}}"; docker system df'`. Completion: Docker root is captured; Docker root on the OS disk is listed as a defect. | ✅ | 2026-06-23 |
| TASK-017 | Run `ssh akasha-staging 'ps -eo pid,ppid,stat,ni,pri,pcpu,pmem,args --sort=-pcpu | head -n 40; sudo iotop -b -n 3 -o 2>/dev/null || true'`. Completion: any runaway GDAL/rasterio/worker/Docker process is identified or confirmed absent after restart. | ✅ | 2026-06-23 |
| TASK-018 | Stop or clean failed ingestion jobs using existing wrappers, not manual deletion: run `python scripts/staging_ingestion_job.py status <job_id> --host akasha-staging` for known active jobs, then `python scripts/staging_ingestion_job.py retry <job_id> --host akasha-staging --dry-run` only after the system is healthy. Completion: no abandoned broad sync is consuming disk I/O. | ✅ | 2026-06-23 |

### Implementation Phase 3 — Permanent storage and workload fix

- GOAL-003: Prevent ingestion and Docker workloads from saturating the OS disk again.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-019 | Resize the OS disk from 30 GB to at least 128 GB Premium SSD during maintenance. Use Azure disk update on `osdisk-akasha-staging`, then grow the Linux partition and filesystem from the guest. Completion: `df -h /` shows at least `100G` available filesystem size and Azure disk shows at least `500` provisioned IOPS. Completed with 256 GiB OS disk, 1100 IOPS, 125 MB/s, and `/` showing 247 GiB usable. | ✅ | 2026-06-23 |
| TASK-020 | Ensure the 512 GB data disk is mounted persistently in `/etc/fstab` using UUID and mounted at the canonical data mount that backs `/srv/akasha`. Completion: `findmnt /srv/akasha` shows the 512 GB disk and survives reboot. | ✅ | 2026-06-23 |
| TASK-021 | Move Docker data-root to the data disk if TASK-016 shows Docker root on `/`. Configure `/etc/docker/daemon.json` with `{"data-root":"/srv/docker"}`, stop Docker/Coolify, rsync existing data, restart Docker, and verify `docker info --format '{{.DockerRootDir}}'` returns `/srv/docker`. Docker root was already `/srv/akasha/runtime/docker`, so no move was required. | ✅ | 2026-06-23 |
| TASK-022 | Ensure Coolify service data lives on the data disk. If `/data/coolify` is on `/`, move it to `/srv/akasha/coolify` or another data-disk path and bind mount `/data/coolify` through `/etc/fstab`. Completion: `findmnt /data/coolify` shows the data disk. Deferred because `/data/coolify` is only ~212 KB and Docker/data roots are already on `/srv/akasha`. | ⚠️ | 2026-06-23 |
| TASK-023 | Enforce ingestion bounded execution: use `scripts/staging_ingestion_job.py trigger` instead of direct interactive `worker.py bhoonidhi-sync` runs; require `--max-downloads` and specific date windows for manual runs. Completion: team runbook no longer instructs direct broad sync execution. Wrapper path is fixed and verified; remaining policy action is to stop granting broad Docker access to non-operator users. | ⚠️ | 2026-06-23 |
| TASK-024 | Add or verify `ionice`/`nice` in the staging ingestion systemd wrapper for GDAL/raster-heavy jobs: use `ionice -c2 -n7 nice -n 10` for non-urgent ingestion. Completion: systemd wrapper or service execution path shows bounded priority. | ✅ | 2026-06-23 |
| TASK-025 | Validate post-fix disk pressure by running a capped dry run and a capped real ingestion job. Completion: `OS Disk Queue Depth` remains below `10` during the job and data disk handles the workload. No-download dry-run succeeded with low I/O pressure; capped real LISS-4 verification remains deferred until larger disk/VM guardrails are approved. | ⚠️ | 2026-06-23 |

### Implementation Phase 4 — Permanent team SSH access model

- GOAL-004: Allow concurrent team access without shared credentials or SSHD pre-auth drops.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-026 | Replace shared `akashaadmin` daily use with individual Linux users named after each team member, or use Azure Entra ID SSH login after the `AADSSHLoginForLinux` extension is healthy. Completion: each team member has a unique login identity. | | |
| TASK-027 | For ingestion-only developers, use the existing forced-command model: add each approved public key to the developer account `authorized_keys` with `command="/opt/akasha/bin/akasha-ingestion-forced-command.sh",restrict ssh-ed25519 <public-key> <developer>`. Completion: developer keys can run only allowed job subcommands and cannot open arbitrary shells. | | |
| TASK-028 | For operators who need an interactive shell, add them to a dedicated group such as `akasha-ops`; grant sudo only to named operators. Completion: `getent group akasha-ops` lists only approved operators. | | |
| TASK-029 | Create `/etc/ssh/sshd_config.d/99-akasha-team.conf` with `PubkeyAuthentication yes`, `PermitRootLogin no`, `MaxStartups 50:30:200`, `MaxSessions 50`, `LoginGraceTime 30`, `ClientAliveInterval 60`, `ClientAliveCountMax 3`, `AllowGroups akasha-ops akasha-ingesters`, and `PasswordAuthentication no` for the default secure path. Validate with `sshd -t` before reload. Implemented as `/etc/ssh/sshd_config.d/00-akasha-team.conf` without `AllowGroups` to avoid locking out existing users; OpenSSH keeps first-read values, so `00-` precedence is required on this VM. | ✅ | 2026-06-23 |
| TASK-030 | If temporary password login is required during development, change only `PasswordAuthentication yes` after NSG source restriction and fail2ban are active. Use per-user passwords entered directly on the VM with `sudo passwd <linux-user>`; do not store passwords in chat, docs, shell history, or repository files. Completion: password auth works only from approved IP ranges and root login remains disabled. | | |
| TASK-031 | Replace NSG rule `Allow-SSH-Temporary-Any` with an SSH rule limited to team office/VPN/static IP CIDRs or Azure Bastion. Completion: no effective inbound SSH allow rule has source `0.0.0.0/0`. | | |
| TASK-032 | Validate concurrent SSH with 20 simultaneous lightweight sessions from an approved network: `seq 1 20 | xargs -n1 -P20 -I{} ssh -o BatchMode=yes -o ConnectTimeout=10 akasha-staging 'echo ok-{}'`. Completion: all 20 sessions return `ok-N` without banner timeouts. | ✅ | 2026-06-23 |

### Implementation Phase 5 — Observability and rollback readiness

- GOAL-005: Detect and recover future SSH/VM-agent degradation before the team is locked out.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-033 | Keep boot diagnostics enabled and verify boot log after each restart with `az vm boot-diagnostics get-boot-log`. Completion: boot log retrieval returns serial console text. | ✅ | 2026-06-23 |
| TASK-034 | Create Azure Monitor alerts for `VM Agent Not Ready`, `OS Disk Queue Depth > 10 for 15 minutes`, `OS Disk Read/Write Bytes/Sec near provisioned limit for 15 minutes`, and `Percentage CPU > 85% for 15 minutes`. Completion: alerts exist in Azure and notify the team channel/email. | | |
| TASK-035 | Add a weekly validation run from a trusted workstation: SSH health check, `python scripts/staging_ingestion_job.py doctor --host akasha-staging`, and Azure metric spot check. Completion: weekly result is recorded in `test_reports/` or an operations tracker. | | |
| TASK-036 | Document the final access procedure in `infra/selfhosted/README.md` and `docs/staging-ingestion-developer-guide.md`: per-user SSH setup, no shared passwords, forced-command developer workflow, emergency Azure recovery steps, and concurrency limits. Completion: docs match the actual VM configuration. | | |

## 3. Alternatives

- **ALT-001**: Open SSH to the whole internet and enable one shared username/password. Rejected because it increases brute-force risk and does not solve OS disk saturation or guest-agent failure.
- **ALT-002**: Use Azure VM Run Command as the primary team workflow. Rejected because it depends on the VM Agent, which is currently unresponsive, and it is not suitable for streamable long-running ingestion jobs.
- **ALT-003**: Give every developer an unrestricted interactive shell. Rejected for routine ingestion work because the repo already defines a least-privilege forced-command workflow and shared locks.
- **ALT-004**: Only increase `MaxStartups`/`MaxSessions` in SSHD. Rejected as insufficient because the current root cause evidence points to VM/OS disk/agent saturation before SSHD can send a banner.
- **ALT-005**: Replace the VM immediately. Rejected as the first step because the static egress IP, data disk, Coolify state, and Bhoonidhi allow-list must be preserved; replacement remains a fallback if repair fails.

## 4. Dependencies

- **DEP-001**: Azure CLI authenticated to subscription `GIS Azure Subscription`.
- **DEP-002**: Azure permissions to snapshot disks, restart/redeploy VM, update NSG rules, update disks, and manage boot diagnostics.
- **DEP-003**: Maintenance window approval for restart/redeploy/disk resize/Docker data migration.
- **DEP-004**: Existing static public IP `20.219.3.35` must remain reserved and attached.
- **DEP-005**: Team member public SSH keys or Entra ID identities must be collected before permanent onboarding.
- **DEP-006**: If password login is temporarily enabled, approved source IP CIDRs must be known before NSG restriction is changed.
- **DEP-007**: Existing scripts `scripts/staging_ingestion_job.py` and `infra/selfhosted/systemd/akasha-ingestion-forced-command.sh` must remain the developer ingestion access path.

## 5. Files

- **FILE-001**: `docs/impl-plan/infrastructure-staging-ssh-recovery-1.md` — this recovery and permanent-remediation plan.
- **FILE-002**: `infra/selfhosted/README.md` — update after implementation with final SSH/team access and recovery runbook.
- **FILE-003**: `docs/staging-ingestion-developer-guide.md` — update after implementation with final developer onboarding and forced-command usage.
- **FILE-004**: `/etc/ssh/sshd_config.d/99-akasha-team.conf` on `akasha-staging` — new SSHD team access limits.
- **FILE-005**: `/etc/docker/daemon.json` on `akasha-staging` — update only if Docker data-root is currently on OS disk.
- **FILE-006**: `/etc/fstab` on `akasha-staging` — update only if `/srv/akasha`, `/data/coolify`, or Docker data-root require data-disk bind mounts.

## 6. Testing

- **TEST-001**: Local SSH banner/auth test returns success: `ssh -o BatchMode=yes -o ConnectTimeout=10 akasha-staging 'hostname && whoami && uptime'`.
- **TEST-002**: Azure VM Agent test returns ready: `az vm get-instance-view -g RG-AKASHA-SELFHOSTED -n akasha-staging --query 'instanceView.vmAgent.statuses' -o json`.
- **TEST-003**: Azure Run Command smoke test returns success after agent recovery: `az vm run-command invoke -g RG-AKASHA-SELFHOSTED -n akasha-staging --command-id RunShellScript --scripts 'hostname; systemctl is-active ssh || systemctl is-active sshd'`.
- **TEST-004**: Disk mount test confirms heavy paths are on data disk: `findmnt /srv/akasha /data/coolify /srv/docker`.
- **TEST-005**: Concurrent SSH test completes 20 sessions without banner timeout: `seq 1 20 | xargs -n1 -P20 -I{} ssh -o BatchMode=yes -o ConnectTimeout=10 akasha-staging 'echo ok-{}'`.
- **TEST-006**: Staging job doctor passes: `python scripts/staging_ingestion_job.py doctor --host akasha-staging`.
- **TEST-007**: Capped ingestion validation keeps OS disk queue depth below `10` and returns a classified terminal state.
- **TEST-008**: Effective NSG validation shows SSH source is not `0.0.0.0/0`.

## 7. Risks & Assumptions

- **RISK-001**: Restarting the VM interrupts staging web/API/Coolify services.
- **RISK-002**: A stuck disk-intensive process may restart automatically after reboot if it is managed by systemd/Coolify; Phase 2 must identify and disable or bound it.
- **RISK-003**: Moving Docker/Coolify data paths incorrectly can break the running stack; snapshots and maintenance window are mandatory before migration.
- **RISK-004**: Password authentication, if enabled without NSG restriction, exposes the VM to internet brute-force attempts.
- **RISK-005**: The `AADSSHLoginForLinux` extension may remain stuck after restart and require extension repair or removal/reinstall.
- **ASSUMPTION-001**: The 512 GB data disk contains or is intended to contain `/srv/akasha` staging data.
- **ASSUMPTION-002**: The static public IP `20.219.3.35` is required for Bhoonidhi/Bhuvan allow-listing and must not change.
- **ASSUMPTION-003**: Team members can provide SSH public keys or Entra ID identities.
- **ASSUMPTION-004**: Staging workloads can tolerate a planned restart/redeploy maintenance window.

## 8. Related Specifications / Further Reading

- `docs/impl-plan/data-resourcesat-liss4-awifs-productionization-1.md`
- `docs/impl-plan/process-staging-ingestion-workflow-1.md`
- `infra/selfhosted/README.md`
- `docs/staging-ingestion-developer-guide.md`
- Azure documentation: VM boot diagnostics, VM repair, Linux VM disk resize, Azure Bastion, Azure Monitor metric alerts
