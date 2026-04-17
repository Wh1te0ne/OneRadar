# UI Direction V1

## Source Of Truth

The approved interface baseline for V1 is the Stitch project AI???? (projects/7116847179377516441).

Reference screens as of 2026-04-13:

- Feed ??? (OneRadar)
- Library ??? (OneRadar)
- AI ????? (OneRadar)
- AI ??/????? (OneRadar)
- ?? Settings

Use this Stitch project as the visual and structural baseline for desktop implementation unless the user explicitly overrides it.

## Design Thesis

OneRadar V1 should feel like a calm Chinese-first editorial reading workspace, not a generic admin dashboard.

The approved direction is:

- high-end editorial
- low-chrome
- tonal layering instead of hard borders
- spacious Chinese typography
- library / archive mood rather than analytics dashboard mood
- primary emphasis on reading, classification, and AI-assisted understanding

## Layout Rules

Follow these structure rules when implementing screens:

- Use a persistent navigation rail or floating bridge for workspace switching.
- Default primary views are Feed, Library, Article Reader, Video/Podcast Reader, and Settings.
- Keep the main content area focused on one reading task at a time.
- Use an inspector or side panel only when it provides secondary context such as metadata, AI summary, notes, or actions.
- Prefer surface changes, spacing, and typography for hierarchy before adding dividers or cards.
- Avoid dashboard-card mosaics.

## Visual Rules

- Chinese-first UI copy in V1.
- Theme modes: system, light, dark; default to system.
- No heavy 1px border grid. Use tonal separation first.
- Use warm neutral surfaces and one indigo-family accent.
- Use premium-but-readable typography with generous line-height for Chinese text.
- Buttons and chips may use rounded pills, but routine panels should stay restrained.
- Reading surfaces should feel like paper layers, not widgets.

## Interaction Rules

- Inbox is the default landing space for new imports.
- Folder movement should feel lightweight and immediate.
- Stable UID should be visible in import feedback and detail surfaces, but not dominate the reading flow.
- Reader actions should stay close to content: highlight, note, summary, jump to source, move to folder.
- For video/podcast content, timestamp navigation must be treated as a first-class reader action.

## Missing Functional Additions Allowed On Top Of This Design

When functionality is missing, add it within this visual framework instead of changing the overall UI direction.

P0 additions allowed within the Stitch baseline:

- manual link import entry
- import processing state and retry
- duplicate detection feedback
- Inbox to folder organization flow
- provider configuration
- article highlight and note interactions
- AI summary and outline panel
- video transcript segments with timestamp jump
- delete, archive, favorite, and reading progress actions
- search and filter controls

## Screen Intent

### Feed

Use as the triage surface:

- newly imported items
- processing items
- suggested next reading
- quick classification into folders

### Library

Use as the organized archive:

- Inbox
- folders
- saved collections
- filters and search

### Article Reader

Use as the long-form reading surface:

- clean readable body
- summary / outline
- highlight and notes
- source jump
- reading state

### Video Or Podcast Reader

Use as the transcript-first reading surface:

- transcript segments
- timestamp jump
- subtitle / ASR provenance
- summary / outline
- notes tied to time ranges

### Settings

Use as the system surface:

- provider setup
- theme mode
- parsing / model defaults
- server connection diagnostics

## Implementation Guidance

When converting Stitch to code:

- preserve the information architecture first
- preserve spacing and hierarchy before decorative detail
- prefer layout and typography fidelity over perfect visual imitation
- do not regress into a generic CRUD admin look when adding missing features
- new screens should inherit this design language instead of inventing a separate one
