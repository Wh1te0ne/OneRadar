# UI Direction V1

## Source Of Truth

2026-06 之后，OneRadar 的 UI 以“信息雷达 + 临时链接分析 + 调用接口”为主，不再以阅读库、稍后读、内置笔记或知识库组织为主。

参考旧 Stitch 设计时只继承视觉气质，不继承旧信息架构。

## Design Thesis

OneRadar V1 should feel like a calm Chinese-first information operations console, not a general reading app or a generic admin dashboard.

The approved direction is:

- quiet, utility-first, and editorially readable
- dense enough for RSS source work and daily news scanning
- low-chrome navigation with clear task surfaces
- restrained panels and typography rather than dashboard-card mosaics
- first-class model/provider configuration because summaries and analysis depend on it
- no Library / read-later / notes mood in the primary product

## Layout Rules

Follow these structure rules when implementing screens:

- Use a persistent navigation rail or compact mobile tab bar for workspace switching.
- Default primary views are 每日新闻, 信息源, 链接分析, 调用接口, and 设置.
- RSS entries open the original source URL directly.
- Do not add read/unread state, reader progress, highlights, notes, folders, collections, or saved-library affordances to RSS rows.
- Keep model/provider settings visible under 设置 and reflect model availability on analysis surfaces.
- Use side panels only for secondary context such as source status, API examples, provider state, or result metadata.
- Avoid marketing-style hero sections and decorative card-heavy composition.

## Visual Rules

- Chinese-first UI copy in V1.
- Theme modes: system, light, dark; default to system.
- No heavy 1px border grid. Use tonal separation first.
- Use warm neutral surfaces with restrained accent color.
- Buttons and chips may be compact, but routine panels should stay restrained.
- Tables, rows, and result panes should be scannable and stable; avoid layout shifts when content loads.

## Interaction Rules

- RSS source management supports adding, refreshing, removing, and filtering by source/date.
- Clicking an RSS entry opens the original link in the system browser or a new browser tab.
- Daily news is a date-based brief generated from cached RSS entries and opens source links directly.
- Link analysis is temporary: submit URL, return original text/visible platform text, summary, metadata, and JSON. It must not create a saved reading item.
- API/MCP uses integration tokens. Newly created tokens should support both `mcp:read` and `analysis:write` unless a narrower scope is explicitly needed.
- Provider/model configuration remains a core settings workflow and must not be hidden as an advanced-only feature.

## Screen Intent

### 每日新闻

Use as the daily scanning surface:

- saved daily report by date
- AI-first grouped news structure
- source links that jump to original pages
- regenerate/share actions where available

### 信息源

Use as the RSS operations surface:

- source add/remove/refresh
- source and date filters
- cached entry list
- direct source opening
- refresh errors and source health

### 链接分析

Use as the temporary analysis workbench:

- URL input for webpage, WeChat article, Bilibili, and future video/social platforms
- original text or platform-visible text
- AI summary when a summarization model is configured
- JSON result for downstream copying
- explicit indication that nothing is saved to a reading library

### 调用接口

Use as the product-to-product integration surface:

- MCP endpoint
- temporary analysis endpoint
- integration token creation/revocation
- curl examples and capability matrix

### 设置

Use as the system surface:

- provider setup and connection testing
- current chat/summarization model
- ASR/transcription model where relevant
- theme mode
- server connection diagnostics
- source-specific integration credentials such as Bilibili cookies

## Implementation Guidance

When changing UI:

- preserve the new information architecture first
- remove old Library/reader affordances from primary navigation instead of hiding them behind copy
- keep shared behavior coherent across desktop web and mobile web surfaces
- leave native Android changes for a dedicated pass unless the user explicitly asks, because the current deploy target is the Docker-served web stack
- do not regress into the old reader/archive product shape when adding missing features
