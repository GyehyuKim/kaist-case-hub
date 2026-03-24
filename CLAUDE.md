# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

KAIST MBA 수업에서 요구되는 긴 영문 아티클/케이스를 수강생 전체가 쉽게 읽을 수 있는 웹 서비스.

핵심 기능:
1. 영한 대조 읽기 — 좌측 영어 원문 / 우측 한국어 번역 (전체 맥락 기반 번역)
2. 문장 대응 하이라이트 — 마우스 호버 시 좌우 원문/번역 문장 동시 하이라이트 (data-sid 매칭)
3. AI 맥락 설명 — 로컬 Ollama(qwen3.5)로 단어 더블클릭 시 맥락 설명 + AI 질문 기능

## Structure

```
/                             Top-level hub (course selector + login gate)
/venture-capital/             BIZ.60010 VC (Prof. 백용욱)
  athleta/                    Athleta Corporation (HBS 9-803-045)
  timecredit/                 TimeCredit (HBS 9-824-073)
  coupa/                      Coupa Software
/ai-evolution/                BIZ.69911 AI Evolution (Prof. 이지수)
  manna/                      Manna (Marshall Brain)
  navigating/                 Navigating the Jagged Frontier + MoLG (2탭)
  something-big/              Something Big Is Happening (소스만, 뷰어 미완)
```

## Running Locally

Each course has its own server. Run from the course directory:

```bash
cd venture-capital && python server.py   # port 8080
cd ai-evolution && python server.py      # port 8081
```

The server auto-opens the browser. Static files are served from the same directory. Ollama must be running separately (`ollama serve`).

For GitHub Pages (no server), viewers fall back to `openAI_local` — direct Ollama calls from the browser via `http://localhost:11434`.

## Key Conventions

- **Self-contained HTML**: Each viewer is a single `index.html` with inline CSS/JS. No shared assets.
- **Auth**: sessionStorage key `kaist-case-auth`, password `kaist2026`. Login gate at top-level hub only; course/case pages redirect to `../` if not authenticated.
- **terms.json**: Per-course glossary at course root (e.g., `venture-capital/terms.json`). Viewers fetch `../terms.json`.
- **server.py**: Per-course Ollama proxy. VC on port 8080, AI Evolution on port 8081.
- **Captures/**: Per-case screenshot folders. Referenced via relative paths in viewers.
- **Navigation**: Case viewer `<- Hub` links to `../` (course hub). Course hub logo links to `../` (top-level hub).

## Case Viewer HTML Structure

Each `index.html` case viewer is self-contained. Key structural elements:

- **`.bi-row`**: Two-column grid (`1fr 1fr`) containing `.cell.en` and `.cell.kr` side by side
- **`.sent[data-sid]`**: Wraps individual sentences. Hover/click highlights that element; matching `data-sid` values across EN/KR pair the sentences for synchronized highlighting
- **`.cell.full`**: Full-width row (for exhibits/tables spanning both columns)
- **`.exhibit-wrap`**: Zoomable image widget — contains `.exhibit-toolbar` (brightness/contrast/sharpness sliders), `.exhibit-stage` (pan+zoom canvas), `.exhibit-hint`
- **`#ai-panel`**: Fixed bottom panel for AI word explanations; slides up on double-click/drag-select; shows streaming tokens from server

**Multi-reading tab variant** (`navigating/index.html`): uses `.reading-tabs` / `.tab-btn` to switch between multiple readings within one viewer — a superset of the standard bilingual layout.

## Automation

| Skill | 용도 |
|-------|------|
| `/translate-case` | HBS 케이스: 스캔 OCR → 번역 → 뷰어 빌드 (7단계) |
| `/translate-reading` | 학술 리딩: 맥락 번역 → KR.md 생성 |

도구 체인: `~/.claude/tools/` — ocr_to_md, ocr_cleanup, identify_pages, build_viewer, translate

## Adding a New Case

1. Create folder: `<course>/<case-slug>/`
2. Place `index.html` (bilingual viewer), `Captures/` (screenshots), optional `*_KR.md`
3. Update course hub's `CASES` array: set `status: 'available'`, `url: '<case-slug>/'`
4. Viewer must use `AUTH_KEY = 'kaist-case-auth'` and `fetch('../terms.json')`
5. 또는 `/translate-case` 스킬로 전체 파이프라인 자동 실행

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
- Accept `text` key from request body (and `context` for surrounding sentence)
- Stream SSE (`Content-Type: text/event-stream`): first sends `{"model": "..."}`, then `{"token": "..."}` per token, finally `{"done": true}`
- System prompt must enforce the two-section format above
- For qwen3 models: set `"think": false` at top level of Ollama payload to disable reasoning tokens

### Client (`index.html`) requirements
- `openAI_server`: calls `/api/explain` with `fetch()`, reads streaming response via `r.body.getReader()`, buffers tokens, renders with `el.innerHTML = renderMd(buf)`
- `openAI_local` (Ollama fallback): calls Ollama directly at `http://localhost:11434/api/generate` with separate `system` + `prompt` fields; streaming OK but buffer → `el.innerHTML = renderMd(buf)`
- `renderMd(text)`: escape HTML first, then apply `**bold**` → `<strong>`, `\n\n` → `<br><br>`

## Deployment

GitHub Pages from `main` branch, root directory.
URL: `diziba213.github.io/kaist-case-hub/`
