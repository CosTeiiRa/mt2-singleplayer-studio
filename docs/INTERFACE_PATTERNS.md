# Shared interface patterns

[Overview](../README.md) · [Development guide](DEVELOPMENT.md)

## Game items

Use the current shared catalogue for names, icons, effects and availability.
`itemContent(id, options)` renders the common icon, name and ID; `itemReference`
adds an inspect button with the shared hover/focus behavior. Recipe titles can
override the visible title without renaming their reward item in the catalogue.
Unknown IDs remain inspectable and missing assets receive explicit labels.

Use these helpers in search, pickers, saved items, drop tables, crafting, quest
rewards and economy tables. Call `bindImages` after replacing markup so failed
images use the same fallback. `itemHelpAttrs` connects both pointer and keyboard
focus to the same tooltip, with escaped catalogue content and configured effects.

Inspection opens read-only effects and references. Editing fields retain their
selection behavior and expose a separate **Inspect item** action. Back preserves
the underlying picker or returns focus to the source view. Selecting a reward
does not save or deploy an editor's draft.

## Server operations

`deployment_progress.py` records observed stages around existing commands. A
native game update exposes the launcher as one stage: Studio does not estimate
its internal progress. Compilation, migration, crafting, restart, health and
content verification stay separate where Studio actually runs them separately.

`web/operations.js` maps those states into shared status text. The persistent
banner survives page navigation; **View progress/result** opens the same operation
in Apply. The dialog puts the current stage first, then an optional technical log.
Failed/unverified operations open their log once without preventing its collapse.
Elapsed time uses the recorded finish time and never implies an ETA. A step count
is not a percentage of build time. Earlier receipts without stages remain valid.

Success, failed, interrupted and unverified are distinct results. Validation
explicitly leaves changes pending and does not restart the game. A lost connection
reports an unknown status, retains the operation and offers Reconnect. Newer saved
changes stay pending even when the previous operation succeeded. Completion can
be dismissed for the current session; a different operation becomes visible again.

The banner's elapsed clock is outside its live announcement. Stage/result updates
have text as well as color; the current stage has `aria-current="step"`. Errors
use the browser's top layer so an open dialog cannot hide them. Error notifications
remain until dismissed; routine success notifications close after a short delay.

## Verification boundaries

Tests cover stage ordering, terminal states, pending changes, result dismissal,
connection loss, old receipts, HTML escaping and shared identity. Browser checks
cover representative desktop flows and a read-only deployment fixture. A fixture
cannot verify an actual Docker rebuild, in-game behavior or screen-reader output.
Re-test those separately when changing deployment commands or game integration.
