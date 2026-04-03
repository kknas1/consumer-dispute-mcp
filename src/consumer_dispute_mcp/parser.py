"""법제처 API로 소비자분쟁해결기준 파싱.

데이터 소스:
- 행정규칙 목록: www.law.go.kr/DRF/lawSearch.do?target=admrul
- 행정규칙 본문: www.law.go.kr/DRF/lawService.do?target=admrul

사용법:
    api_key는 open.law.go.kr 회원가입 후 무료 발급.
    환경변수 LAW_API_KEY 또는 함수 인자로 전달.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from bs4 import BeautifulSoup, Tag

from consumer_dispute_mcp.models import (
    DamageType,
    DisputeData,
    DisputeItem,
    Meta,
)

BASE_URL = "http://www.law.go.kr/DRF"
LAW_NAME = "소비자분쟁해결기준"

# ── API 호출 ──────────────────────────────────────────


def _get_api_key() -> str:
    key = os.environ.get("LAW_API_KEY", "")
    if not key:
        raise RuntimeError("LAW_API_KEY 환경변수를 설정해주세요. (open.law.go.kr에서 발급)")
    return key


async def fetch_admin_rule_list(api_key: str | None = None) -> list[dict]:
    """행정규칙 목록에서 '소비자분쟁해결기준' 항목을 검색한다.

    Returns:
        법령 목록 (행정규칙일련번호, 법령명, 시행일자 등).
    """
    key = api_key or _get_api_key()
    params = {
        "OC": key,
        "target": "admrul",
        "query": LAW_NAME,
        "type": "XML",
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(f"{BASE_URL}/lawSearch.do", params=params)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml-xml")
    results = []
    for item in soup.find_all("admrul"):
        results.append({
            "lsi_seq": _text(item, "행정규칙일련번호"),
            "law_name": _text(item, "행정규칙명"),
            "announcement_no": _text(item, "발령번호"),
            "enforce_date": _text(item, "시행일자"),
        })
    return results


async def fetch_admin_rule_body_xml(lsi_seq: str, api_key: str | None = None) -> str:
    """행정규칙 본문 XML을 가져온다.

    Args:
        lsi_seq: 행정규칙일련번호.

    Returns:
        본문 XML 문자열.
    """
    key = api_key or _get_api_key()
    params = {
        "OC": key,
        "target": "admrul",
        "ID": lsi_seq,
        "type": "XML",
    }
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(f"{BASE_URL}/lawService.do", params=params)
        resp.raise_for_status()
    return resp.text


# ── 텍스트 테이블 파싱 ───────────────────────────────


def parse_dispute_tables(xml_text: str) -> list[DisputeItem]:
    """행정규칙 XML에서 별표 II(품목별 해결기준) 텍스트 테이블을 파싱한다.

    법제처 API는 별표를 박스 드로잉 문자(┃┠┼━ 등)로 된 텍스트 테이블로 제공한다.
    각 테이블 블록은 품목 헤더 + 분쟁유형/해결기준/비고 행으로 구성된다.

    Returns:
        파싱된 DisputeItem 리스트.
    """
    soup = BeautifulSoup(xml_text, "lxml-xml")

    # 별표 II = 품목별 해결기준 (두 번째 별표단위)
    tables = soup.find_all("별표단위")
    if len(tables) < 2:
        raise RuntimeError("별표 II (품목별 해결기준)를 찾을 수 없습니다.")

    content = tables[1].find("별표내용").get_text()
    lines = content.split("\n")

    items: list[DisputeItem] = []
    current_industry = ""
    current_section = ""  # Ⅰ. 상품(재화), Ⅱ. 서비스업 부문

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 대분류: Ⅰ. 상품(재화), Ⅱ. 서비스업 부문
        section_match = re.match(r"^(Ⅰ|Ⅱ|Ⅲ|Ⅳ)\.\s*(.+)", line)
        if section_match:
            current_section = section_match.group(2).strip()
            i += 1
            continue

        # 업종 헤더: "1. 농ㆍ수ㆍ축산물(7개 업종)" 등
        industry_match = re.match(r"^\d+\.\s+(.+)", line)
        if industry_match and "┃" not in line:
            current_industry = industry_match.group(1).strip()
            # 괄호 안 개수 정보 제거
            current_industry = re.sub(r"\(\d+개\s*(업종|품목|품종)\)", "", current_industry).strip()
            i += 1
            continue

        # 테이블 블록 시작: ┏━━...┓
        if line.startswith("┏"):
            block_lines = []
            while i < len(lines):
                block_lines.append(lines[i])
                if lines[i].strip().startswith("┗"):
                    i += 1
                    break
                i += 1
            else:
                i += 1

            parsed = _parse_text_table_block(
                block_lines, current_industry, current_section,
            )
            if parsed:
                items.append(parsed)
            continue

        i += 1

    return _merge_items(items)


def _parse_text_table_block(
    block_lines: list[str],
    industry: str,
    section: str,
) -> DisputeItem | None:
    """박스 드로잉 문자로 된 하나의 테이블 블록을 파싱한다.

    블록 구조:
        ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
        ┃① 품목명                         ┃  ← 품목 헤더
        ┠────────┬──────────┬──────┨
        ┃분쟁유형         │해결기준       │비고  ┃  ← 컬럼 헤더
        ┣━━━━━━━━┿━━━━━━━━━━┿━━━━━━┫
        ┃1) 조건...       │o 교환 또는... │     ┃  ← 데이터 행
        ┗━━━━━━━━┷━━━━━━━━━━┷━━━━━━┛
    """
    if len(block_lines) < 4:
        return None

    # 품목명 추출 (첫 번째 데이터 행)
    item_name = ""
    for line in block_lines[1:]:
        stripped = line.strip()
        if stripped.startswith("┃") and "분" not in stripped[:10]:
            # ┃① 전자제품, 사무용기기 (2 - 1)┃
            inner = _strip_box(stripped)
            if inner and not inner.startswith("분"):
                item_name = inner
                # 페이지 번호 제거: (2 - 1) 등
                item_name = re.sub(r"\(\d+\s*-\s*\d+\)", "", item_name).strip()
                # 공백 정리
                item_name = _clean_text(item_name)
                break
        if stripped.startswith("┠") or stripped.startswith("┣"):
            break

    if not item_name:
        return None

    # 데이터 행 파싱 (┣━━ 이후부터 ┗ 전까지)
    damage_types: list[DamageType] = []
    in_data = False
    current_condition_parts: list[str] = []
    current_remedy_parts: list[str] = []

    for line in block_lines:
        stripped = line.strip()

        # 데이터 영역 시작 감지
        if stripped.startswith("┣"):
            in_data = True
            continue

        if not in_data:
            continue

        # 테이블 끝
        if stripped.startswith("┗"):
            break

        # 행 구분선 → 현재 축적된 데이터를 하나의 DamageType으로 저장
        if stripped.startswith("┠"):
            if current_condition_parts:
                condition = _clean_text(" ".join(current_condition_parts))
                remedy = _clean_text(" ".join(current_remedy_parts))
                if condition and remedy:
                    damage_types.append(DamageType(
                        condition=condition,
                        remedy=_parse_remedies(remedy),
                    ))
                current_condition_parts = []
                current_remedy_parts = []
            continue

        # 데이터 행: ┃ 내용1 │ 내용2 │ 내용3 ┃
        if stripped.startswith("┃"):
            cols = _split_by_columns(line)
            if len(cols) >= 2:
                cond_text = cols[0].strip()
                remedy_text = cols[1].strip()
                if cond_text:
                    current_condition_parts.append(cond_text)
                if remedy_text:
                    current_remedy_parts.append(remedy_text)

    # 마지막 미저장 항목 처리
    if current_condition_parts:
        condition = _clean_text(" ".join(current_condition_parts))
        remedy = _clean_text(" ".join(current_remedy_parts))
        if condition and remedy:
            damage_types.append(DamageType(
                condition=condition,
                remedy=_parse_remedies(remedy),
            ))

    if not damage_types:
        return None

    return DisputeItem(
        industry=industry,
        category=section,
        item=item_name,
        damage_types=damage_types,
    )


def _split_by_columns(line: str) -> list[str]:
    """데이터 행을 │ 문자 기준으로 분할한다.

    행 형태: ┃ 분쟁유형 │ 해결기준 │ 비고 ┃
    → ["분쟁유형", "해결기준"] (비고 컬럼은 제외)
    """
    inner = _strip_box(line)
    parts = inner.split("│")
    # 비고 컬럼(마지막)은 제외하고, 분쟁유형 + 해결기준만 반환
    if len(parts) >= 2:
        return [_clean_box_text(p) for p in parts[:2]]
    return [_clean_box_text(p) for p in parts]


def _merge_items(items: list[DisputeItem]) -> list[DisputeItem]:
    """같은 품목명의 분할 테이블(2-1, 2-2 등)을 병합한다."""
    merged: dict[str, DisputeItem] = {}
    for item in items:
        key = f"{item.industry}|{item.item}"
        if key in merged:
            merged[key].damage_types.extend(item.damage_types)
        else:
            merged[key] = item
    return list(merged.values())


# ── 데이터 저장 ───────────────────────────────────────


def save_disputes_json(data: DisputeData, path: str | Path) -> None:
    """DisputeData를 JSON 파일로 저장한다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        data.model_dump_json(indent=2),
        encoding="utf-8",
    )


# ── 전체 파이프라인 ──────────────────────────────────


async def fetch_and_parse(api_key: str | None = None) -> DisputeData:
    """전체 파이프라인: API 호출 → 파싱 → DisputeData 반환.

    1. 행정규칙 목록에서 소비자분쟁해결기준 검색
    2. 최신 버전의 본문 XML 조회
    3. 텍스트 테이블 파싱하여 구조화된 데이터 반환
    """
    rules = await fetch_admin_rule_list(api_key)
    if not rules:
        raise RuntimeError(f"'{LAW_NAME}' 행정규칙을 찾을 수 없습니다.")

    latest = max(rules, key=lambda r: r.get("enforce_date", ""))

    xml_text = await fetch_admin_rule_body_xml(latest["lsi_seq"], api_key)
    items = parse_dispute_tables(xml_text)

    meta = Meta(
        version=latest.get("enforce_date", ""),
        announcement_no=latest.get("announcement_no", ""),
        fetched_at=datetime.now(timezone.utc),
    )
    return DisputeData(meta=meta, items=items)


# ── 유틸 ─────────────────────────────────────────────


def _text(tag: Tag, child_name: str) -> str:
    """XML 태그에서 자식 요소의 텍스트를 안전하게 추출."""
    child = tag.find(child_name)
    return child.get_text(strip=True) if child else ""


def _clean_text(text: str) -> str:
    """공백/개행 정리."""
    return re.sub(r"\s+", " ", text).strip()


def _strip_box(line: str) -> str:
    """박스 드로잉 문자(┃) 제거 후 내부 텍스트 반환."""
    inner = line.strip().strip("┃").strip()
    return inner


def _clean_box_text(text: str) -> str:
    """박스 내부 텍스트에서 불필요한 문자 제거."""
    text = text.replace("│", "").replace("┃", "")
    text = re.sub(r"[oO○ㅇ]\s+", "", text, count=1)  # "o 제품교환" → "제품교환"
    return text.strip()


def _parse_remedies(text: str) -> list[str]:
    """보상기준 텍스트를 개별 구제수단 리스트로 분리한다.

    예: "제품교환 또는 구입가환급" → ["제품교환", "구입가환급"]
    """
    parts = re.split(r"\s+또는\s+|\s+혹은\s+", text)
    return [p.strip() for p in parts if p.strip()]
