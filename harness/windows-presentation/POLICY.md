# Windows process presentation policy

Background child processes with captured or null standard streams must not
create a visible console or take focus. The implementation must preserve
timeouts, environment handling, Job Object containment, process cleanup, and
MCP pipe behavior when it composes `CREATE_NO_WINDOW` with existing flags.

Interactive terminal inheritance, ConPTY sessions, authentication prompts,
external editors, and user requested app opening retain their visible behavior.
Managed daemon detachment retains its own creation flags. A no-window flag is
applied at each background launch boundary, never as a global default for all
children.

Qualification observes create, show, and foreground events. A zero-event
background result needs a visible positive control and functional assertions;
the absence of a visible popup alone is insufficient evidence.

Managed/shared daemon lifetime additionally requires
`REJECT_UNPROVEN_RESIDUAL_JOB_MEMBERSHIP`: successful breakaway from an inner Job
does not prove independence from a retained ancestor. Qualification rejects any
residual Job or failed membership query, including harmless-looking outer Jobs.
The three-case native fixture proves survival without a residual Job, bounded
survival in a benign outer Job and death on closing a kill-on-close outer Job.
This fixture owns only surrogate children; it cannot assign the controlling shell
or Codex session to its test Jobs. Actual source rejection belongs to G03/G04.

See [candidate qualification](CANDIDATE-QUALIFICATION.md) for the separate stable
and unreleased mappings and the managed-daemon/GPT-6 Sol release gates.
