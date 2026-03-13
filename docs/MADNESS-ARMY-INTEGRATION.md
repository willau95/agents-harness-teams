# Madness Army Fleet Integration

Run `agents-harness-teams` tasks distributed across multiple machines in your Madness Army fleet.

---

## What Is Madness Army?

Madness Army is a fleet of machines (Mac, Linux, Raspberry Pi) each running a relay daemon
that exposes a local HTTP API for receiving and executing agent tasks.

The relay daemon runs on **port 59000** (Express.js) and provides:
- `POST /blueprint/dispatch` — Receive a task + context, spawn a Claude Code worker
- `GET  /blueprint/status/{task_id}` — Check worker status
- `GET  /system/stats` — Get machine load (CPU, memory, active tasks)
- `GET  /health` — Health check

---

## Prerequisites

### On each remote machine

1. **Install the relay daemon:**
   ```bash
   git clone https://github.com/your-org/madness-army-relay
   cd madness-army-relay
   npm install
   npm start
   # Relay now listening on port 59000
   ```

2. **Install Claude Code:**
   ```bash
   npm install -g @anthropic-ai/claude-code
   claude --version  # Verify installation
   ```

3. **Set ANTHROPIC_API_KEY:**
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   # Or add to ~/.zshrc / ~/.bashrc
   ```

4. **Install agents-harness-teams:**
   ```bash
   pip install agents-harness-teams
   ```

---

## Discover Your Fleet's IPs

### On your local network (LAN)

```bash
# macOS / Linux — scan subnet
nmap -sn 192.168.1.0/24 | grep -E "Nmap scan|report"

# Or use arp-scan
arp-scan --localnet

# Test each machine's relay health
curl http://192.168.1.2:59000/health
curl http://192.168.1.3:59000/health
```

### Verify a machine is relay-ready

```bash
curl http://192.168.1.2:59000/system/stats
# Expected response:
# {"active_tasks": 0, "max_concurrent_tasks": 4, "cpu_percent": 12.3, "memory_percent": 45.1}
```

---

## Usage

### Single machine (default)

```bash
harness run
```

Uses `claude` CLI on the local machine. No fleet setup needed.

---

### Madness Army fleet

```bash
harness run --fleet "192.168.1.2:59000,192.168.1.3:59000,192.168.1.4:59000"
```

**What happens:**
1. Harness completes Steps 1-7 (logic check + human approval) on local machine
2. For Step 8 (development), harness queries each relay's `/system/stats`
3. Tasks are dispatched to the least-loaded available machine
4. Each machine spawns a Claude Code worker for its assigned task
5. Harness polls `/blueprint/status/{task_id}` to track progress
6. Step 9 (validation + report) runs on local machine

---

### With master document

```bash
harness run \
  --fleet "192.168.1.2:59000,192.168.1.3:59000" \
  --master-doc ARCHITECTURE.md
```

---

## How Task Distribution Works

```
Harness (local machine)
  │
  ├── Step 1-7: Run locally (recall, logic check, human approval)
  │
  └── Step 8: Dispatch to fleet
       │
       ├── Query fleet health: GET /health (all machines in parallel)
       ├── Get stats: GET /system/stats
       ├── Sort by active_tasks (least loaded first)
       │
       ├── Task 1.1 → POST 192.168.1.2:59000/blueprint/dispatch
       ├── Task 1.2 → POST 192.168.1.3:59000/blueprint/dispatch (after 1.1 done)
       └── Task 1.3 → POST 192.168.1.4:59000/blueprint/dispatch (parallel with 1.2)
```

Dependencies are respected: task 1.2 won't dispatch until 1.1 is `done`.

---

## Monitoring the Fleet

### Check fleet status

```python
from harness.integrations.madness_army import MadnessArmyRelay

relay = MadnessArmyRelay([
    "http://192.168.1.2:59000",
    "http://192.168.1.3:59000",
])

import asyncio
statuses = asyncio.run(relay.get_fleet_status())
print(relay.format_fleet_table(statuses))
```

Output:
```
Fleet Status:
────────────────────────────────────────────────────────────────────
URL                                 Online   Tasks    CPU%     Avail
────────────────────────────────────────────────────────────────────
http://192.168.1.2:59000            ✓        1        23.4     yes
http://192.168.1.3:59000            ✓        0        8.1      yes
http://192.168.1.4:59000            ✗        0        0.0      no
────────────────────────────────────────────────────────────────────
```

### Check individual task status

```bash
curl http://192.168.1.2:59000/blueprint/status/task_1_1
# {"task_id": "task_1_1", "status": "running", "progress": "60%"}
```

### Monitor via harness status

```bash
harness status
# Shows all tasks with their machine assignment and duration
```

---

## Adding New Machines

1. Set up the machine (install relay + Claude Code + API key)
2. Add its IP to your `--fleet` parameter:
   ```bash
   harness run --fleet "192.168.1.2:59000,192.168.1.3:59000,192.168.1.5:59000"
   ```

No configuration files to update — fleet is defined at runtime via CLI.

---

## Troubleshooting

**Machine shows offline:**
```bash
# Check relay is running
ssh user@192.168.1.2 "ps aux | grep node"

# Restart relay
ssh user@192.168.1.2 "cd ~/madness-army-relay && npm start"

# Check firewall
ssh user@192.168.1.2 "sudo ufw allow 59000"
```

**Task stuck on remote machine:**
```bash
# Check worker logs on remote machine
ssh user@192.168.1.2 "cat ~/project/.harness/workers/task_1_1/stdout.log"
ssh user@192.168.1.2 "cat ~/project/.harness/workers/task_1_1/stderr.log"
```

**httpx not installed:**
```bash
pip install httpx
# Or: pip install agents-harness-teams[fleet]
```
