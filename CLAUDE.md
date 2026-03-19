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

## Navigation Rules

- Every course hub page (`/ai-evolution/`, `/venture-capital/`, etc.) **must have an explicit back button** in the header — `← 메인으로` linking to `../`. The logo link alone is not sufficient (users don't recognize it as clickable).
- Button style: `font-size:11px; border:1px solid var(--border); border-radius:6px; padding:4px 12px;` — class `back-btn`, placed at the right end of the header.
- Every case viewer already has a `← Hub` back-btn — keep this pattern consistent.

## AI Explanation Panel (더블클릭 단어 설명) — Design Requirements

These requirements apply to every case viewer's double-click word explanation feature.

### Output format (STRICT — do not change without explicit user approval)
```
**일반적 의미:** [단어의 사전적 정의, 1문장]

**맥락적 의미:** [이 리딩/케이스 문맥에서의 해석, 2문장 이내]
```

### Rules
- **Concise**: Total under 60 Korean words. No preamble, no analysis, no tables.
- **Markdown rendered**: `**bold**` must be shown as actual bold, not raw asterisks. Use `innerHTML` + a sanitized `renderMd()` helper, not `textContent`.
- **Visual separation**: Blank line between the two sections (rendered as `<br><br>`).
- **No extras**: No "요약", no "질문 분석", no bullet lists beyond the two fixed items.

### Server (`server.py`) requirements
- Accept both `word` and `text` keys from request body: `body.get("word") or body.get("text")`
- Return plain JSON `{"explanation": "..."}`, NOT SSE streaming (clients call `r.json()`)
- System prompt must enforce the two-section format above

### Client (`index.html`) requirements
- `openAI_server`: calls `/api/explain`, uses `r.json()`, renders with `renderMd()`
- `openAI_local` (Ollama fallback): uses separate `system` + `prompt` fields; same format instruction in `system`; streaming OK but buffer → `el.innerHTML = renderMd(buf)`
- `renderMd(text)`: escape HTML first, then apply `**bold**` → `<strong>`, `\n\n` → `<br><br>`

## Deployment

GitHub Pages from `main` branch, root directory.
URL: `diziba213.github.io/kaist-case-hub/`
