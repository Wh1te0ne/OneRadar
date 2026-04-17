# OneRadar Desktop

This directory contains the V1 desktop shell for OneRadar.

## Intent

The desktop client is a web-first UI wrapped in Tauri. It is responsible for:

- server connection and login
- manual link import
- library browsing
- item reading for articles and Bilibili transcripts
- highlights, notes, tags, and collections
- provider and settings management

## Current State

This is a lightweight skeleton, not a full application.

It provides:

- a React router shell
- connect/login screen
- library screen
- item detail screen
- settings screen
- Tauri config placeholders

## Expected Growth Path

1. Wire the app to the API server.
2. Replace mocked library data with server-backed item queries.
3. Add authentication persistence.
4. Add import forms and task status polling.
5. Add reader interactions for highlights, notes, and transcript jumps.
6. Expand provider management into real CRUD flows.

## Local Development

Install dependencies and run the Vite shell first:

```bash
npm install
npm run dev
```

When the Tauri toolchain is ready, the shell can be launched with:

```bash
npm run tauri:dev
```

## Notes

- This repo intentionally keeps UI logic in standard React code so the same patterns can later be reused for mobile or PWA-oriented work.
- The final desktop experience should keep the reader fast and quiet, not overloaded with controls.
