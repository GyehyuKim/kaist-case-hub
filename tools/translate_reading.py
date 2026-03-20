#!/usr/bin/env python3
"""
translate_reading.py - Context-aware academic essay translation using GPT-5 nano

Usage:
    python translate_reading.py <source.md>
        --context "Author=X, Year=Y, Type=essay, Topic=Z"
        --tone    "1st-person reflective|analytical|academic|essay"
        --subject "AI|medicine|economics|business"
        --output  <output_kr.md>

Requirements:
    pip install openai
    set OPENAI_API_KEY=<your-key>
"""

import argparse
import os
import sys
from pathlib import Path

from openai import OpenAI

# ---------------------------------------------------------------------------
# Subject-domain glossaries (applied to system prompt)
# ---------------------------------------------------------------------------
SUBJECT_GLOSSARIES = {
    "AI": """\
AI/기술 분야 주요 용어 (첫 등장 시 한국어(영어) 병기, 이후 한국어만):
- artificial general intelligence / AGI -> 인공일반지능(AGI)
- large language model / LLM -> 대규모 언어 모델(LLM)
- alignment -> 정렬
- superintelligence -> 초지능
- automation bias -> 자동화 편향
- reinforcement learning -> 강화학습
- transformer -> 트랜스포머
- emergent behavior -> 창발적 행동
- human oversight -> 인간 감독
- corrigibility -> 수정 가능성
- principal-agent problem -> 주인-대리인 문제
- benchmark -> 벤치마크
- fine-tuning -> 파인튜닝
- inference -> 추론
- neural network -> 신경망
- jagged technological frontier -> 들쭉날쭉한 기술의 최전선
""",
    "medicine": """\
의학/생명과학 분야 주요 용어:
- clinical trial -> 임상시험
- randomized controlled trial / RCT -> 무작위 대조 시험(RCT)
- biomarker -> 바이오마커
- CRISPR -> CRISPR(크리스퍼)
- mRNA vaccine -> mRNA 백신
- proteomics -> 프로테오믹스
- optogenetics -> 광유전학
- CAR-T therapy -> CAR-T 세포 치료
- Alzheimer's disease -> 알츠하이머병
- neurodegenerative disease -> 신경퇴행성 질환
- in vitro -> 시험관 내
- in vivo -> 생체 내
""",
    "economics": """\
경제학 분야 주요 용어:
- GDP -> GDP
- marginal returns -> 한계 수익
- factors of production -> 생산 요소
- economic development -> 경제 발전
- poverty -> 빈곤
- inequality -> 불평등
- productivity -> 생산성
- purchasing power parity -> 구매력 평가(PPP)
""",
    "business": """\
경영 분야 주요 용어:
- venture capital / VC -> 벤처캐피털(VC)
- term sheet -> 텀시트
- liquidation preference -> 청산 우선권
- anti-dilution -> 희석 방지
- board seat -> 이사회 의석
- burn rate -> 번 레이트
- runway -> 런웨이
""",
}

# ---------------------------------------------------------------------------
# Translation tone instructions
# ---------------------------------------------------------------------------
TONE_INSTRUCTIONS = {
    "1st-person reflective": (
        "저자의 1인칭 시점('저는', '제가', '저의')을 반드시 유지하십시오. "
        "성찰적이고 지식인 에세이체로 번역하십시오. "
        "저자가 개인적 신념과 판단을 서술하는 목소리를 그대로 살려야 합니다."
    ),
    "analytical": (
        "분석적이고 학문적인 문체로 번역하십시오. "
        "객관적 어조를 유지하되 논리적 흐름을 살리십시오."
    ),
    "academic": (
        "논문체 한국어로 번역하십시오. "
        "~이다/~하였다 체계를 사용하되 가독성을 유지하십시오."
    ),
    "essay": (
        "에세이 문체 한국어로 번역하십시오. "
        "자연스럽고 읽기 쉬운 문장을 만드십시오."
    ),
}


def build_system_prompt(context: str, tone: str, subject: str) -> str:
    tone_instr = TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["essay"])
    glossary = SUBJECT_GLOSSARIES.get(subject, "")

    return f"""당신은 한국어 학술 번역 전문가입니다. 아래 영문 원고를 고품질 한국어로 번역합니다.

## 원고 컨텍스트
{context}

## 번역 원칙

### 1. 저자 목소리 보존
{tone_instr}

### 2. 단락 단위 번역 (문장 직역 금지)
- 문장 단위 직역이 아닌, 단락 전체의 의미와 흐름을 파악한 후 번역하십시오.
- 관용적 표현은 의미를 살려 의역하십시오.
  예시: "a plan to fight fires" -> "당장의 불을 끄기 위한 대책"
  예시: "talking your book" -> "자기 이익에 유리한 말만 늘어놓는 것"
- 영어의 복잡한 구조를 한국어에 자연스럽게 재구성하십시오.

### 3. 전문 용어 처리
- 첫 등장: 한국어(영어) 형식으로 병기 (예: 인공일반지능(AGI))
- 이후 등장: 한국어만 사용
- 고유명사(인명, 기관명, 제품명, 논문명)는 원문 영어 유지
{glossary}

### 4. 문장 완결성 (필수 준수)
- 모든 번역 문장은 문법적으로 완전한 문장이어야 합니다.
- "~아닌.", "~때문에.", "~하지만.", "~위해서." 등 불완전한 파편 절대 금지.
- 원문의 em dash(--)나 콜론(:)은 한국어에서 자연스러운 연결어로 처리하십시오.
- 원문이 긴 문장 하나라면, 한국어에서 두 문장으로 나눠도 됩니다.

### 5. 출력 형식
- 원문의 단락 구조(섹션 제목, 단락 구분, 번호 목록, 불릿 포인트)를 그대로 보존하십시오.
- 섹션 헤더: 영어 원문 헤더 아래에 "### 한국어 제목" 형식으로 추가하십시오.
- 각주는 > **[각주 N]** 내용 형식으로 처리하십시오.
- 번역 완료 후 메타 코멘트나 설명을 일절 덧붙이지 마십시오.

원문을 받으면 즉시 번역을 시작하십시오."""


def translate_chunk(client: OpenAI, text: str, system_prompt: str, max_output: int = 65536) -> str:
    response = client.responses.create(
        model="gpt-5-nano",
        max_output_tokens=max_output,
        reasoning={"effort": "low"},
        input=[
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        ],
    )

    result = response.output_text

    if not result:
        collected = []
        for item in response.output or []:
            for part in item.get("content", []) or []:
                if part.get("type") in ("output_text", "text") and part.get("text"):
                    collected.append(part["text"])
        result = "\n".join(collected).strip()

    if not result:
        details = getattr(response, "incomplete_details", None)
        status = getattr(response, "status", "unknown")
        print(f"[WARNING] Empty output. status={status}, incomplete_details={details}", file=sys.stderr)

    return result or ""


def split_into_chunks(text: str, max_chars: int = 300_000) -> list:
    """Split at paragraph boundaries if text exceeds max_chars."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    paragraphs = text.split("\n\n")
    current = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para) + 2
        if current_len + para_len > max_chars and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def main():
    parser = argparse.ArgumentParser(
        description="Context-aware academic essay translation via GPT-5 nano"
    )
    parser.add_argument("source", help="Source .md or .txt file (English original)")
    parser.add_argument(
        "--context",
        required=True,
        help='Context descriptor, e.g. "Author=Dario Amodei, Year=2024, Type=Essay, Topic=AI optimism"',
    )
    parser.add_argument(
        "--tone",
        default="essay",
        choices=list(TONE_INSTRUCTIONS.keys()),
        help="Translation tone/style (default: essay)",
    )
    parser.add_argument(
        "--subject",
        default="AI",
        choices=list(SUBJECT_GLOSSARIES.keys()),
        help="Subject domain for terminology glossary (default: AI)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path (default: <source_stem>_KR.md next to source)",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=65536,
        help="Max output tokens per API call (default: 65536)",
    )
    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.exists():
        print(f"[ERROR] Source file not found: {source_path}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = source_path.with_name(source_path.stem + "_KR.md")

    source_text = source_path.read_text(encoding="utf-8")
    print(f"[INFO] Source  : {source_path} ({len(source_text):,} chars)", file=sys.stderr)
    print(f"[INFO] Output  : {output_path}", file=sys.stderr)
    print(f"[INFO] Context : {args.context}", file=sys.stderr)
    print(f"[INFO] Tone    : {args.tone}  |  Subject: {args.subject}", file=sys.stderr)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[ERROR] OPENAI_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    system_prompt = build_system_prompt(args.context, args.tone, args.subject)

    chunks = split_into_chunks(source_text)
    print(f"[INFO] Chunks  : {len(chunks)}", file=sys.stderr)

    translated_parts = []
    for i, chunk in enumerate(chunks, 1):
        print(
            f"[INFO] Translating chunk {i}/{len(chunks)} ({len(chunk):,} chars)...",
            file=sys.stderr,
        )
        result = translate_chunk(client, chunk, system_prompt, args.max_output_tokens)
        if not result:
            print(f"[WARNING] Empty result for chunk {i}, embedding original.", file=sys.stderr)
            translated_parts.append(f"<!-- TRANSLATION FAILED: chunk {i} -->\n\n{chunk}")
        else:
            translated_parts.append(result)

    separator = "\n\n---\n\n" if len(translated_parts) > 1 else ""
    body = separator.join(translated_parts)

    header = (
        f"# {source_path.stem} — 한국어 번역본\n\n"
        f"> **원문:** {source_path.name}\n"
        f"> **컨텍스트:** {args.context}\n"
        f"> **번역 문체:** {args.tone}\n"
        f"> **번역 도구:** GPT-5 nano (gpt-5-nano-2025-08-07)\n\n"
        f"---\n\n"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(header + body, encoding="utf-8")

    stat = output_path.stat()
    print(f"[OK] Saved: {output_path} ({stat.st_size:,} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
