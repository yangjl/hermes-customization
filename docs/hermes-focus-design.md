# Hermes Focus: agent-workbench frontend design

Status: implemented theme foundation; structural redesign proposed  
Reviewed: 2026-08-21  
Source project: `/Users/jyang21/.hermes/hermes-agent/web`  
Customization project: `/Users/jyang21/Documents/projects/hermes-customizations`

## Product direction

Hermes should feel like an **agent workbench**, not a terminal placed inside an
admin dashboard and not a generic chat clone. The primary job is to start or
resume work, follow what the agent is doing, intervene when needed, and inspect
the result. Model administration, gateway operations, plugins, and credentials
are important but secondary.

The design rule is:

> Conversation owns intent; a run timeline explains execution; an inspector
> holds context and artifacts; administration stays behind progressive
> disclosure.

## Current-state audit

The audit used the live Hermes dashboard at desktop (1600 × 1000) and narrow
viewport (390 × 844), plus the React source for `App.tsx`, `ChatPage.tsx`,
`ChatSidebar.tsx`, and `ChatSessionList.tsx`.

### What is already strong

- Chat remains mounted while navigating, so a running PTY is not discarded.
- Session resume, reconnect, model selection, reasoning level, image paste, and
  copy-last-response are real capabilities rather than mock controls.
- The right panel can collapse, and narrow layouts already use a drawer.
- Backend and event-feed failure states are represented explicitly.
- The theme contract provides palette, typography, density, component variables,
  terminal colors, and scoped custom CSS without patching the source checkout.

### What makes the interface harder than it needs to be

1. **The global navigation has one visual weight.** Chat, routine history,
   developer configuration, credentials, gateway operations, documentation,
   and plugins appear as peers. The first screen reads as a control panel before
   it reads as an agent.
2. **The chat's empty/loading state is visually blank.** A cursor on a large
   white canvas does not explain readiness, available input, useful commands,
   attachments, or whether the runtime is still starting.
3. **The right rail mixes different questions.** Model/effort answers “what will
   run?” while Sessions answers “where was I?” They compete for the same narrow
   column even though one is run context and the other is navigation history.
4. **The terminal is powerful but semantically opaque.** Tool calls, approvals,
   agent reasoning, files, errors, and final answers share the same character
   stream. The UI cannot selectively collapse, label, link, or announce those
   states as well as structured components can.
5. **Mobile chrome is fragile.** The model/tools label and copy-response control
   can exceed the narrow viewport. The terminal remains usable, but important
   controls are clipped or too quiet.
6. **Wide tracking and monospace UI text slow scanning.** The original visual
   language suits a terminal brand, but session history and navigation are
   product UI, not terminal output.

## Target information architecture

### Desktop

Use four layers, with only three visible by default:

1. **App rail (56–64 px):** Chat, Sessions, Files, Automations; a single Manage
   entry opens Models, Skills, Plugins, MCP, Channels, Profiles, Keys, and
   System. The rail shows gateway health as a quiet status dot.
2. **Conversation index (260–288 px, collapsible):** New task, search, recent
   sessions, pinned sessions, and scoped profile. Session navigation belongs
   here rather than in the run inspector.
3. **Conversation workspace (fluid, primary):** semantic transcript, run
   progress, and one sticky composer. It always receives the most space.
4. **Run inspector (300–340 px, closed by default):** Overview, Timeline,
   Artifacts, and Context tabs. Model, reasoning, token/context use, working
   directory, files, and tool details live here.

On screens below roughly 1280 px, collapse the app rail to icons and keep the
conversation index optional. The workspace must never shrink below a readable
message column merely to preserve secondary rails.

### Mobile

- A 56 px header contains navigation, the session title, and one inspector icon.
- The transcript is the only central surface.
- The composer remains sticky above the safe-area and keyboard inset.
- Conversations and the run inspector open as separate full-height drawers.
- Model and reasoning appear in a compact context sheet, not as a clipped label.
- No important action is hover-only; primary targets are at least 44 × 44 px.

## Conversation workspace

The terminal remains a supported **Console view**, but it should stop being the
only representation of a session. A structured Chat view can consume the same
gateway event stream and render:

| Event | UI treatment |
|---|---|
| User message | concise user bubble/card with attachments |
| Assistant text | readable Markdown in a bounded column |
| Reasoning | collapsed disclosure, clearly labeled |
| Tool call | compact timeline row; running/success/error state |
| Approval or question | accessible inline human-input card |
| Artifact/file | preview card that opens the inspector |
| Subagent | nested run card with step progress |
| Failure/offline | persistent inline state with a nearby retry action |
| Final answer | strong but quiet completion boundary and copy action |

The composer is the only write surface. File upload, voice, slash commands,
model choice, and context attachments change composer state; rails should never
open competing input forms for the same task.

### Empty and starting states

Replace the blank cursor-only canvas with one explicit state at a time:

- **Starting Hermes…** with elapsed time and a cancel/retry path.
- **Ready** with a focused composer, three short example intents, and the
  current profile/working directory.
- **Reconnecting** with the transcript preserved and input temporarily gated.
- **Ended** with Resume, Start new task, and Open console actions.

These states must be perceivable in text, not only by color or animation.

## Visual system: Hermes Focus

`dashboard-themes/hermes-focus.yaml` implements the theme-level portion of this
design without editing the Hermes checkout:

- cool neutral canvas and white work surfaces;
- blue reserved for selection, focus, and primary action;
- green/amber/red reserved for real status;
- system sans for interface scanning and JetBrains Mono only for terminal/code;
- stronger selected navigation, quieter system chrome, bounded transcript, and
  distinct inspector surface;
- explicit focus rings and reduced-motion behavior;
- mobile icon treatment that avoids long clipped labels.

The theme deliberately does **not** hide routes or use brittle `nth-child`
selectors to fake a new information architecture. Grouping navigation, moving
sessions, and rendering semantic events require source-level components.

## Implementation sequence

### Stage 0 — theme foundation (implemented)

- Install `hermes-focus.yaml` through the customization repository.
- Preserve the original Light Lab theme as an option.
- Validate live desktop and narrow layouts without patching Hermes source.

### Stage 1 — shell hierarchy (small source change)

- Replace the flat route list with four primary destinations plus Manage.
- Move recent sessions into a conversation-index drawer/rail.
- Replace the mobile “Model & tools” text button with a stable icon control.
- Add explicit loading, ready, reconnecting, and ended chat states.
- Keep the current persistent `ChatPage` mount and URL resume behavior.

### Stage 2 — structured conversation (medium source change)

- Define a versioned frontend event union from the existing gateway feed.
- Render semantic message/tool/approval/artifact components.
- Keep Console as a view toggle and as a fail-safe for events not yet modeled.
- Preserve unknown events as readable plain text rather than dropping them.
- Persist only session-scoped composer text/selected skill; clear after a
  confirmed send.

### Stage 3 — run inspector and scale (medium source change)

- Add Overview, Timeline, Artifacts, and Context tabs.
- Backfill details only when expanded.
- Virtualize transcripts and session lists above a measured threshold.
- Add context-pressure, cost, and token indicators that reserve their layout
  while data is loading.

## Acceptance evidence

For each structural stage, prove:

- 1600 × 1000, 1280 × 800, and 390 × 844 layouts with no horizontal overflow;
- starting, ready, streaming, approval, success, error, reconnecting, and ended
  states;
- long session title, long model name, and Chinese UI strings;
- keyboard navigation, visible focus, drawer focus restoration, and Escape;
- screen-reader names for icon-only controls and live status changes;
- reduced motion and 200% text zoom;
- a real session resume and a running chat that survives route changes.

The Stage 0 theme was loaded through Hermes' theme API and visually checked at
1600 × 1000 and 390 × 844 on 2026-08-21. It introduced no Hermes source-tree
changes.

## Reuse boundary

Use the theme as a low-risk customization against the current dashboard theme
contract. Its selectors intentionally rely only on stable shell IDs,
`aria-controls`, `aria-current`, `data-chat-active`, and the documented terminal
host class. Recheck after Hermes upgrades that change these hooks.

The structural proposal assumes Hermes continues to expose a structured gateway
event feed alongside the PTY. If the event protocol is not authoritative enough
to reconstruct a session, keep Console primary until server-owned session
history and terminal events can be reconciled.

