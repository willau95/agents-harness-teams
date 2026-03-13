# Extending agents-harness-teams

How to add new agent types, skills, and hooks to the harness.

---

## Adding a New Agent Type

Agents are defined as Markdown files in the `agents/` directory with YAML frontmatter.

### Step 1: Create the agent definition file

Copy the template from `templates/task-card.md` and create `agents/your-agent.md`:

```markdown
---
name: your-agent
model: claude-sonnet-4-6   # or claude-opus-4-6
role: your-role            # e.g. validation, execution, reporting
---
You are the Harness [Your Agent Name] Agent.

[Describe the agent's role and responsibility in 1-3 sentences.]

Protocol:
1. [First instruction]
2. [Second instruction]
3. [Third instruction]

[Add any output format requirements.]
```

### Step 2: Register the role in spawner.py

Add your role to the `ROLE_MODELS` dict in `harness/spawner.py`:

```python
ROLE_MODELS = {
    ...
    "your_role": "sonnet",  # or "opus" for planning/architecture roles
}
```

### Step 3: Use in phase_cycle.py (if it's a new step)

If your agent runs as a new step in the 10-step flow, add it to `PhaseCycle` in
`harness/phase_cycle.py`:

```python
async def _step_your_step(self, phase_id: str):
    """Your new step description."""
    print("[Step N/10] 🔧 YOUR STEP — ...")
    # Spawn your agent with the appropriate context
    # Write output to disk
    # Return result
```

### Agent File Conventions

| Field | Values | Notes |
|-------|--------|-------|
| `name` | kebab-case string | Matches filename (e.g., `logic-checker`) |
| `model` | `claude-opus-4-6` or `claude-sonnet-4-6` | Use opus for planning, sonnet for execution |
| `role` | string | Maps to `ROLE_MODELS` key in spawner.py |

### Built-in Agents

| File | Role | Model |
|------|------|-------|
| `agents/planner.md` | architecture | opus |
| `agents/logic-checker.md` | validation | opus |
| `agents/coder.md` | execution | sonnet |
| `agents/reviewer.md` | validation | sonnet |
| `agents/reporter.md` | reporting | sonnet |
| `agents/reviser.md` | revision | sonnet |

---

## Adding a New Skill

Skills are Markdown files in the `skills/` directory that describe behavioral patterns
for agents. They are referenced by agents in their prompts.

### Step 1: Create the skill file

```bash
cat > skills/your-skill.md << 'EOF'
# Skill: Your Skill Name

[One sentence describing what this skill enforces.]

Before [trigger condition]:
1. [First rule]
2. [Second rule]
3. [Third rule]
EOF
```

### Step 2: Reference in agent definitions (optional)

Add a reference in the relevant agent's `.md` file:

```markdown
---
name: your-agent
model: claude-sonnet-4-6
role: execution
skills:
  - your-skill
---
Apply the `your-skill` pattern from `skills/your-skill.md`.
...
```

### Built-in Skills

| File | Purpose |
|------|---------|
| `skills/verification-loop.md` | Enforce empirical verification before marking done |
| `skills/continuous-learning.md` | Extract reusable patterns at session end |
| `skills/strategic-compact.md` | Prevent context pollution across sessions |
| `skills/iterative-retrieval.md` | Load context progressively |
| `skills/ten-step-flow.md` | Reference for the 10-step methodology |

---

## Adding a New Hook

Hooks are shell scripts that run at specific Claude Code session lifecycle events.

### Available Hook Events

| Event | Trigger |
|-------|---------|
| `SessionStart` | When a Claude Code session begins |
| `SessionStop` | When a Claude Code session ends |

### Step 1: Create the hook plugin directory

```bash
mkdir -p plugins/claude-code/your-hook/
```

### Step 2: Create plugin.json

```json
{
  "name": "your-hook",
  "version": "0.1.0",
  "description": "Description of what this hook does.",
  "hooks": {
    "SessionStart": "your-start.sh",
    "SessionStop": "your-stop.sh"
  }
}
```

### Step 3: Write the hook scripts

```bash
cat > plugins/claude-code/your-hook/your-start.sh << 'EOF'
#!/usr/bin/env bash
# your-start.sh — runs at session start
set -euo pipefail

HARNESS_DIR=".harness"
# Your logic here
echo "[your-hook] Session started"
EOF

chmod +x plugins/claude-code/your-hook/your-start.sh
```

### Step 4: Configure Claude Code to use the hook

Add to your Claude Code configuration:
```json
{
  "plugins": [
    "./plugins/claude-code/your-hook"
  ]
}
```

### Built-in Hooks

| Plugin | SessionStart | SessionStop |
|--------|-------------|-------------|
| `harness-stop-hook` | — | Verify task completion signal |
| `harness-hooks` | Load task context | Save session summary |

---

## Adding a New CLI Command

Add commands to `harness/cli.py` using Typer:

```python
@app.command()
def your_command(
    arg: str = typer.Argument("default", help="Your argument"),
    flag: bool = typer.Option(False, "--flag", help="A flag"),
):
    """
    Brief description shown in --help.
    """
    console.print("[bold green]Running your-command...[/bold green]")
    # Your implementation here
```

---

## Adding a New Integration

Create a new file in `harness/integrations/`:

```python
# harness/integrations/your_integration.py
"""
Your Integration — brief description.
"""

class YourIntegration:
    def __init__(self, config: dict):
        self.config = config
    
    async def dispatch_task(self, task_id: str, context: dict) -> bool:
        """Send a task to your integration."""
        pass
    
    async def check_status(self, task_id: str) -> dict:
        """Check task status in your integration."""
        pass
```

Then use it in `harness/cli.py`:

```python
if your_flag:
    from .integrations.your_integration import YourIntegration
    integration = YourIntegration(config={...})
    # Pass to PhaseCycle
```

---

## Contributing

When adding new components:

1. Follow existing naming conventions
2. Add docstrings and type hints
3. Write tests in `tests/` for parsers and state logic
4. Update `pyproject.toml` dependencies if needed
5. Document in the appropriate `docs/` file

See `IMPLEMENTATION-SPEC.md` for the full specification.
