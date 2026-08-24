# Commander profile state

## Assumptions

1. All mutable Commander state belongs in `%USERPROFILE%\.commander`, not in
   the installed skill directory.
2. This includes configuration, learned rules, response templates, decision
   history, backlog, pane registration, unresolved-block queue, command
   aggregates, and watcher diagnostics.
3. Existing per-user state can be discarded; no migration compatibility is
   required.

## Plan

1. Tidy First: retain the watcher's existing centralized path constants; verify
   no structural refactor is needed.
2. Add one watcher acceptance test that drives an auto-approved event from
   `%USERPROFILE%\.commander` state and verifies its decision history is
   written there; verify it fails against old skill-directory paths.
3. Redirect watcher state constants and state-loading helpers to
   `%USERPROFILE%\.commander`; verify the acceptance test and focused watcher
   suite pass.
4. Update Commander startup and memory-format documentation to initialize only
   `%USERPROFILE%\.commander`; verify no old mutable storage path remains in
   Commander documentation or watcher code.
5. Remove the local legacy `.claude\skills\commander` state after confirming it
   is not the installed skill source; verify the legacy path no longer exists
   and the new profile directory does.
