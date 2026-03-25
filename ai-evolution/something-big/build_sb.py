# build_sb.py - Rebuild index.html with proper sentence-level matching
# Working dir: C:/Users/dizib/Projects/KAIST-CaseHub/ai-evolution/something-big/

import re
import os

BASE = os.path.dirname(os.path.abspath(__file__))
EN_PATH = os.path.join(BASE, "SomethingBig_EN.md")
KR_PATH = os.path.join(BASE, "SomethingBig_KR.md")
HTML_PATH = os.path.join(BASE, "index.html")

# ---------------------------------------------------------------------------
# HTML escaping
# ---------------------------------------------------------------------------
def esc(text):
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    return text

# ---------------------------------------------------------------------------
# Sentence splitting - English
# ---------------------------------------------------------------------------
EN_ABBREVS = set([
    "Mr", "Mrs", "Ms", "Dr", "Jr", "Sr", "Inc", "Ltd", "Corp", "Co",
    "vs", "etc", "Gov", "Prof", "Vol", "No",
    "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    "St", "Ave", "Blvd",
])

def split_sentences_en(text):
    """Character-level sentence splitter for English."""
    text = text.strip()
    if not text:
        return []

    sentences = []
    current = []
    i = 0
    paren_depth = 0

    while i < len(text):
        ch = text[i]

        if ch == "(":
            paren_depth += 1
            current.append(ch)
            i += 1
            continue
        if ch == ")":
            paren_depth = max(0, paren_depth - 1)
            current.append(ch)
            i += 1
            continue

        if ch in ".!?" and paren_depth == 0:
            # Absorb closing quotes after terminator
            j = i + 1
            while j < len(text) and text[j] in '"\'':
                j += 1
            terminator = text[i:j]  # e.g. '.' or '."'

            # Find next non-whitespace char
            k = j
            while k < len(text) and text[k] in " \t\n\r":
                k += 1

            # End of text -> sentence boundary
            if k >= len(text):
                current.append(terminator)
                sentences.append("".join(current).strip())
                current = []
                i = j
                continue

            next_ch = text[k]

            # Check if it's a decimal: digit.digit
            if ch == ".":
                if i > 0 and text[i-1].isdigit() and k < len(text) and text[k].isdigit():
                    current.append(ch)
                    i += 1
                    continue

                # Check abbreviation: word ending before the dot
                # collect word before the dot
                word_start = i - 1
                while word_start >= 0 and text[word_start].isalpha():
                    word_start -= 1
                word_before = text[word_start+1:i]

                if word_before in EN_ABBREVS:
                    current.append(ch)
                    i += 1
                    continue

                # Single capital initial: one uppercase letter before dot
                if len(word_before) == 1 and word_before.isupper():
                    current.append(ch)
                    i += 1
                    continue

            # If next non-whitespace is uppercase or end -> sentence boundary
            if next_ch.isupper() or next_ch in '"\'':
                current.append(terminator)
                sentences.append("".join(current).strip())
                current = []
                i = j
                continue
            else:
                current.append(terminator)
                i = j
                continue
        else:
            current.append(ch)
            i += 1

    remainder = "".join(current).strip()
    if remainder:
        sentences.append(remainder)

    return [s for s in sentences if s]


# ---------------------------------------------------------------------------
# Sentence splitting - Korean
# ---------------------------------------------------------------------------
def split_sentences_kr(text):
    """Split Korean sentences at common endings followed by whitespace or end.

    Handles:
    - 다./요./죠. + (optional quote) + (whitespace or end)
    - period + space + Korean/uppercase next char (for category-label sentences)
    """
    text = text.strip()
    if not text:
        return []

    sentences = []
    current_chars = []
    i = 0
    paren_depth = 0

    while i < len(text):
        ch = text[i]

        if ch == "(":
            paren_depth += 1
            current_chars.append(ch)
            i += 1
            continue
        if ch == ")":
            paren_depth = max(0, paren_depth - 1)
            current_chars.append(ch)
            i += 1
            continue

        if paren_depth > 0:
            current_chars.append(ch)
            i += 1
            continue

        if ch in ".?!" and i > 0:
            # absorb closing quotes after terminator
            j = i + 1
            while j < len(text) and text[j] in '"\'':
                j += 1
            # skip whitespace
            k = j
            while k < len(text) and text[k] in " \t":
                k += 1

            next_ch = text[k] if k < len(text) else None

            prev = text[i-1]

            # Case 1: previous char is a Korean sentence-ending syllable
            if prev in "다요죠":
                current_chars.append(text[i:j])
                sentences.append("".join(current_chars).strip())
                current_chars = []
                i = j
                continue

            # Case 2: period + space/end + next is Korean char or uppercase
            # This handles "재무 분석. 재무 모델..." style splits
            if ch == "." and next_ch is not None:
                is_next_kr = '\uAC00' <= next_ch <= '\uD7A3'
                is_next_upper = next_ch.isupper()
                if (is_next_kr or is_next_upper) and k > j:  # there was whitespace
                    current_chars.append(ch)
                    sentences.append("".join(current_chars).strip())
                    current_chars = []
                    i = k  # skip past whitespace too
                    continue

        current_chars.append(ch)
        i += 1

    remainder = "".join(current_chars).strip()
    if remainder:
        sentences.append(remainder)

    return [s for s in sentences if s]


# ---------------------------------------------------------------------------
# Markdown parsing: split into sections with paragraphs
# ---------------------------------------------------------------------------
def parse_sections(lines, is_kr=False):
    """
    Returns list of sections.
    Each section: {'heading': str or None, 'paragraphs': [str, ...]}
    For KR: skip line 1 (title) and line 3 (author byline)
    Blockquote lines (starting with >) are treated as their own paragraph
    marked with a special prefix.
    """
    sections = []
    current_heading = None
    current_para_lines = []
    current_paras = []

    def flush_para():
        nonlocal current_para_lines
        text = " ".join(current_para_lines).strip()
        if text:
            current_paras.append(text)
        current_para_lines = []

    def flush_section():
        nonlocal current_heading, current_paras
        flush_para()
        sections.append({"heading": current_heading, "paragraphs": list(current_paras)})
        current_paras = []
        current_heading = None

    # For KR, skip line index 0 (title) and line index 2 (author byline)
    skip_indices = set()
    if is_kr:
        skip_indices = {0, 2}  # 0-indexed

    in_intro = True
    found_first_heading = False

    for i, raw_line in enumerate(lines):
        if i in skip_indices:
            continue

        line = raw_line.rstrip()

        # --- separator line
        if line.strip() == "---":
            flush_para()
            continue

        # ## Heading
        if line.startswith("## "):
            if not found_first_heading:
                # Save intro section (section 0)
                flush_para()
                sections.append({"heading": None, "paragraphs": list(current_paras)})
                current_paras = []
                found_first_heading = True
            else:
                flush_section()
            current_heading = line[3:].strip()
            continue

        # Blockquote
        if line.startswith("> "):
            flush_para()
            bq_text = line[2:].strip()
            current_paras.append("__BLOCKQUOTE__" + bq_text)
            continue

        # Empty line = paragraph separator
        if not line.strip():
            flush_para()
            continue

        # Regular line
        # Strip markdown bold markers like **text.**
        clean = re.sub(r'\*\*(.+?)\*\*', r'\1', line)
        # Strip italic markers
        clean = re.sub(r'\*(.+?)\*', r'\1', clean)
        current_para_lines.append(clean)

    # Flush last section
    if not found_first_heading:
        flush_para()
        sections.append({"heading": None, "paragraphs": list(current_paras)})
    else:
        flush_section()

    return sections


# ---------------------------------------------------------------------------
# Alignment and HTML generation
# ---------------------------------------------------------------------------
def merge_sentences(sents, extra_index):
    """
    Merge sentence at extra_index with its neighbor.
    Prefer merging with the next sentence; if at end, merge with previous.
    """
    if not sents:
        return sents
    result = list(sents)
    if extra_index >= len(result):
        extra_index = len(result) - 1
    if extra_index == len(result) - 1 and len(result) > 1:
        # merge with previous
        result[extra_index - 1] = result[extra_index - 1] + " " + result[extra_index]
        result.pop(extra_index)
    elif extra_index < len(result) - 1:
        # merge with next
        result[extra_index] = result[extra_index] + " " + result[extra_index + 1]
        result.pop(extra_index + 1)
    return result


def generate_para_html(en_para, kr_para, sid_base, stats):
    """
    Generate the HTML for one bi-row paragraph pair.
    sid_base: e.g. "sb-s0p0"
    Returns (en_cell_content, kr_cell_content, sids_used)
    """
    is_bq_en = en_para.startswith("__BLOCKQUOTE__")
    is_bq_kr = kr_para.startswith("__BLOCKQUOTE__")

    if is_bq_en or is_bq_kr:
        en_text = en_para.replace("__BLOCKQUOTE__", "").strip()
        kr_text = kr_para.replace("__BLOCKQUOTE__", "").strip()
        # Blockquotes get paragraph-level SID
        sid = sid_base
        en_html = f'<blockquote><span class="sent" data-sid="{sid}">{esc(en_text)}</span></blockquote>'
        kr_html = f'<blockquote><span class="sent" data-sid="{sid}">{esc(kr_text)}</span></blockquote>'
        stats["paragraph_level"] += 1
        return en_html, kr_html, [sid]

    en_sents = split_sentences_en(en_para)
    kr_sents = split_sentences_kr(kr_para)

    if not en_sents:
        en_sents = [en_para]
    if not kr_sents:
        kr_sents = [kr_para]

    en_count = len(en_sents)
    kr_count = len(kr_sents)
    diff = abs(en_count - kr_count)

    sids_used = []

    if diff == 0:
        # Perfect match - sentence level
        en_parts = []
        kr_parts = []
        for si, (es, ks) in enumerate(zip(en_sents, kr_sents)):
            sid = f"{sid_base}s{si}"
            sids_used.append(sid)
            prefix = " " if si > 0 else ""
            en_parts.append(f'<span class="sent" data-sid="{sid}">{prefix}{esc(es)}</span>')
            kr_parts.append(f'<span class="sent" data-sid="{sid}">{prefix}{esc(ks)}</span>')
            stats["sentence_level"] += 1
        en_html = f'<p>{"".join(en_parts)}</p>'
        kr_html = f'<p>{"".join(kr_parts)}</p>'

    elif diff == 1:
        # Merge the extra sentence with its neighbor
        if en_count > kr_count:
            # EN has one extra, merge at last position
            merged_en = merge_sentences(en_sents, en_count - 1)
        else:
            merged_kr = merge_sentences(kr_sents, kr_count - 1)

        if en_count > kr_count:
            final_en = merged_en
            final_kr = kr_sents
        else:
            final_en = en_sents
            final_kr = merged_kr

        count = min(len(final_en), len(final_kr))
        en_parts = []
        kr_parts = []
        for si in range(count):
            sid = f"{sid_base}s{si}"
            sids_used.append(sid)
            prefix = " " if si > 0 else ""
            en_parts.append(f'<span class="sent" data-sid="{sid}">{prefix}{esc(final_en[si])}</span>')
            kr_parts.append(f'<span class="sent" data-sid="{sid}">{prefix}{esc(final_kr[si])}</span>')
            stats["sentence_level"] += 1

        en_html = f'<p>{"".join(en_parts)}</p>'
        kr_html = f'<p>{"".join(kr_parts)}</p>'
        stats["merge_fallback"] += 1

    else:
        # Paragraph-level fallback
        sid = sid_base
        sids_used.append(sid)
        en_html = f'<p><span class="sent" data-sid="{sid}">{esc(en_para)}</span></p>'
        kr_html = f'<p><span class="sent" data-sid="{sid}">{esc(kr_para)}</span></p>'
        stats["paragraph_level"] += 1
        stats["para_mismatches"].append((sid_base, en_count, kr_count))

    return en_html, kr_html, sids_used


def build_container_html(en_sections, kr_sections):
    """Build the full container HTML content."""
    lines = []
    stats = {
        "bi_rows": 0,
        "sentence_level": 0,
        "paragraph_level": 0,
        "merge_fallback": 0,
        "all_sids": [],
        "para_mismatches": [],
    }

    sec_count = max(len(en_sections), len(kr_sections))

    for sec_idx in range(sec_count):
        if sec_idx >= len(en_sections) or sec_idx >= len(kr_sections):
            continue

        en_sec = en_sections[sec_idx]
        kr_sec = kr_sections[sec_idx]

        en_heading = en_sec["heading"]
        kr_heading = kr_sec["heading"]

        # Section divider
        if sec_idx == 0:
            divider_text = "Introduction"
        else:
            divider_text = f"Section {sec_idx}: {en_heading}" if en_heading else f"Section {sec_idx}"

        lines.append(f'<div class="section-divider">{esc(divider_text)}</div>')

        # Heading bi-row (not for section 0)
        if sec_idx > 0 and en_heading:
            lines.append('<div class="bi-row">')
            lines.append(f'  <div class="cell en"><h2>{esc(en_heading)}</h2></div>')
            lines.append(f'  <div class="cell kr"><h2>{esc(kr_heading or "")}</h2></div>')
            lines.append('</div>')
            stats["bi_rows"] += 1

        # Paragraphs
        en_paras = en_sec["paragraphs"]
        kr_paras = kr_sec["paragraphs"]

        # Align paragraph counts: use min, report if unequal
        para_count = max(len(en_paras), len(kr_paras))

        for para_idx in range(para_count):
            en_para = en_paras[para_idx] if para_idx < len(en_paras) else ""
            kr_para = kr_paras[para_idx] if para_idx < len(kr_paras) else ""

            sid_base = f"sb-s{sec_idx}p{para_idx}"

            if not en_para and not kr_para:
                continue

            # If one side is empty, use paragraph-level
            if not en_para or not kr_para:
                present_para = en_para or kr_para
                sid = sid_base
                stats["all_sids"].append(sid)
                stats["bi_rows"] += 1
                if en_para.startswith("__BLOCKQUOTE__") or kr_para.startswith("__BLOCKQUOTE__"):
                    text = present_para.replace("__BLOCKQUOTE__", "").strip()
                    en_html = f'<blockquote><span class="sent" data-sid="{sid}">{esc(text if en_para else "")}</span></blockquote>' if en_para else ""
                    kr_html = f'<blockquote><span class="sent" data-sid="{sid}">{esc(text if kr_para else "")}</span></blockquote>' if kr_para else ""
                else:
                    en_html = f'<p><span class="sent" data-sid="{sid}">{esc(en_para)}</span></p>' if en_para else "<p></p>"
                    kr_html = f'<p><span class="sent" data-sid="{sid}">{esc(kr_para)}</span></p>' if kr_para else "<p></p>"
                lines.append('<div class="bi-row">')
                lines.append(f'  <div class="cell en">{en_html}</div>')
                lines.append(f'  <div class="cell kr">{kr_html}</div>')
                lines.append('</div>')
                continue

            en_html, kr_html, sids = generate_para_html(en_para, kr_para, sid_base, stats)
            stats["all_sids"].extend(sids)
            stats["bi_rows"] += 1

            lines.append('<div class="bi-row">')
            lines.append(f'  <div class="cell en">{en_html}</div>')
            lines.append(f'  <div class="cell kr">{kr_html}</div>')
            lines.append('</div>')

    return "\n".join(lines), stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # Read source files
    with open(EN_PATH, encoding="utf-8") as f:
        en_lines = f.readlines()
    with open(KR_PATH, encoding="utf-8") as f:
        kr_lines = f.readlines()
    with open(HTML_PATH, encoding="utf-8") as f:
        html_content = f.read()

    # Parse sections
    en_sections = parse_sections(en_lines, is_kr=False)
    kr_sections = parse_sections(kr_lines, is_kr=True)

    print(f"EN sections: {len(en_sections)}")
    print(f"KR sections: {len(kr_sections)}")
    for i, (es, ks) in enumerate(zip(en_sections, kr_sections)):
        print(f"  Sec {i}: EN heading='{es['heading']}' ({len(es['paragraphs'])} paras) | KR heading='{ks['heading']}' ({len(ks['paragraphs'])} paras)")

    # Build container HTML
    container_html, stats = build_container_html(en_sections, kr_sections)

    # Find container split points in index.html
    # Find opening <div class="container"> and closing </div><!-- end container --> or equivalent
    container_open_re = re.compile(r'<div class="container">')
    # Find the last </div> before the copyright-footer
    # Strategy: find <div class="container"> position, then find next </div> that closes it
    # We'll use a simpler approach: find the marker lines

    # Find start of container content (after <div class="container">)
    match_open = container_open_re.search(html_content)
    if not match_open:
        print("ERROR: Could not find <div class=\"container\"> in index.html")
        return

    container_start = match_open.end()  # position right after <div class="container">

    # Find closing </div> for container: the one just before <div id="copyright-footer">
    # We look for the first </div> that precedes \n\n<div id="copyright-footer">
    copyright_marker = '<div id="copyright-footer">'
    copyright_pos = html_content.find(copyright_marker)
    if copyright_pos < 0:
        # Try ai-panel
        copyright_pos = html_content.find('<div id="ai-panel">')
        if copyright_pos < 0:
            print("ERROR: Could not find container closing marker")
            return

    # Find the last </div> before copyright_pos
    # Walk backwards from copyright_pos to find \n</div>\n
    end_segment = html_content[container_start:copyright_pos]
    # Find the last </div> in end_segment
    last_div_close = end_segment.rfind("</div>")
    if last_div_close < 0:
        print("ERROR: Could not find closing </div> for container")
        return

    container_end = container_start + last_div_close  # points to start of </div>

    # Reconstruct HTML
    before_container = html_content[:container_start]
    after_container = html_content[container_end:]  # starts with </div>

    new_html = before_container + "\n" + container_html + "\n" + after_container

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(new_html)

    print("\n--- Verification ---")
    print(f"Total bi-rows: {stats['bi_rows']}")
    print(f"Total unique SIDs: {len(set(stats['all_sids']))}")
    print(f"Sentence-level SIDs (s0/s1/... suffix): {stats['sentence_level']}")
    print(f"Paragraph-level SIDs (no s suffix): {stats['paragraph_level']}")
    print(f"Merge fallback applied: {stats['merge_fallback']}")

    if stats["para_mismatches"]:
        print(f"\nParagraphs with count mismatch >= 2:")
        for sid, ec, kc in stats["para_mismatches"]:
            print(f"  {sid}: EN={ec} sentences, KR={kc} sentences")
    else:
        print("No paragraph-level mismatches (diff >= 2).")

    # Check for duplicate SIDs
    all_sids = stats["all_sids"]
    seen = {}
    for sid in all_sids:
        seen[sid] = seen.get(sid, 0) + 1
    dups = {k: v for k, v in seen.items() if v > 1}
    if dups:
        print(f"\nWARNING: Duplicate SIDs found: {dups}")
    else:
        print("No duplicate SIDs.")

    print("\nDone: index.html rebuilt.")


if __name__ == "__main__":
    main()
