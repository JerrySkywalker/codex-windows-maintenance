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
