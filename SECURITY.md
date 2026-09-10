# Security review (M9)

Local-only companion. No AI, no cloud, no accounts.

## Guarantees

- No shell execution: the codebase never uses `shell=True`, `os.system`,
  or `Popen` with a shell. Reminder text is data only.
- No network by default: protocol, runtime, scheduler, GUI, and CLI work
  from local files. The only network surface is the opt-in WebSocket
  adapter, which refuses non-loopback hosts (`127.0.0.1`, `localhost`, `::1`).
- Local paths only: packs reject paths escaping their directory, configs
  resolve relative to their own file, and `--root`/`COMPANION_ROOT` never
  execute anything.
- Atomic writes: state and reminders use tmp + `fsync` + replace. Corrupt
  JSON is preserved as `*.corrupt`, never silently dropped.

## Verification

```powershell
py -m pytest tests/test_hardening.py -v
companion doctor
```

`test_security_no_shell_or_remote_network` greps `src/companion` for
`shell=True`, `os.system(`, `urllib.request`, `requests.`, `socket.bind`,
and `Popen(` and fails on any hit. `doctor` reports writability, JSON
validity, corrupt backups, Tk availability, and optional deps.
