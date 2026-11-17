# TBS pilot on compute-01

Prepared for Rabolab2 / VM 101. These are operator instructions; the remote VM
has not been resized or started by this document.

## Experiment to run

Use the existing `scripts/tbs_receptiveness_sweep.py`, with
`docs/simulation/observed-tbs-receptiveness.json`. This is a fresh Linux run of
the current matched synthetic TBS experiment:

| Factor | Setting |
| --- | --- |
| Actors | 16 development actors; four per original profile group |
| Repetitions | Three per actor |
| Receptiveness | 0.25, 0.50, 0.75 |
| Conditions | A unassisted; C generic direct; E personalised direct; D generic Socratic; F personalised Socratic |
| Protocol | Full TBS: 192 trials, 24 blocks, per calibration/comparison |
| Work | 144 jobs; each includes one calibration and all five conditions |
| Primary outcome | Targets attained / 24; paired changes in percentage points |
| Secondary outcome | Multiplied block score, kept in separate units |

All 720 comparison sessions and 144 calibrations are fresh. Repetitions are
averaged within actors; they do not create additional participants. The runner
reconstructs 48 independent unassisted trajectories, checks every new A, checks
calibration equality across levels, and numerically replays all comparison
trials. Full completion should have 144 baseline checks and 96 cross-level
calibration checks.

Language is offline/bounded; no LLM account, API key or model server is needed.
This tests the specified synthetic actors and structured assistance mechanisms.
The provisional TBS actor and unavailable historical offers limit conclusions
about human effects. This is not a natural-language generation evaluation.

## 1. Allocate CPUs and memory

Current VM: 16 vCPUs and 32 GiB RAM, so at most 16 workers with its current CPU
allocation. The original physical-host snapshot shows 64 logical CPUs and about
189 GiB RAM. If those resources are still available, use 64 vCPUs and 128 GiB RAM
for the largest CPU allocation. Keep host resources available for Proxmox, NAT,
WireGuard and storage. A 64-worker launch is a ceiling to test, not a measured
fastest or memory-safe setting; logical CPUs do not imply linear scaling.

First, in the Ubuntu SSH session, stop any jobs and shut down the guest:

```bash
sudo poweroff
```

Then in **Rabolab2 -> Shell**, confirm VM 101 is stopped and resize it:

```bash
qm status 101
qm set 101 --sockets 2 --cores 32 --numa 1 --memory 131072 --balloon 0
qm start 101
```

Do this while stopped; hot-changing virtual topology is unnecessary here.
WireGuard runs on the host and remains available during the guest shutdown.
Proxmox's CPU and memory options are documented at
https://github.com/proxmox/pve-docs/blob/master/generated/qm.1-synopsis.adoc.

Reconnect from the Mac with WireGuard active:

```bash
ssh mlnores@10.42.0.11
nproc
free -h
df -h /
```

Expect 64 CPUs after resizing. The existing 200 GiB virtual disk can be retained
initially; confirm the earlier root-filesystem expansion and monitor trace size.
If `/` still shows about 97 GiB and `sudo vgs` shows 99 GiB free, expand it:

```bash
sudo lvextend --resizefs -l +100%FREE /dev/ubuntu-vg/ubuntu-lv
df -h /
```

The filesystem should then show about 194 GiB. This consumes space already
available inside the VM; it does not change the Proxmox virtual disk.

The previous 144-job MAB runs occupy tens of GB each; TBS disk use has not been
measured for a complete run. Leave substantial free space and extend storage
before it fills. CPU resizing does not expand the disk.

## 2. Transfer the supplied snapshot

The supplied `tbs-vm-bundle.tar.gz` contains the current working-tree runtime,
two pilot scripts, three relevant test modules, the two TBS configuration files,
and the 16-actor development export. It excludes the Mac virtual environment,
Git internals, original spreadsheets, other cohorts and historical pilot outputs.
The local source data tree is about 154 GB and must not be copied wholesale.

In **Mac Terminal**:

```bash
cd "/Users/martinlopeznores/Desktop/Irena Danilovska"
scp deployment/tbs-vm/tbs-vm-bundle.tar.gz deployment/tbs-vm/tbs-vm-bundle.tar.gz.sha256 mlnores@10.42.0.11:~/
```

In the **Ubuntu SSH session**:

```bash
cd ~
sha256sum -c tbs-vm-bundle.tar.gz.sha256
```

Use a fresh `~/tbs-pilot` directory. Do not extract over an existing experiment:

```bash
test ! -e "$HOME/tbs-pilot" && tar -xzf tbs-vm-bundle.tar.gz
cd ~/tbs-pilot
sha256sum -c SHA256SUMS
```

All checksum checks must pass. This snapshot includes uncommitted/untracked
current implementation files, so a plain Git clone would not necessarily contain
the same experiment.

## 3. Build and validate the Linux environment

Run inside `~/tbs-pilot`, as `mlnores`:

```bash
sudo apt update
sudo apt install -y python3-venv tmux htop
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-vm.txt
.venv/bin/python -m pip check
.venv/bin/python -m pip freeze > environment-linux.freeze.txt
```

`requirements-vm.txt` pins the five libraries recorded by the existing pilot
fingerprint to the locally inspected versions. Linux's Python patch version and
resolved transitive packages can differ from the Mac. The new Linux manifests
record the Linux runtime; `environment-linux.freeze.txt` records all installed
packages. Do not transplant the Mac's existing output manifests or resume its
SQLite attempts on Linux.

Set offline mode and one numerical-library thread per process before tests:

```bash
export SOCRATIC_LLM=offline SOCRATIC_LANGUAGE_MODE=bounded SOCRATIC_INTERPRET_RESPONSES=0
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1
set -o pipefail
PYTHONPATH=.:scripts:tests .venv/bin/python -m unittest test_tbs_receptiveness_sweep test_observed_personalisation test_reconsideration -v 2>&1 | tee preflight.log
```

Require 36 passing tests and no dependency/checksum failures before proceeding.
The coordinator also sets offline mode and these thread limits before importing
the simulation package, including in each worker.

## 4. Freeze a fresh pilot

```bash
cd ~/tbs-pilot
TBS_OUT="$PWD/runs/tbs-vm-$(date -u +%Y%m%dT%H%M%SZ)"
PYTHONPATH=. .venv/bin/python scripts/tbs_receptiveness_sweep.py \
  --config docs/simulation/observed-tbs-receptiveness.json \
  --output-dir "$TBS_OUT" \
  --workers "$(nproc)" --prepare-only && printf '%s\n' "$TBS_OUT" > .tbs-output
```

This validates and freezes the grid and reconstructs independent controls; it
does not execute the comparison jobs. Check that the command succeeds. Every new
scientific configuration or software version needs a fresh output directory.

## 5. Run inside tmux

```bash
tmux new -s tbs-pilot
```

Inside that tmux session:

```bash
cd ~/tbs-pilot
TBS_OUT="$(cat .tbs-output)"
TBS_WORKERS="$(nproc)"
set -o pipefail
PYTHONPATH=. .venv/bin/python -u scripts/tbs_receptiveness_sweep.py \
  --output-dir "$TBS_OUT" --workers "$TBS_WORKERS" \
  2>&1 | tee -a "$TBS_OUT/sweep.log"
```

This requests all guest CPUs: 64 workers after the resize, or 16 without it.
There are 144 queued jobs, not 144 simultaneous workers. Jobs have separate
SQLite databases and immutable attempt directories. Only one coordinator writes
shared status/analysis. Do not launch one runner per condition or level.

The largest useful count depends on measured full-job memory and throughput.
Monitor the first batch closely; if RAM pressure, sustained swapping or host CPU
contention appears, stop gracefully and resume with 32 or 48 workers. Compare
completed jobs/hour, not just CPU utilisation. The runner records completed-job
peak RSS in `max_rss_bytes`. No reliable Xeon ETA is available before jobs finish;
the Mac's planning allowance is not a server benchmark.

Detach with Ctrl+B, then D. Reattach after another SSH login with:

```bash
tmux attach -t tbs-pilot
```

Linux does not need macOS's `caffeinate`. tmux survives SSH/VPN disconnections,
but not a VM reboot. Finish software updates/reboots before the pilot and do not
alter the runtime, dependencies, coordinator or scheduler while it runs.

## 6. Monitor

In another Ubuntu SSH session:

```bash
cd ~/tbs-pilot
TBS_OUT="$(cat .tbs-output)"
tail -f "$TBS_OUT/sweep.log"
```

Ctrl+C exits `tail` without stopping the runner. Other useful commands:

```bash
cat "$TBS_OUT/status.json"
free -h
df -h "$TBS_OUT"
du -sh "$TBS_OUT"
htop
```

Status includes completed jobs, active jobs, failures, control checks and an ETA
once jobs commit. Results update in `analysis.json` and `analysis.md`. A labelled
first-repetition preview is separate from the complete three-repetition analysis.

On completion, require `status: complete`, `completed_jobs: 144`,
`total_jobs: 144`, `control_checks_passed: true`, no failures, and
`analysis.json` reporting `complete: true` with 16 matched actors. Expected control
counts are 144 baseline checks, 96 calibration checks and 48 independent baselines.

## 7. Stop or change worker count

Request a graceful stop from another Ubuntu SSH session:

```bash
cd ~/tbs-pilot
TBS_OUT="$(cat .tbs-output)"
printf '{}\n' > "$TBS_OUT/stop-after-jobs.json"
```

The runner finishes in-flight jobs before exiting; that may take a while. Wait
until the runner exits and all workers have finished before resuming. Do not
delete lock files or run a second coordinator concurrently.

Resume inside tmux, choosing the desired count within the guest CPU limit:

```bash
cd ~/tbs-pilot
TBS_OUT="$(cat .tbs-output)"
rm -f "$TBS_OUT/stop-after-jobs.json"
TBS_WORKERS=32
set -o pipefail
PYTHONPATH=. .venv/bin/python -u scripts/tbs_receptiveness_sweep.py \
  --output-dir "$TBS_OUT" --workers "$TBS_WORKERS" \
  2>&1 | tee -a "$TBS_OUT/sweep.log"
```

Use 64 instead of 32 to return to the CPU ceiling after establishing sufficient
memory headroom. Verified completed jobs are retained; missing jobs receive new
numbered attempts. After a failure, inspect `status.json` and the indicated
attempt's `worker.log` before resuming. Do not modify frozen code to bypass an
error. Interrupted attempts can add disk usage.

## 8. Retrieve results

In Mac Terminal, retrieve the analysis from the dated directory shown in
`.tbs-output`; replace `RUN_DIRECTORY` below with that directory's basename:

```bash
mkdir -p "$HOME/Desktop/tbs-vm-results"
scp mlnores@10.42.0.11:~/tbs-pilot/runs/RUN_DIRECTORY/analysis.json "$HOME/Desktop/tbs-vm-results/"
scp mlnores@10.42.0.11:~/tbs-pilot/runs/RUN_DIRECTORY/analysis.md "$HOME/Desktop/tbs-vm-results/"
```

Keep the complete remote run, manifests, participant snapshot, logs, per-attempt
databases and Linux environment freeze for provenance. The analysis files alone
are summaries, not a full experiment backup. Keep this Linux experiment separate
from earlier Mac pilots; changing worker count within this run is supported.
