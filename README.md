# consumer-dispute-mcp

한국 **소비자분쟁해결기준**(공정거래위원회 고시)을 조회할 수 있는 MCP(Model Context Protocol) 서버입니다.

법제처 국가법령정보센터 API에서 데이터를 수집하여, Claude Desktop / Cursor 등 MCP 클라이언트에서 품목별 보상기준을 자연어로 검색할 수 있습니다.

## 현재 상태

- 고시 제2025-14호 (2025.12.18 시행) 기준
- 96개 품목 수집 완료
- 상품(재화) + 서비스업 부문 전체 커버

## 설치

```bash
git clone https://github.com/kknas1/consumer-dispute-mcp.git
cd consumer-dispute-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## API 키 발급

법제처 국가법령정보 공동활용 서비스에서 무료로 발급받을 수 있습니다.

1. [open.law.go.kr](https://open.law.go.kr) 회원가입
2. 로그인 후 OPEN API 키 발급
3. 환경변수로 설정:

```bash
export LAW_API_KEY=your_api_key
```

## 데이터 수집

```bash
LAW_API_KEY=your_api_key python scripts/fetch_law.py
```

`data/disputes_latest.json`에 구조화된 데이터가 저장됩니다.

## MCP 서버 실행

```bash
consumer-dispute-mcp
```

또는:

```bash
python -m consumer_dispute_mcp.server
```

### Claude Desktop 연동

`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "consumer-dispute": {
      "command": "python",
      "args": ["-m", "consumer_dispute_mcp.server"],
      "cwd": "/path/to/consumer-dispute-mcp"
    }
  }
}
```

### Cursor 연동

`.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "consumer-dispute": {
      "command": "python",
      "args": ["-m", "consumer_dispute_mcp.server"],
      "cwd": "/path/to/consumer-dispute-mcp"
    }
  }
}
```

## MCP 도구

| 도구 | 설명 |
|------|------|
| `search_dispute_standard` | 품목명/업종으로 보상기준 검색 |
| `get_remedy_guide` | 피해 상황을 자연어로 입력하면 적용 가능한 보상기준 반환 |
| `list_industries` | 전체 업종 목록 조회 |
| `get_law_version` | 현재 데이터 버전 및 업데이트 일시 확인 |

## 데이터 파이프라인

```
공정거래위원회 (고시 발령)
    ↓
법제처 국가법령정보센터 (디지털화)
    ↓
law.go.kr/DRF API (XML)
    ↓
parser.py (텍스트 테이블 파싱)
    ↓
disputes_latest.json (구조화 JSON)
    ↓
MCP 서버 (Claude/Cursor에서 도구로 사용)
```

## 관련 법령

- 소비자기본법 제16조제2항
- 소비자기본법 시행령 제8조, 제9조
- 소비자분쟁해결기준 (공정거래위원회 고시) - 별표 I~IV

## Disclaimer

이 프로젝트는 **개인 프로젝트**이며, 공정거래위원회·법제처 등 어떠한 정부기관과도 관련이 없습니다. 제공되는 데이터는 법적 효력이 없으며, 정확한 분쟁해결기준은 반드시 [국가법령정보센터](https://www.law.go.kr)에서 원문을 확인하시기 바랍니다.

## 라이선스

MIT
