# consumer-dispute-mcp

## 프로젝트 개요

한국 소비자분쟁해결기준(공정거래위원회 고시)을 MCP(Model Context Protocol) 서버로 구현한 오픈소스 프로젝트.

- **데이터 소스**: 법제처 국가법령정보센터 (open.law.go.kr) + law.go.kr
- **자동 업데이트**: GitHub Actions가 법령 변경이력 API를 매일 폴링하여 고시 개정 시 자동으로 데이터 갱신
- **목적**: Claude Desktop, Cursor 등 MCP 클라이언트에서 소비자분쟁 보상기준을 자연어로 조회

## 기술 스택

- **언어**: Python 3.11+
- **MCP SDK**: `mcp` (anthropic 공식)
- **파싱**: `httpx`, `beautifulsoup4`, `lxml`
- **스케줄링**: GitHub Actions (cron)
- **데이터 포맷**: JSON (구조화된 품목별 보상기준)

## 프로젝트 구조

```
consumer-dispute-mcp/
├── CLAUDE.md                   # 이 파일
├── README.md
├── pyproject.toml
├── src/
│   └── consumer_dispute_mcp/
│       ├── __init__.py
│       ├── server.py           # MCP 서버 메인
│       ├── parser.py           # law.go.kr 파싱 로직
│       ├── updater.py          # 법령 변경이력 API 폴링
│       └── models.py           # 데이터 모델 (Pydantic)
├── data/
│   ├── disputes_latest.json    # 최신 품목별 보상기준 (자동 업데이트)
│   ├── snapshots/              # 버전별 스냅샷 (날짜 기반)
│   └── CHANGELOG.md            # 법령 변경 이력 자동 생성
├── scripts/
│   ├── fetch_law.py            # 법령 수동 fetch 스크립트
│   └── validate_data.py        # 데이터 무결성 검증
├── tests/
│   ├── test_parser.py
│   ├── test_server.py
│   └── fixtures/               # 테스트용 법령 HTML 샘플
└── .github/
    └── workflows/
        ├── law_update.yml      # 핵심: 법령 변경 감지 + 자동 업데이트
        └── ci.yml              # PR 시 테스트
```

## 핵심 데이터 구조

소비자분쟁해결기준은 **127개 업종, 559개 품목**으로 구성됨 (2024.12.27 기준).

```json
{
  "meta": {
    "version": "2024-12-27",
    "law_name": "소비자분쟁해결기준",
    "announcement_no": "공정거래위원회 고시 제2024-XX호",
    "fetched_at": "2025-04-03T00:00:00Z"
  },
  "items": [
    {
      "industry": "공산품",
      "category": "전자제품",
      "item": "TV",
      "damage_types": [
        {
          "condition": "구입 후 10일 이내 정상 사용 중 중요 하자",
          "remedy": ["제품교환", "구입가환급"]
        },
        {
          "condition": "품질보증기간 이내 수리 불가능",
          "remedy": ["제품교환", "구입가환급"]
        }
      ],
      "warranty_period": "1년",
      "parts_retention_period": "7년"
    }
  ]
}
```

## MCP Tools 설계

서버가 노출할 MCP 도구:

### `search_dispute_standard`
품목명 또는 업종으로 보상기준 검색
```
input: { "query": "노트북", "industry": "전자제품" (optional) }
output: 해당 품목의 피해유형별 보상기준 리스트
```

### `get_remedy_guide`
사용자 상황을 자연어로 입력받아 적용 가능한 보상기준 반환
```
input: { "situation": "에어컨 구매 3개월 후 냉방 불량, 수리 2회 시도" }
output: 해당되는 보상기준 + 청구 방법 안내
```

### `list_industries`
전체 업종 목록 반환

### `get_law_version`
현재 데이터의 법령 버전 및 최종 업데이트 일시 반환

## GitHub Actions: law_update.yml 핵심 로직

```
매일 09:00 KST 실행
→ 법제처 행정규칙 변경이력 API 호출
→ "소비자분쟁해결기준" 시행일자 비교
→ 변경 감지 시:
   1. law.go.kr에서 최신 고시 전문 파싱
   2. disputes_latest.json 업데이트
   3. snapshots/ 에 날짜 기반 백업
   4. CHANGELOG.md 자동 추가 (변경 품목 diff)
   5. GitHub Release 생성
   6. (선택) Slack/이메일 알림
```

## 법제처 API 엔드포인트

- **행정규칙 목록 조회**: `https://open.law.go.kr/LSO/openApi/admRulInfo/admRulInfoList.do`
- **행정규칙 본문 조회**: `https://open.law.go.kr/LSO/openApi/admRulInfo/admRulInfoByLsiSeq.do`
- **변경이력 목록**: `https://www.data.go.kr/data/15058499/openapi.do` (법령 변경이력)
- API 키: `open.law.go.kr` 회원가입 후 무료 발급

## 개발 시 주의사항

- `disputes_latest.json`은 GitHub Actions가 자동 커밋하므로, 수동으로 편집하지 말 것
- 법령 파싱은 HWP 원본이 아닌 law.go.kr HTML 기준 (HWP 파싱은 별도 이슈로 관리)
- 품목명 검색 시 유사어 처리 필요 (예: "노트북" ↔ "휴대용컴퓨터")
- MCP 서버는 stdio transport 기본, SSE transport 옵션으로 제공

## 관련 법령

- 소비자기본법 제16조제2항
- 소비자기본법 시행령 제8조, 제9조
- 소비자분쟁해결기준 (공정거래위원회 고시) — 별표 I~IV
