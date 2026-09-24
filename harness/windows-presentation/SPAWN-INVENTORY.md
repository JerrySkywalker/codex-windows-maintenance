# Windows spawn inventory

Review these source paths at every upstream port. Paths are relative to the
Codex source checkout; line numbers are intentionally omitted because they move.

| Boundary | Source paths | Expected behavior |
| --- | --- | --- |
| Code Mode host | `codex-rs/code-mode/src/remote_session/connection.rs` | Background, hidden, piped IPC |
| Captured shell | `codex-rs/core/src/spawn.rs` | Hidden only for redirected output; inherited terminal remains visible |
| Hooks and notify | `codex-rs/hooks/src/engine/command_runner.rs`, `codex-rs/hooks/src/legacy_notify.rs` | Hidden, preserve job and fallback flags |
| Internal Git and plugins | `codex-rs/git-utils/src`, `codex-rs/core-plugins/src`, `codex-rs/worktree/src/git.rs` | Hidden, preserve timeout and cleanup |
| MCP helpers | `codex-rs/rmcp-client/src/http_headers.rs`, `codex-rs/rmcp-client/src/stdio_server_launcher.rs`, `codex-rs/utils/pty/src/child_command.rs` | Hidden, preserve stdio and job retries |
| PowerShell probes | `codex-rs/shell-command/src`, `codex-rs/tui/src/tui/keyboard_modes.rs` | Hidden, preserve captured output |
| Pipe and sandbox helpers | `codex-rs/utils/pty/src/pipe.rs`, `codex-rs/windows-sandbox-rs/src` | Hidden only for pipe mode; ConPTY stays interactive |
| CLI, daemon, exec server | `codex-rs/cli/src`, `codex-rs/app-server-daemon/src`, `codex-rs/exec-server/src` | Hide background probes and cleanup; preserve daemon detachment and app opening |

Review new `Command`, `CreateProcessW`, and `CreateProcessAsUserW` sites in the
upstream diff. The policy in `POLICY.md` decides whether each site is hidden.
