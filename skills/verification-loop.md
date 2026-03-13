# Skill: Verification Loop
Enforce empirical verification before marking any task complete.
Before writing completion signal:
1. Re-read success_criteria
2. Run verification commands
3. Only write complete.json if ALL pass
4. If any fail: continue working, do not exit session
