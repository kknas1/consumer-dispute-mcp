"""소비자분쟁해결기준 수동 fetch 스크립트.

사용법:
    LAW_API_KEY=your_key python scripts/fetch_law.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from consumer_dispute_mcp.parser import fetch_and_parse, save_disputes_json

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


async def main() -> None:
    print("소비자분쟁해결기준 데이터를 가져오는 중...")
    data = await fetch_and_parse()

    out_path = DATA_DIR / "disputes_latest.json"
    save_disputes_json(data, out_path)
    print(f"저장 완료: {out_path}")
    print(f"  버전: {data.meta.version}")
    print(f"  품목 수: {len(data.items)}")


if __name__ == "__main__":
    asyncio.run(main())
