# Issue tracker: Local Markdown

Issues and specs live in `.scratch/<feature-slug>/`.

- Specs: `spec.md`.
- Tickets: `issues/<NN>-<slug>.md`, numbered from 01, one file per ticket.
- Triage state: a `Status:` line using the mapping in `triage-labels.md`.
- Comments: append under `## Comments`.
- Publishing means creating the relevant Markdown file.
- Fetching means reading the referenced ticket file.

## Wayfinding

- Map: `.scratch/<effort>/map.md`, containing Notes, Decisions-so-far, and Fog.
- Children: `issues/NN-<slug>.md`, with a `Type:` of research, prototype,
  grilling, or task.
- Dependencies: `Blocked by: NN, NN`. All listed tickets must be resolved
  before work starts.
- Frontier: choose the first numbered open, unblocked, unclaimed ticket.
- Claim: save `Status: claimed` before starting work.
- Resolve: append `## Answer`, set `Status: resolved`, and add a summary
  and ticket link to the map's Decisions-so-far.
