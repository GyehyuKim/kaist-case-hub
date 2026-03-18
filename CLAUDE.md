# CLAUDE.md

## Repository Purpose

Multi-course case study hub for KAIST MBA Spring 2026. Serves bilingual (EN/KR) case viewers with AI term explanation via local Ollama.

## Structure

```
/                       Top-level hub (course selector + login gate)
/venture-capital/       BIZ.60010 VC course hub (Prof. 백용욱)
/venture-capital/athleta/       Athleta case viewer
/venture-capital/timecredit/    TimeCredit case viewer
/ai-evolution/          BIZ.69911 AI Evolution course hub (Prof. 이지수)
/ai-evolution/manno/            Manna case (pending)
/ai-evolution/navigating/       Navigating the Jagged Frontier (pending)
```

## Key Conventions

- **Self-contained HTML**: Each viewer is a single `index.html` with inline CSS/JS. No shared assets.
- **Auth**: sessionStorage key `kaist-case-auth`, password `kaist2026`. Login gate at top-level hub only; course/case pages redirect to `../` if not authenticated.
- **terms.json**: Per-course glossary at course root (e.g., `venture-capital/terms.json`). Viewers fetch `../terms.json`.
- **server.py**: Per-course Ollama proxy. VC on port 8080, AI Evolution on port 8081.
- **Captures/**: Per-case screenshot folders. Referenced via relative paths in viewers.
- **Navigation**: Case viewer `<- Hub` links to `../` (course hub). Course hub logo links to `../` (top-level hub).

## Adding a New Case

1. Create folder: `<course>/<case-slug>/`
2. Place `index.html` (bilingual viewer), `Captures/` (screenshots), optional `*_KR.md`
3. Update course hub's `CASES` array: set `status: 'available'`, `url: '<case-slug>/'`
4. Viewer must use `AUTH_KEY = 'kaist-case-auth'` and `fetch('../terms.json')`

## Deployment

GitHub Pages from `main` branch, root directory.
URL: `diziba213.github.io/kaist-case-hub/`
