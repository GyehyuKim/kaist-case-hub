"""
build_molg.py - Rebuild MoLG section in index.html with sentence-level bi-rows.

Parses MoLG_original.md (EN) and MoLG_KR.md (KR), splits into paragraphs and
sentences, aligns with LaBSE, and rebuilds the reading-2 section in index.html.
"""

import re
import sys
import html as html_module
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path(__file__).parent
EN_FILE = BASE / "MoLG_original.md"
KR_FILE = BASE / "MoLG_KR.md"
INDEX_FILE = BASE / "index.html"


# ---------------------------------------------------------------------------
# EN sentence splitter (character-level state machine)
# ---------------------------------------------------------------------------
EN_ABBREVS = {
    "mr", "mrs", "ms", "dr", "jr", "sr", "inc", "ltd", "corp", "co", "vs",
    "etc", "gov", "prof", "rev", "vol", "no",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "e.g", "i.e",
}


def split_en_sentences(text):
    """Split English text into sentences using character-level state machine."""
    sentences = []
    current = []
    i = 0
    n = len(text)
    paren_depth = 0

    while i < n:
        ch = text[i]

        if ch in "([":
            paren_depth += 1
            current.append(ch)
            i += 1
            continue
        if ch in ")]":
            paren_depth = max(0, paren_depth - 1)
            current.append(ch)
            i += 1
            continue

        if ch in ".!?" and paren_depth == 0:
            # Check for ellipsis
            if ch == "." and i + 1 < n and text[i + 1] == ".":
                current.append(ch)
                i += 1
                continue

            # Check decimal: digit.digit
            if ch == "." and i > 0 and text[i - 1].isdigit() and i + 1 < n and text[i + 1].isdigit():
                current.append(ch)
                i += 1
                continue

            # Absorb closing quotes after terminator
            end_idx = i + 1
            while end_idx < n and text[end_idx] in "\"''\u201d\u2019":
                end_idx += 1

            term_char = text[i:end_idx]
            current.append(term_char)

            # Look ahead for next non-whitespace
            j = end_idx
            while j < n and text[j] in " \t":
                j += 1

            if j >= n:
                sent = "".join(current).strip()
                if sent:
                    sentences.append(sent)
                current = []
                i = end_idx
                continue

            next_ch = text[j]

            # Check if this is just an abbreviation
            if ch == ".":
                pre_text = "".join(current[:-1])
                pre_words = pre_text.split()
                word_before = pre_words[-1].lower().rstrip(".") if pre_words else ""
                if word_before in EN_ABBREVS:
                    i = end_idx
                    continue

                # Single capital initial: A. B. etc.
                if pre_words and len(pre_words[-1]) == 1 and pre_words[-1].isupper():
                    i = end_idx
                    continue

            # Split if next char is uppercase, or if '?' or '!'
            if next_ch.isupper() or ch in "!?" or (ch == "." and next_ch.isupper()):
                sent = "".join(current).strip()
                if sent:
                    sentences.append(sent)
                current = []
                i = end_idx
                while i < n and text[i] in " \t":
                    i += 1
                continue

            i = end_idx
            continue

        current.append(ch)
        i += 1

    sent = "".join(current).strip()
    if sent:
        sentences.append(sent)

    return [s for s in sentences if s.strip()]


# ---------------------------------------------------------------------------
# KR sentence splitter
# ---------------------------------------------------------------------------

def split_kr_sentences(text):
    """Split Korean text into sentences."""
    if not text.strip():
        return []

    # Split on Korean sentence endings followed by period/!/?
    parts = re.split(r'(?<=[다요죠군네])(?:[.!?])(?=\s|$)', text)

    result = []
    for part in parts:
        part = part.strip()
        if part:
            # Further split on ". " followed by Korean or uppercase
            sub = re.split(r'(?<=\.)\s+(?=[가-힣A-Z])', part)
            for s in sub:
                s = s.strip()
                if s:
                    result.append(s)

    if not result:
        return [text.strip()] if text.strip() else []
    return result


# ---------------------------------------------------------------------------
# LaBSE alignment
# ---------------------------------------------------------------------------

def labse_align(en_sents, kr_sents, model):
    """DP alignment with 1:1, 1:2, 2:1 transitions."""
    import numpy as np

    if not en_sents or not kr_sents:
        return []

    en_emb = model.encode(en_sents, normalize_embeddings=True, show_progress_bar=False)
    kr_emb = model.encode(kr_sents, normalize_embeddings=True, show_progress_bar=False)

    m = len(en_sents)
    k = len(kr_sents)

    sim = np.dot(en_emb, kr_emb.T)

    NEG_INF = float("-inf")
    dp = [[NEG_INF] * (k + 1) for _ in range(m + 1)]
    back = [[None] * (k + 1) for _ in range(m + 1)]
    dp[0][0] = 0.0

    for i in range(m + 1):
        for j in range(k + 1):
            if dp[i][j] == NEG_INF:
                continue
            score = dp[i][j]

            # 1:1
            if i < m and j < k:
                ns = score + sim[i][j]
                if ns > dp[i + 1][j + 1]:
                    dp[i + 1][j + 1] = ns
                    back[i + 1][j + 1] = (i, j, "1:1")

            # 1:2 (one EN aligns to two KR)
            if i < m and j + 1 < k:
                avg_kr = (kr_emb[j] + kr_emb[j + 1]) / 2.0
                avg_kr /= (np.linalg.norm(avg_kr) + 1e-10)
                ns = score + float(np.dot(en_emb[i], avg_kr))
                if ns > dp[i + 1][j + 2]:
                    dp[i + 1][j + 2] = ns
                    back[i + 1][j + 2] = (i, j, "1:2")

            # 2:1 (two EN aligns to one KR)
            if i + 1 < m and j < k:
                avg_en = (en_emb[i] + en_emb[i + 1]) / 2.0
                avg_en /= (np.linalg.norm(avg_en) + 1e-10)
                ns = score + float(np.dot(avg_en, kr_emb[j]))
                if ns > dp[i + 2][j + 1]:
                    dp[i + 2][j + 1] = ns
                    back[i + 2][j + 1] = (i, j, "2:1")

    if dp[m][k] == NEG_INF:
        pairs = []
        for idx in range(min(m, k)):
            pairs.append(((idx,), (idx,)))
        return pairs

    alignments = []
    ci, cj = m, k
    while ci > 0 or cj > 0:
        if back[ci][cj] is None:
            break
        pi, pj, ttype = back[ci][cj]
        if ttype == "1:1":
            alignments.append(((pi,), (pj,)))
        elif ttype == "1:2":
            alignments.append(((pi,), (pj, pj + 1)))
        elif ttype == "2:1":
            alignments.append(((pi, pi + 1), (pj,)))
        ci, cj = pi, pj

    alignments.reverse()
    return alignments


def positional_align(en_sents, kr_sents):
    """Positional 1:1 alignment fallback (no LaBSE needed)."""
    m, k = len(en_sents), len(kr_sents)
    alignments = []
    for i in range(min(m, k)):
        alignments.append(((i,), (i,)))
    # Remaining EN sentences (if EN > KR): attach to last KR
    if m > k and k > 0:
        for i in range(k, m):
            ei, ki = alignments[-1]
            alignments[-1] = (ei + (i,), ki)
    # Remaining KR sentences (if KR > EN): attach to last EN
    elif k > m and m > 0:
        for j in range(m, k):
            ei, ki = alignments[-1]
            alignments[-1] = (ei, ki + (j,))
    return alignments


# ---------------------------------------------------------------------------
# HTML escaping helper
# ---------------------------------------------------------------------------

def esc(text):
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


# ---------------------------------------------------------------------------
# Markdown parsing
# ---------------------------------------------------------------------------

def parse_en_md(path):
    """Parse MoLG_original.md into sections."""
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()

    # Strip header lines at the start of file (title / subtitle / date)
    # e.g. "Machines of Loving Grace1", "How AI Could Transform...", "October 2024"
    HEADER_PREFIXES = (
        "Machines of Loving Grace",
        "How AI Could Transform",
        "October 20",
    )
    filtered = []
    for line in lines:
        if line.strip() and any(line.strip().startswith(p) for p in HEADER_PREFIXES):
            continue  # skip header metadata
        filtered.append(line)
    lines = filtered

    SECTION_TITLES = [
        "Basic assumptions and framework",
        "1. Biology and health",
        "2. Neuroscience and mind",
        "3. Economic development and poverty",
        "4. Peace and governance",
        "5. Work and meaning",
        "Taking stock",
        "Footnotes",
    ]

    sections = []
    current_section_title = None
    current_paras = []
    current_lines = []

    def flush_para():
        if current_lines:
            para = " ".join(l.strip() for l in current_lines if l.strip())
            if para:
                current_paras.append(para)
            current_lines.clear()

    def flush_section():
        nonlocal current_section_title, current_paras
        flush_para()
        if current_paras or current_section_title:
            sections.append({
                "title": current_section_title,
                "paragraphs": list(current_paras),
            })
        current_paras.clear()
        current_section_title = None

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped in SECTION_TITLES:
            flush_para()
            flush_section()
            current_section_title = stripped
            continue

        if not stripped:
            flush_para()
            continue

        if current_lines:
            prev_text = " ".join(l.strip() for l in current_lines).rstrip()
            if prev_text and prev_text[-1] in ".!?" and stripped and stripped[0].isupper():
                flush_para()

        current_lines.append(line)

    flush_para()
    flush_section()

    return sections


def parse_kr_md(path):
    """Parse MoLG_KR.md into sections."""
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()

    sections = []
    current_title_en = None
    current_title_kr = None
    current_paras = []
    current_lines = []
    in_header = True

    def flush_para():
        if current_lines:
            para = " ".join(l.strip() for l in current_lines if l.strip())
            if para:
                current_paras.append(para)
            current_lines.clear()

    def flush_section():
        nonlocal current_title_en, current_title_kr, current_paras
        flush_para()
        if current_paras or current_title_en:
            sections.append({
                "title_en": current_title_en,
                "title_kr": current_title_kr,
                "paragraphs": list(current_paras),
            })
        current_paras.clear()
        current_title_en = None
        current_title_kr = None

    i = 0
    while i < len(lines):
        raw_line = lines[i]
        line = raw_line.rstrip()
        stripped = line.strip()

        if in_header:
            if stripped.startswith("---") or stripped.startswith(">") or stripped.startswith("# "):
                i += 1
                continue
            elif not stripped:
                i += 1
                continue
            else:
                in_header = False

        if stripped.startswith("## ") and not stripped.startswith("### "):
            flush_para()
            flush_section()
            current_title_en = stripped[3:].strip()
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].strip().startswith("### "):
                current_title_kr = lines[j].strip()[4:].strip()
                i = j + 1
            else:
                current_title_kr = current_title_en
                i += 1
            continue

        if re.match(r'^\d+\.\s', stripped):
            current_lines.append(re.sub(r'^\d+\.\s+', '', stripped))
            i += 1
            continue

        # Skip date lines (e.g. "2024년 10월")
        if re.match(r'^\d{4}년\s+\d+월', stripped):
            flush_para()
            i += 1
            continue

        if not stripped:
            flush_para()
            i += 1
            continue

        clean = stripped
        clean = re.sub(r'^\*\*(.+?)\*\*\s*', r'\1 ', clean)
        clean = re.sub(r'^-\s+', '', clean)
        clean = re.sub(r'<sup>\d+</sup>', '', clean)
        if clean.startswith("> "):
            clean = clean[2:]
        if clean.startswith(">"):
            clean = clean[1:].strip()

        if clean.strip():
            current_lines.append(clean)
        i += 1

    flush_para()
    flush_section()

    return sections


# ---------------------------------------------------------------------------
# Paragraph-level bullet detection
# ---------------------------------------------------------------------------

def is_list_paragraph(text):
    if "Biology and physical health" in text and "Neuroscience" in text:
        return True
    if re.match(r'^\d+\.\s+생물학', text):
        return True
    if "생물학과 신체 건강" in text and "신경과학과 정신 건강" in text:
        return True
    return False


# ---------------------------------------------------------------------------
# Build HTML for a paragraph pair
# ---------------------------------------------------------------------------

def build_birow(sid_base, en_para, kr_para, model, stats):
    """Build a single bi-row for a paragraph pair."""
    if is_list_paragraph(en_para):
        en_html = esc(en_para)
        kr_html = esc(kr_para)
        en_cell = f'<span class="sent" data-sid="{sid_base}">{en_html}</span>'
        kr_cell = f'<span class="sent" data-sid="{sid_base}">{kr_html}</span>'
        stats["para_level"] += 1
        stats["bi_rows"] += 1
        stats["sids"].add(sid_base)
        return (
            f'<div class="bi-row">\n'
            f'  <div class="cell en"><p>{en_cell}</p></div>\n'
            f'  <div class="cell kr"><p>{kr_cell}</p></div>\n'
            f'</div>\n'
        )

    en_sents = split_en_sentences(en_para)
    kr_sents = split_kr_sentences(kr_para)

    if not en_sents:
        en_sents = [en_para]
    if not kr_sents:
        kr_sents = [kr_para]

    m, k = len(en_sents), len(kr_sents)

    # Paragraph-level fallback when sentence counts diverge too much
    ratio = m / k if k > 0 else 99.0
    use_fallback = abs(m - k) >= 3 and (ratio < 0.4 or ratio > 2.5)

    if use_fallback:
        en_parts = []
        for idx, s in enumerate(en_sents):
            prefix = " " if idx > 0 else ""
            en_parts.append(
                f'<span class="sent" data-sid="{sid_base}">{prefix}{esc(s)}</span>'
            )
        kr_parts = []
        for idx, s in enumerate(kr_sents):
            prefix = " " if idx > 0 else ""
            kr_parts.append(
                f'<span class="sent" data-sid="{sid_base}">{prefix}{esc(s)}</span>'
            )
        stats["para_level"] += 1
        stats["bi_rows"] += 1
        stats["sids"].add(sid_base)
        print(f"  FALLBACK {sid_base}: EN={m} KR={k} ratio={ratio:.2f}", file=sys.stderr)
        return (
            f'<div class="bi-row">\n'
            f'  <div class="cell en"><p>{"".join(en_parts)}</p></div>\n'
            f'  <div class="cell kr"><p>{"".join(kr_parts)}</p></div>\n'
            f'</div>\n'
        )

    # Try LaBSE first; fall back to positional alignment
    alignments = None
    if model is not None:
        try:
            alignments = labse_align(en_sents, kr_sents, model)
        except Exception as e:
            print(f"  LaBSE error at {sid_base}: {e}, using positional", file=sys.stderr)

    if not alignments:
        alignments = positional_align(en_sents, kr_sents)
        stats["positional"] += 1

    # Build SID map
    en_sid_map = {}
    kr_sid_map = {}

    sent_counter = 0
    for en_idxs, kr_idxs in alignments:
        for ei in en_idxs:
            if ei not in en_sid_map:
                en_sid_map[ei] = f"{sid_base}s{sent_counter}"
                sent_counter += 1

    for ei in range(m):
        if ei not in en_sid_map:
            en_sid_map[ei] = f"{sid_base}s{sent_counter}"
            sent_counter += 1

    for en_idxs, kr_idxs in alignments:
        target_sid = en_sid_map[en_idxs[0]]
        for ki in kr_idxs:
            kr_sid_map[ki] = target_sid

    for ki in range(k):
        if ki not in kr_sid_map:
            nearest = min(range(m), key=lambda x: abs(x * k / m - ki))
            kr_sid_map[ki] = en_sid_map.get(nearest, sid_base)

    # Build EN HTML
    en_parts = []
    for idx in range(m):
        sid = en_sid_map[idx]
        prefix = " " if idx > 0 else ""
        en_parts.append(
            f'<span class="sent" data-sid="{sid}">{prefix}{esc(en_sents[idx])}</span>'
        )
        stats["sids"].add(sid)

    # Build KR HTML
    kr_parts = []
    for idx in range(k):
        sid = kr_sid_map[idx]
        prefix = " " if idx > 0 else ""
        kr_parts.append(
            f'<span class="sent" data-sid="{sid}">{prefix}{esc(kr_sents[idx])}</span>'
        )

    stats["sent_level"] += 1
    stats["bi_rows"] += 1

    return (
        f'<div class="bi-row">\n'
        f'  <div class="cell en"><p>{"".join(en_parts)}</p></div>\n'
        f'  <div class="cell kr"><p>{"".join(kr_parts)}</p></div>\n'
        f'</div>\n'
    )


# ---------------------------------------------------------------------------
# Section mapping
# ---------------------------------------------------------------------------

EN_TO_KR_SECTION = {
    None: ("Machines of Loving Grace", "\uc0ac\ub791\uc758 \uc740\ucd1d\uc744 \ubca0\ud478\ub294 \uae30\uacc4\ub4e4"),
    "Basic assumptions and framework": ("Basic assumptions and framework", "\uae30\ubcf8 \uac00\uc815\uacfc \ud504\ub808\uc784\uc6cc\ud06c"),
    "1. Biology and health": ("Biology and physical health", "\uc0dd\ubb3c\ud559\uacfc \uc2e0\uccb4 \uac74\uac15"),
    "2. Neuroscience and mind": ("Neuroscience and mental health", "\uc2e0\uacbd\uacfc\ud559\uacfc \uc815\uc2e0 \uac74\uac15"),
    "3. Economic development and poverty": ("Economic development and poverty", "\uacbd\uc81c \ubc1c\uc804\uacfc \ube48\uacf5"),
    "4. Peace and governance": ("Peace and governance", "\ud3c9\ud654\uc640 \uac70\ubc84\ub10c\uc2a4"),
    "5. Work and meaning": ("Work and meaning", "\uc77c\uacfc \uc758\ubbf8"),
    "Taking stock": ("Taking stock", "\uacb0\uc0b0"),
    "Footnotes": ("Footnotes", "\uac01\uc8fc"),
}


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build_molg_html(model):
    """Parse source files, align, and generate MoLG HTML content."""
    print("Parsing EN markdown...", file=sys.stderr)
    en_sections = parse_en_md(EN_FILE)
    print(f"  {len(en_sections)} EN sections found", file=sys.stderr)
    for s in en_sections:
        print(f"    [{s['title']}] {len(s['paragraphs'])} paragraphs", file=sys.stderr)

    print("Parsing KR markdown...", file=sys.stderr)
    kr_sections = parse_kr_md(KR_FILE)
    print(f"  {len(kr_sections)} KR sections found", file=sys.stderr)
    for s in kr_sections:
        print(f"    [{s.get('title_en')}] / [{s.get('title_kr')}] {len(s['paragraphs'])} paragraphs", file=sys.stderr)

    kr_by_title = {}
    for s in kr_sections:
        te = s.get("title_en", "")
        kr_by_title[te] = s

    stats = {
        "bi_rows": 0,
        "sent_level": 0,
        "para_level": 0,
        "positional": 0,
        "sids": set(),
    }

    html_parts = []

    for sec_idx, en_sec in enumerate(en_sections):
        en_title = en_sec["title"]
        en_paras = en_sec["paragraphs"]

        if en_title == "Footnotes":
            continue

        kr_lookup_key = en_title
        if en_title is None:
            kr_lookup_key = "How AI Could Transform the World for the Better"

        kr_sec = kr_by_title.get(kr_lookup_key)
        if kr_sec is None:
            for key in kr_by_title:
                if key and en_title and (key in en_title or en_title in key):
                    kr_sec = kr_by_title[key]
                    break
        if kr_sec is None:
            print(f"  WARNING: No KR section found for [{en_title}]", file=sys.stderr)
            kr_paras = [""] * len(en_paras)
            kr_title_kr = en_title or ""
        else:
            kr_paras = kr_sec["paragraphs"]
            kr_title_kr = kr_sec.get("title_kr", "")

        en_display, kr_display = EN_TO_KR_SECTION.get(en_title, (en_title or "", kr_title_kr or ""))

        if sec_idx == 0:
            html_parts.append(
                f'<div class="section-divider">Machines of Loving Grace / \uc0ac\ub791\uc758 \uc740\ucd1d\uc744 \ubca0\ud478\ub294 \uae30\uacc4\ub4e4</div>\n'
            )
        else:
            html_parts.append(
                f'<div class="section-divider">{esc(en_display)} / {esc(kr_display)}</div>\n'
            )
            html_parts.append(
                f'<div class="bi-row">\n'
                f'  <div class="cell en"><h2>{esc(en_display)}</h2></div>\n'
                f'  <div class="cell kr"><h2>{esc(kr_display)}</h2></div>\n'
                f'</div>\n'
            )

        max_paras = max(len(en_paras), len(kr_paras)) if (en_paras or kr_paras) else 0
        en_paras_padded = en_paras + [""] * (max_paras - len(en_paras))
        kr_paras_padded = kr_paras + [""] * (max_paras - len(kr_paras))

        print(f"  Sec [{en_title}]: EN={len(en_paras)} KR={len(kr_paras)} paras", file=sys.stderr)

        for para_idx, (en_p, kr_p) in enumerate(zip(en_paras_padded, kr_paras_padded)):
            sid_base = f"molg-s{sec_idx}p{para_idx}"
            if not en_p.strip() and not kr_p.strip():
                continue
            if not en_p.strip():
                en_p = kr_p
            if not kr_p.strip():
                kr_p = en_p

            birow = build_birow(sid_base, en_p, kr_p, model, stats)
            html_parts.append(birow)

    return "".join(html_parts), stats


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_output(html_content, stats):
    """Verify the generated HTML for SID correctness.

    Rules:
      - Each EN cell SID must appear exactly once in EN cells (1 span per SID).
      - Each KR cell SID must be a subset of EN cell SIDs.
      - No orphan SIDs (KR SID with no matching EN SID).
    """
    import re
    from collections import Counter

    # Extract SIDs from EN and KR cells separately
    # Split by bi-row, then by cell
    bi_row_re = re.compile(
        r'<div class="cell en">(.*?)</div>\s*<div class="cell kr">(.*?)</div>',
        re.DOTALL,
    )

    en_sids_all = []
    kr_sids_all = []
    for m in bi_row_re.finditer(html_content):
        en_cell, kr_cell = m.group(1), m.group(2)
        en_sids_all.extend(re.findall(r'data-sid="([^"]+)"', en_cell))
        kr_sids_all.extend(re.findall(r'data-sid="([^"]+)"', kr_cell))

    en_counts = Counter(en_sids_all)
    kr_counts = Counter(kr_sids_all)

    en_sid_set = set(en_counts)
    kr_sid_set = set(kr_counts)

    # EN: sentence-level SIDs (molg-sXpYsN) must appear exactly once
    # Paragraph-level SIDs (molg-sXpY, no sN suffix) may appear multiple times (fallback)
    en_sent_sids = {sid for sid in en_sid_set if re.search(r's\d+$', sid)}
    en_para_sids = {sid for sid in en_sid_set if not re.search(r's\d+$', sid)}
    en_dupes = [(sid, cnt) for sid, cnt in en_counts.items()
                if cnt > 1 and sid in en_sent_sids]
    # KR: each SID must exist in EN
    kr_orphans = [sid for sid in kr_sid_set if sid not in en_sid_set]

    print(f"\n--- Verification ---", file=sys.stderr)
    print(f"  Unique EN SIDs: {len(en_sid_set)}", file=sys.stderr)
    print(f"  Unique KR SIDs: {len(kr_sid_set)}", file=sys.stderr)
    if en_dupes:
        print(f"  WARN: EN SIDs appearing >1x: {len(en_dupes)}", file=sys.stderr)
        for sid, cnt in sorted(en_dupes, key=lambda x: -x[1])[:10]:
            print(f"    {sid}: {cnt}x", file=sys.stderr)
    if kr_orphans:
        print(f"  WARN: KR SIDs not in EN: {len(kr_orphans)}", file=sys.stderr)
        for sid in kr_orphans[:10]:
            print(f"    {sid}", file=sys.stderr)

    # Sentence-level vs paragraph-level SIDs
    sent_level = [s for s in en_sid_set if re.search(r's\d+$', s)]
    para_level = [s for s in en_sid_set if not re.search(r's\d+$', s)]
    print(f"  EN sentence-level SIDs: {len(sent_level)}", file=sys.stderr)
    print(f"  EN paragraph-level SIDs: {len(para_level)}", file=sys.stderr)

    # Total KR spans per EN SID (to detect extreme 1:N mappings)
    extreme = [(sid, kr_counts[sid]) for sid in en_sid_set if kr_counts.get(sid, 0) > 5]
    if extreme:
        print(f"  INFO: EN SIDs with >5 KR spans ({len(extreme)} total - likely para fallback):",
              file=sys.stderr)
        for sid, cnt in sorted(extreme, key=lambda x: -x[1])[:5]:
            print(f"    {sid}: {cnt} KR spans", file=sys.stderr)

    ok = len(en_dupes) == 0 and len(kr_orphans) == 0
    print(f"  Result: {'PASS' if ok else 'FAIL'}", file=sys.stderr)
    return ok


# ---------------------------------------------------------------------------
# Inject into index.html
# ---------------------------------------------------------------------------

def inject_into_index(new_content):
    """Replace the MoLG section content in index.html."""
    html = INDEX_FILE.read_text(encoding="utf-8")

    container_start = html.find('<div class="container">', html.find('id="reading-2"'))
    if container_start == -1:
        print("ERROR: Could not find reading-2 container", file=sys.stderr)
        return False

    container_end = html.find("</div><!-- /container -->", container_start)
    if container_end == -1:
        print("ERROR: Could not find container end marker", file=sys.stderr)
        return False

    new_html = (
        html[:container_start]
        + '<div class="container">\n'
        + new_content
        + '\n</div><!-- /container -->'
        + html[container_end + len("</div><!-- /container -->"):]
    )

    INDEX_FILE.write_text(new_html, encoding="utf-8")
    print(f"  Wrote {len(new_html)} bytes to {INDEX_FILE.name}", file=sys.stderr)
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("Loading LaBSE model...", file=sys.stderr)
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("sentence-transformers/LaBSE")
        print("  Model loaded OK.", file=sys.stderr)
    except Exception as e:
        print(f"  WARNING: Could not load LaBSE: {e}", file=sys.stderr)
        print("  Will use positional alignment only.", file=sys.stderr)
        model = None

    print("Building MoLG HTML...", file=sys.stderr)
    new_content, stats = build_molg_html(model)

    print("\n--- Build Stats ---", file=sys.stderr)
    print(f"  Total bi-rows: {stats['bi_rows']}", file=sys.stderr)
    print(f"  LaBSE sentence-level: {stats['sent_level']}", file=sys.stderr)
    print(f"  Positional alignment: {stats['positional']}", file=sys.stderr)
    print(f"  Para-level fallback: {stats['para_level']}", file=sys.stderr)
    print(f"  Unique SIDs: {len(stats['sids'])}", file=sys.stderr)

    ok = verify_output(new_content, stats)
    if not ok:
        print("\nERROR: Verification FAILED. Not writing to index.html.", file=sys.stderr)
        sys.exit(1)

    print("\nInjecting into index.html...", file=sys.stderr)
    success = inject_into_index(new_content)

    if success:
        print("Done.", file=sys.stderr)
        print(f"\nSummary:")
        print(f"  Total bi-rows: {stats['bi_rows']}")
        print(f"  Unique SIDs: {len(stats['sids'])}")
        print(f"  Sentence-level: {stats['sent_level'] + stats['positional']}")
        print(f"  Para-level fallbacks: {stats['para_level']}")
    else:
        print("FAILED to inject into index.html", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
