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
    "e.g", "i.e", "vs",
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
            if ch == "." and i + 1 < n and text[i + 1] == "." :
                current.append(ch)
                i += 1
                continue

            # Check decimal: digit.digit
            if ch == "." and i > 0 and text[i - 1].isdigit() and i + 1 < n and text[i + 1].isdigit():
                current.append(ch)
                i += 1
                continue

            # Check footnote marker: digit at end of word followed by .
            # e.g. "...word1." where 1 is a footnote - treat as part of word
            # Already handled since we're looking at the '.' after digit

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
                # End of text
                sent = "".join(current).strip()
                if sent:
                    sentences.append(sent)
                current = []
                i = end_idx
                continue

            next_ch = text[j]

            # Check if this is just an abbreviation
            # Get the word before the period
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
                # Skip whitespace
                while i < n and text[i] in " \t":
                    i += 1
                continue

            i = end_idx
            continue

        current.append(ch)
        i += 1

    # Remaining
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

    sentences = []
    # Split on Korean sentence endings: 다|요|죠|군|네 followed by [.!?] + whitespace/end
    # Also split on . + space + Korean char or uppercase
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

    # If no splits happened, return the whole text
    if not result:
        return [text.strip()] if text.strip() else []
    return result


# ---------------------------------------------------------------------------
# LaBSE alignment
# ---------------------------------------------------------------------------

def labse_align(en_sents, kr_sents, model):
    """DP alignment with 1:1, 1:2, 2:1 transitions.
    Returns list of (en_indices_tuple, kr_indices_tuple) pairs.
    """
    import numpy as np

    if not en_sents or not kr_sents:
        return []

    en_emb = model.encode(en_sents, normalize_embeddings=True, show_progress_bar=False)
    kr_emb = model.encode(kr_sents, normalize_embeddings=True, show_progress_bar=False)

    m = len(en_sents)
    k = len(kr_sents)

    sim = np.dot(en_emb, kr_emb.T)  # (m, k)

    NEG_INF = float("-inf")
    # dp[i][j] = best score aligning en[:i] with kr[:j]
    dp = [[NEG_INF] * (k + 1) for _ in range(m + 1)]
    # back[i][j] = (prev_i, prev_j) transition
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

    # Backtrack
    if dp[m][k] == NEG_INF:
        # Fallback: 1:1 mapping with truncation
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


# ---------------------------------------------------------------------------
# HTML escaping helper
# ---------------------------------------------------------------------------

def esc(text):
    """HTML escape for attribute-unsafe characters."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


# ---------------------------------------------------------------------------
# Markdown parsing
# ---------------------------------------------------------------------------

def parse_en_md(path):
    """Parse MoLG_original.md into sections.

    Returns list of:
        {"title": str or None, "paragraphs": [str, ...]}
    Section 0 = Intro (no heading).
    """
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()

    # Known section titles (in order of appearance)
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

        # Check if this line is a section title
        stripped = line.strip()
        if stripped in SECTION_TITLES:
            flush_para()
            flush_section()
            current_section_title = stripped
            continue

        # Blank line = paragraph break
        if not stripped:
            flush_para()
            continue

        # In the EN file, some sections have multiple standalone paragraphs
        # without blank lines between them. Detect a new paragraph start when:
        # 1. We already have content in current_lines
        # 2. The current line is a complete standalone paragraph (ends with . ! ?)
        #    and starts with capital letter (or number like "Yet", "In", "By", etc.)
        # This handles the "Maximize leverage." and "Avoid..." bullet blocks.
        if current_lines:
            # Check if the PREVIOUS accumulated content ended a complete sentence
            # by looking at the combined text so far
            prev_text = " ".join(l.strip() for l in current_lines).rstrip()
            # If previous text ends with sentence-ending punctuation and this line
            # starts a new clear paragraph, break it.
            if prev_text and prev_text[-1] in ".!?" and stripped and stripped[0].isupper():
                flush_para()

        current_lines.append(line)

    flush_para()
    flush_section()

    return sections


def parse_kr_md(path):
    """Parse MoLG_KR.md into sections.

    Returns list of:
        {"title_en": str, "title_kr": str, "paragraphs": [str, ...]}
    """
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()

    sections = []
    current_title_en = None
    current_title_kr = None
    current_paras = []
    current_lines = []
    in_header = True  # skip metadata at top

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

        # Skip metadata header (lines starting with #, >, ---)
        if in_header:
            if stripped.startswith("---") or stripped.startswith(">") or stripped.startswith("# "):
                i += 1
                continue
            elif not stripped:
                i += 1
                continue
            else:
                in_header = False

        # ## Section header (English title)
        if stripped.startswith("## ") and not stripped.startswith("### "):
            flush_para()
            flush_section()
            current_title_en = stripped[3:].strip()
            # Look for ### Korean subheader on next non-blank line
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

        # Skip list markers in numbered lists (1. 2. 3. etc at line start)
        # but keep the content
        if re.match(r'^\d+\.\s', stripped):
            # It's a numbered list item - keep as paragraph line
            current_lines.append(re.sub(r'^\d+\.\s+', '', stripped))
            i += 1
            continue

        # Skip markdown bold markers (**text**)
        # Keep content
        if not stripped:
            flush_para()
            i += 1
            continue

        # Remove markdown formatting from line for storage
        clean = stripped
        # Remove leading ** bold markers (like **영향력 극대화.**)
        clean = re.sub(r'^\*\*(.+?)\*\*\s*', r'\1 ', clean)
        # Remove - list prefix
        clean = re.sub(r'^-\s+', '', clean)
        # Remove superscript markup <sup>N</sup>
        clean = re.sub(r'<sup>\d+</sup>', '', clean)
        # Remove leading > blockquote
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
    """Detect if a paragraph is a bullet/list (one item per line conceptually).
    These are paragraphs where multiple short items are joined, like
    'Biology and physical health\nNeuroscience...'
    """
    # If it's the five categories list
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
    """Build a single bi-row for a paragraph pair.

    sid_base: e.g. "molg-s0p0"
    en_para: raw EN text
    kr_para: raw KR text
    model: LaBSE model or None
    stats: dict to accumulate counts

    Returns HTML string.
    """
    # Special case: list paragraph - don't sentence split
    if is_list_paragraph(en_para):
        en_html = esc(en_para)
        kr_html = esc(kr_para)
        en_cell = f'<span class="sent" data-sid="{sid_base}">{en_html}</span>'
        kr_cell = f'<span class="sent" data-sid="{sid_base}">{kr_html}</span>'
        stats["para_level"] += 1
        stats["bi_rows"] += 1
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

    # Fallback condition: diff >= 3 and ratio < 0.3 or > 3.0
    ratio = m / k if k > 0 else 99
    use_fallback = abs(m - k) >= 3 and (ratio < 0.3 or ratio > 3.0)

    if use_fallback or model is None:
        # Paragraph-level fallback: all sentences share the base SID
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
        return (
            f'<div class="bi-row">\n'
            f'  <div class="cell en"><p>{"".join(en_parts)}</p></div>\n'
            f'  <div class="cell kr"><p>{"".join(kr_parts)}</p></div>\n'
            f'</div>\n'
        )

    # LaBSE alignment
    try:
        alignments = labse_align(en_sents, kr_sents, model)
    except Exception as e:
        print(f"  LaBSE error: {e}, falling back to para-level", file=sys.stderr)
        alignments = None

    if not alignments:
        # Fallback
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
        return (
            f'<div class="bi-row">\n'
            f'  <div class="cell en"><p>{"".join(en_parts)}</p></div>\n'
            f'  <div class="cell kr"><p>{"".join(kr_parts)}</p></div>\n'
            f'</div>\n'
        )

    # Build SID map: en_idx -> sid, kr_idx -> sid
    # EN sentences get sequential SIDs: sid_base + "s0", "s1", ...
    # For 2:1 transitions, second EN gets its own SID but KR maps to first EN's SID
    en_sid_map = {}  # en_idx -> sid
    kr_sid_map = {}  # kr_idx -> sid

    # First, assign SIDs to EN sentences in order
    sent_counter = 0
    for en_idxs, kr_idxs in alignments:
        for ei in en_idxs:
            if ei not in en_sid_map:
                en_sid_map[ei] = f"{sid_base}s{sent_counter}"
                sent_counter += 1

    # For any EN sentences not covered (shouldn't happen but be safe)
    for ei in range(m):
        if ei not in en_sid_map:
            en_sid_map[ei] = f"{sid_base}s{sent_counter}"
            sent_counter += 1

    # Assign KR SIDs based on alignment
    for en_idxs, kr_idxs in alignments:
        # KR gets the first EN sentence's SID
        target_sid = en_sid_map[en_idxs[0]]
        for ki in kr_idxs:
            kr_sid_map[ki] = target_sid

    # For any KR sentences not covered
    for ki in range(k):
        if ki not in kr_sid_map:
            # Try to find nearest EN sentence
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
# Section mapping: EN sections -> KR sections
# ---------------------------------------------------------------------------

EN_TO_KR_SECTION = {
    None: ("Machines of Loving Grace", "사랑의 은총을 베푸는 기계들"),
    "Basic assumptions and framework": ("Basic assumptions and framework", "기본 가정과 프레임워크"),
    "1. Biology and health": ("Biology and physical health", "생물학과 신체 건강"),
    "2. Neuroscience and mind": ("Neuroscience and mental health", "신경과학과 정신 건강"),
    "3. Economic development and poverty": ("Economic development and poverty", "경제 발전과 빈곤"),
    "4. Peace and governance": ("Peace and governance", "평화와 거버넌스"),
    "5. Work and meaning": ("Work and meaning", "일과 의미"),
    "Taking stock": ("Taking stock", "결산"),
    "Footnotes": ("Footnotes", "각주"),
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

    # Build KR section lookup by EN title
    kr_by_title = {}
    for s in kr_sections:
        te = s.get("title_en", "")
        kr_by_title[te] = s

    stats = {
        "bi_rows": 0,
        "sent_level": 0,
        "para_level": 0,
        "sids": set(),
    }

    html_parts = []

    # Section 0 (intro) gets the main section-divider (already exists in index.html)
    # We need to generate from the first section divider onward

    for sec_idx, en_sec in enumerate(en_sections):
        en_title = en_sec["title"]
        en_paras = en_sec["paragraphs"]

        # Skip Footnotes section
        if en_title == "Footnotes":
            continue

        # Get KR section
        # Map EN title to KR title lookup key
        kr_lookup_key = en_title
        if en_title is None:
            # Intro: KR file has this under "How AI Could Transform the World for the Better"
            kr_lookup_key = "How AI Could Transform the World for the Better"
        elif en_title == "1. Biology and health":
            kr_lookup_key = "1. Biology and health"
        elif en_title == "2. Neuroscience and mind":
            kr_lookup_key = "2. Neuroscience and mind"
        elif en_title == "3. Economic development and poverty":
            kr_lookup_key = "3. Economic development and poverty"
        elif en_title == "4. Peace and governance":
            kr_lookup_key = "4. Peace and governance"
        elif en_title == "5. Work and meaning":
            kr_lookup_key = "5. Work and meaning"

        kr_sec = kr_by_title.get(kr_lookup_key)
        if kr_sec is None:
            # Try partial match
            for key in kr_by_title:
                if key and en_title and (key in en_title or en_title in key):
                    kr_sec = kr_by_title[key]
                    break
        if kr_sec is None:
            print(f"  WARNING: No KR section found for [{en_title}]", file=sys.stderr)
            kr_paras = [""] * len(en_paras)
            kr_title_en = en_title or ""
            kr_title_kr = en_title or ""
        else:
            kr_paras = kr_sec["paragraphs"]
            kr_title_en = kr_sec.get("title_en", en_title or "")
            kr_title_kr = kr_sec.get("title_kr", "")

        # Get EN/KR display titles
        en_display, kr_display = EN_TO_KR_SECTION.get(en_title, (en_title or "", kr_title_kr or ""))

        # Section divider (skip for intro section 0 - it's already in the template)
        if sec_idx == 0:
            # The intro section: emit the main divider + first bi-row (title block)
            html_parts.append(
                f'<div class="section-divider">Machines of Loving Grace / 사랑의 은총을 베푸는 기계들</div>\n'
            )
        else:
            html_parts.append(
                f'<div class="section-divider">{esc(en_display)} / {esc(kr_display)}</div>\n'
            )
            # Heading bi-row for non-intro sections
            html_parts.append(
                f'<div class="bi-row">\n'
                f'  <div class="cell en"><h2>{esc(en_display)}</h2></div>\n'
                f'  <div class="cell kr"><h2>{esc(kr_display)}</h2></div>\n'
                f'</div>\n'
            )

        # Align paragraphs
        # Pad shorter list with empty strings
        max_paras = max(len(en_paras), len(kr_paras))
        en_paras_padded = en_paras + [""] * (max_paras - len(en_paras))
        kr_paras_padded = kr_paras + [""] * (max_paras - len(kr_paras))

        print(f"  Section [{en_title}]: {len(en_paras)} EN, {len(kr_paras)} KR paragraphs", file=sys.stderr)

        for para_idx, (en_p, kr_p) in enumerate(zip(en_paras_padded, kr_paras_padded)):
            sid_base = f"molg-s{sec_idx}p{para_idx}"
            if not en_p.strip() and not kr_p.strip():
                continue

            # If one side is empty, use fallback
            if not en_p.strip():
                en_p = kr_p  # use KR as placeholder
            if not kr_p.strip():
                kr_p = en_p  # use EN as placeholder

            birow = build_birow(sid_base, en_p, kr_p, model, stats)
            html_parts.append(birow)

    return "".join(html_parts), stats


# ---------------------------------------------------------------------------
# Inject into index.html
# ---------------------------------------------------------------------------

def inject_into_index(new_content):
    """Replace the MoLG section content in index.html."""
    html = INDEX_FILE.read_text(encoding="utf-8")

    # Find reading-2 container start
    container_start = html.find("<div class=\"container\">", html.find('<div id="reading-2"'))
    if container_start == -1:
        print("ERROR: Could not find reading-2 container", file=sys.stderr)
        return False

    # Find container end
    container_end = html.find("</div><!-- /container -->", container_start)
    if container_end == -1:
        print("ERROR: Could not find container end", file=sys.stderr)
        return False

    # Find lang-bar end (what comes right before our content)
    lang_bar_end = html.find("</div>\n\n<div class=\"container\">", html.find('<div id="reading-2"'))
    # Actually just replace from <div class="container"> to </div><!-- /container -->

    # The replacement: <div class="container">  + new_content + \n</div><!-- /container -->
    new_html = (
        html[:container_start]
        + '<div class="container">\n'
        + new_content
        + '\n</div><!-- /container -->'
        + html[container_end + len("</div><!-- /container -->"):]
    )

    INDEX_FILE.write_text(new_html, encoding="utf-8")
    print(f"Wrote {len(new_html)} bytes to {INDEX_FILE}", file=sys.stderr)
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("Loading LaBSE model...", file=sys.stderr)
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("sentence-transformers/LaBSE")
        print("  Model loaded.", file=sys.stderr)
    except Exception as e:
        print(f"  WARNING: Could not load LaBSE: {e}", file=sys.stderr)
        print("  Falling back to paragraph-level alignment only.", file=sys.stderr)
        model = None

    print("Building MoLG HTML...", file=sys.stderr)
    new_content, stats = build_molg_html(model)

    print("\n--- Stats ---", file=sys.stderr)
    print(f"  Total bi-rows: {stats['bi_rows']}", file=sys.stderr)
    print(f"  Sentence-level: {stats['sent_level']}", file=sys.stderr)
    print(f"  Paragraph-level fallback: {stats['para_level']}", file=sys.stderr)
    print(f"  Unique SIDs: {len(stats['sids'])}", file=sys.stderr)

    print("\nInjecting into index.html...", file=sys.stderr)
    success = inject_into_index(new_content)

    if success:
        print("Done.", file=sys.stderr)
        print(f"\nSummary:")
        print(f"  Total bi-rows: {stats['bi_rows']}")
        print(f"  Unique SIDs: {len(stats['sids'])}")
        print(f"  Sentence-level bi-rows: {stats['sent_level']}")
        print(f"  Paragraph-level fallbacks: {stats['para_level']}")
    else:
        print("FAILED to inject into index.html", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
