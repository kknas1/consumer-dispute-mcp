"""법제처 API로 소비자분쟁해결기준 파싱.

데이터 소스:
- 행정규칙 목록: open.law.go.kr/LSO/openApi/admRulInfo/admRulInfoList.do
- 행정규칙 본문: open.law.go.kr/LSO/openApi/admRulInfo/admRulInfoByLsiSeq.do

사용법:
    api_key는 open.law.go.kr 회원가입 후 무료 발급.
    환경변수 LAW_API_KEY 또는 함수 인자로 전달.
"""

from __future__ import annotations

import json
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

BASE_URL = "https://open.law.go.kr/LSO/openApi/admRulInfo"
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
        법령 목록 (lsiSeq, 법령명, 시행일자 등 포함).
    """
    key = api_key or _get_api_key()
    params = {
        "OC": key,
        "target": "admrul",
        "query": LAW_NAME,
        "type": "XML",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BASE_URL}/admRulInfoList.do", params=params)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml-xml")
    results = []
    for item in soup.find_all("admrul"):
        results.append({
            "lsi_seq": _text(item, "법령일련번호"),
            "law_name": _text(item, "행정규칙명"),
            "announcement_no": _text(item, "고시번호"),
            "enforce_date": _text(item, "시행일자"),
        })
    return results


async def fetch_admin_rule_body(lsi_seq: str, api_key: str | None = None) -> str:
    """행정규칙 본문 HTML을 가져온다.

    Args:
        lsi_seq: 법령일련번호 (fetch_admin_rule_list 결과에서 획득).

    Returns:
        본문 HTML 문자열.
    """
    key = api_key or _get_api_key()
    params = {
        "OC": key,
        "lsiSeq": lsi_seq,
        "type": "HTML",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(f"{BASE_URL}/admRulInfoByLsiSeq.do", params=params)
        resp.raise_for_status()
    return resp.text


# ── HTML 파싱 ─────────────────────────────────────────


def parse_dispute_tables(html: str) -> list[DisputeItem]:
    """행정규칙 본문 HTML에서 별표(품목별 보상기준) 테이블을 파싱한다.

    소비자분쟁해결기준 고시의 별표 II~IV에 해당하는 테이블에서
    업종, 품목, 피해유형, 보상기준을 추출한다.

    Args:
        html: 행정규칙 본문 HTML.

    Returns:
        파싱된 DisputeItem 리스트.
    """
    soup = BeautifulSoup(html, "lxml")
    items: list[DisputeItem] = []

    # 별표 테이블들을 찾는다. 실제 HTML 구조에 따라 조정 필요.
    tables = soup.find_all("table")

    current_industry = ""
    current_category = ""

    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        for row in rows[1:]:  # 헤더 행 스킵
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue

            parsed = _parse_table_row(cells, current_industry, current_category)
            if parsed is None:
                continue

            item, current_industry, current_category = parsed
            items.append(item)

    return items


def _parse_table_row(
    cells: list[Tag],
    prev_industry: str,
    prev_category: str,
) -> tuple[DisputeItem, str, str] | None:
    """테이블 행 하나를 파싱하여 DisputeItem을 생성한다.

    소비자분쟁해결기준 테이블은 보통 다음 컬럼 구조:
    업종 | 품목 | 피해유형 | 보상기준

    병합 셀(rowspan/colspan)이 많으므로, 빈 셀은 이전 행의 값을 유지한다.

    Returns:
        (DisputeItem, 업종, 품목분류) 또는 파싱 불가 시 None.
    """
    texts = [_clean_text(c.get_text()) for c in cells]

    # 최소 3개 컬럼: 품목, 피해유형, 보상기준
    # 4개 이상이면 첫 번째가 업종
    if len(texts) >= 4:
        industry = texts[0] or prev_industry
        category = texts[0] or prev_category  # 업종 = 카테고리 (세부 분류는 추후)
        item_name = texts[1]
        condition = texts[2]
        remedy_text = texts[3]
    elif len(texts) == 3:
        industry = prev_industry
        category = prev_category
        item_name = texts[0]
        condition = texts[1]
        remedy_text = texts[2]
    else:
        return None

    if not item_name or not condition:
        return None

    remedies = _parse_remedies(remedy_text)
    damage_type = DamageType(condition=condition, remedy=remedies)

    return (
        DisputeItem(
            industry=industry,
            category=category,
            item=item_name,
            damage_types=[damage_type],
        ),
        industry,
        category,
    )


def _parse_remedies(text: str) -> list[str]:
    """보상기준 텍스트를 개별 구제수단 리스트로 분리한다.

    예: "제품교환 또는 구입가환급" → ["제품교환", "구입가환급"]
    """
    # "또는", "혹은", 콤마, 세미콜론 등으로 분리
    parts = re.split(r"[,;]|\s+또는\s+|\s+혹은\s+", text)
    return [p.strip() for p in parts if p.strip()]


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
    2. 최신 버전의 본문 HTML 조회
    3. 테이블 파싱하여 구조화된 데이터 반환
    """
    rules = await fetch_admin_rule_list(api_key)
    if not rules:
        raise RuntimeError(f"'{LAW_NAME}' 행정규칙을 찾을 수 없습니다.")

    # 시행일자 기준 최신 항목
    latest = max(rules, key=lambda r: r.get("enforce_date", ""))

    html = await fetch_admin_rule_body(latest["lsi_seq"], api_key)
    items = parse_dispute_tables(html)

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
