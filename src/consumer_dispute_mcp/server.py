"""MCP 서버 메인 — 소비자분쟁해결기준 조회 도구 제공."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from consumer_dispute_mcp.models import DisputeData

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "disputes_latest.json"

mcp = FastMCP("consumer-dispute-mcp", instructions="한국 소비자분쟁해결기준을 조회하는 MCP 서버입니다.")


def _load_data() -> DisputeData | None:
    if not DATA_PATH.exists():
        return None
    return DisputeData.model_validate_json(DATA_PATH.read_text(encoding="utf-8"))


@mcp.tool()
def search_dispute_standard(query: str, industry: str | None = None) -> str:
    """품목명 또는 업종으로 보상기준을 검색합니다.

    Args:
        query: 검색할 품목명 (예: "노트북", "에어컨")
        industry: 업종 필터 (선택, 예: "전자제품")
    """
    data = _load_data()
    if data is None:
        return "데이터가 아직 준비되지 않았습니다. scripts/fetch_law.py를 먼저 실행해주세요."

    results = []
    for item in data.items:
        if industry and industry not in item.industry and industry not in item.category:
            continue
        if query in item.item or query in item.category or query in item.industry:
            results.append(item.model_dump())

    if not results:
        return f"'{query}'에 해당하는 품목을 찾지 못했습니다."
    return json.dumps(results, ensure_ascii=False, indent=2)


@mcp.tool()
def get_remedy_guide(situation: str) -> str:
    """사용자 상황을 자연어로 입력받아 적용 가능한 보상기준을 반환합니다.

    Args:
        situation: 사용자의 피해 상황 설명 (예: "에어컨 구매 3개월 후 냉방 불량, 수리 2회 시도")
    """
    data = _load_data()
    if data is None:
        return "데이터가 아직 준비되지 않았습니다."

    # 간단한 키워드 매칭 — 향후 임베딩 기반 검색으로 개선 가능
    keywords = situation.replace(",", " ").split()
    scored: list[tuple[int, dict]] = []
    for item in data.items:
        score = sum(
            1
            for kw in keywords
            if kw in item.item or kw in item.category or kw in item.industry
        )
        if score > 0:
            scored.append((score, item.model_dump()))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [entry for _, entry in scored[:5]]

    if not top:
        return "입력하신 상황에 해당하는 보상기준을 찾지 못했습니다."
    return json.dumps(top, ensure_ascii=False, indent=2)


@mcp.tool()
def list_industries() -> str:
    """전체 업종 목록을 반환합니다."""
    data = _load_data()
    if data is None:
        return "데이터가 아직 준비되지 않았습니다."

    industries = sorted({item.industry for item in data.items})
    return json.dumps(industries, ensure_ascii=False, indent=2)


@mcp.tool()
def get_law_version() -> str:
    """현재 데이터의 법령 버전 및 최종 업데이트 일시를 반환합니다."""
    data = _load_data()
    if data is None:
        return "데이터가 아직 준비되지 않았습니다."
    return data.meta.model_dump_json(indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
