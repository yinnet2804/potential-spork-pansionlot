"""동행복권 연금복권720+ 당첨번호 크롤러.

결과 페이지(/pt720/result)가 내부적으로 호출하는 두 엔드포인트를 쓴다.

- /pt720/selectPstPt720WnList.do
    파라미터 없이 전 회차를 한 번에 돌려준다. 1회부터 최신 회차까지
    회차·추첨일·1등 조·1등 6자리·보너스 6자리가 들어 있어 반복 요청이 필요 없다.
- /pt720/selectPstPt720Info.do?srchPsltEpsd=N
    N회차 주변 몇 회차의 등위별 당첨금과 당첨자 수를 돌려준다.
    당첨금은 회차와 무관하게 고정이라 최신 회차 것만 읽어 등위표를 만든다.

수집 결과는 data/pension720.json 한 파일에 저장하고, 정적 페이지가 이를
그대로 읽어 통계를 계산한다.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

ALLOWED_HOST = "www.dhlottery.co.kr"
RESULT_PAGE = f"https://{ALLOWED_HOST}/pt720/result"
LIST_URL = f"https://{ALLOWED_HOST}/pt720/selectPstPt720WnList.do"
INFO_URL = f"https://{ALLOWED_HOST}/pt720/selectPstPt720Info.do"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Referer": RESULT_PAGE,
    "Accept": "application/json",
}

DATA_FILE = Path(__file__).parent / "data" / "pension720.json"

GROUP_COUNT = 5
DIGIT_COUNT = 6

# 등위별 일치 조건과 지급 방식. 금액 자체는 API에서 읽고, 여기에는 금액만으로는
# 알 수 없는 설명만 둔다. 보너스는 wnSqNo가 21로 따로 내려온다.
RANK_META = {
    1: ("1등", "조 + 6자리 전부 일치", "매월 700만원 × 20년"),
    2: ("2등", "조는 달라도 6자리 일치", "매월 100만원 × 10년"),
    3: ("3등", "뒤 5자리 일치", "일시금"),
    4: ("4등", "뒤 4자리 일치", "일시금"),
    5: ("5등", "뒤 3자리 일치", "일시금"),
    6: ("6등", "뒤 2자리 일치", "일시금"),
    7: ("7등", "뒤 1자리 일치", "일시금"),
}
BONUS_SQ_NO = 21
BONUS_META = ("보너스", "보너스 번호 6자리 일치 (조 무관)", "매월 100만원 × 10년")

_session = requests.Session()
_retry = Retry(
    total=3,
    backoff_factor=1.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
_session.mount("https://", HTTPAdapter(max_retries=_retry))


class CrawlError(RuntimeError):
    pass


def _get_json(url: str, params: dict | None = None) -> dict:
    resp = _session.get(url, params=params, headers=HEADERS, timeout=(5, 10))
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "json" not in content_type.lower():
        # 점검·차단 페이지가 HTML로 돌아오는 경우를 조용히 넘기지 않는다.
        raise CrawlError(f"예상치 못한 응답 Content-Type: {content_type!r}")

    try:
        return resp.json()
    except ValueError as exc:
        raise CrawlError(f"{url} 응답을 JSON으로 해석할 수 없습니다") from exc


def _result_rows(payload: dict) -> list[dict]:
    rows = ((payload.get("data") or {}).get("result")) or []
    if not isinstance(rows, list):
        raise CrawlError("result가 리스트가 아닙니다")
    return rows


def _to_draw(item: dict) -> dict:
    """WnList 한 건을 저장 형식으로 바꾸면서 값 형식을 검증한다."""
    epsd = item.get("psltEpsd")
    if not isinstance(epsd, int) or epsd < 1:
        raise CrawlError(f"잘못된 회차: {epsd!r}")

    ymd = str(item.get("psltRflYmd") or "")
    if not re.fullmatch(r"\d{8}", ymd):
        raise CrawlError(f"{epsd}회 잘못된 추첨일 형식: {ymd!r}")

    group = str(item.get("wnBndNo") or "")
    if group not in {str(g) for g in range(1, GROUP_COUNT + 1)}:
        raise CrawlError(f"{epsd}회 잘못된 조: {group!r}")

    number = str(item.get("wnRnkVl") or "")
    if not re.fullmatch(r"\d{%d}" % DIGIT_COUNT, number):
        raise CrawlError(f"{epsd}회 잘못된 1등 번호: {number!r}")

    # 보너스 번호는 초기 회차에 비어 있을 가능성을 감안해 없으면 None으로 둔다.
    bonus = str(item.get("bnsRnkVl") or "")
    if bonus and not re.fullmatch(r"\d{%d}" % DIGIT_COUNT, bonus):
        raise CrawlError(f"{epsd}회 잘못된 보너스 번호: {bonus!r}")

    return {
        "round": epsd,
        "date": f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}",
        "group": int(group),
        "number": number,
        "bonus": bonus or None,
    }


def fetch_draws() -> list[dict]:
    """전 회차를 회차 오름차순으로 반환한다."""
    rows = _result_rows(_get_json(LIST_URL))
    if not rows:
        raise CrawlError("회차 목록이 비어 있습니다")

    draws = sorted((_to_draw(r) for r in rows), key=lambda d: d["round"])

    rounds = [d["round"] for d in draws]
    if len(set(rounds)) != len(rounds):
        raise CrawlError("회차가 중복됩니다")
    expected = list(range(rounds[0], rounds[-1] + 1))
    if rounds != expected:
        missing = sorted(set(expected) - set(rounds))
        raise CrawlError(f"누락된 회차가 있습니다: {missing[:10]}")

    return draws


def fetch_prizes(target_round: int) -> list[dict]:
    """등위별 당첨금 표를 만든다. 금액은 회차와 무관하게 고정이다."""
    rows = _result_rows(_get_json(INFO_URL, {"srchPsltEpsd": target_round}))
    # 이 엔드포인트는 인접 회차까지 함께 내려주므로 대상 회차만 남긴다.
    rows = [r for r in rows if r.get("psltEpsd") == target_round]
    if not rows:
        raise CrawlError(f"{target_round}회 당첨금 정보를 찾지 못했습니다")

    prizes = []
    for rank, (label, match, payout) in RANK_META.items():
        row = next((r for r in rows if r.get("wnSqNo") == rank), None)
        if row is None:
            raise CrawlError(f"{target_round}회 {label} 행이 없습니다")
        prizes.append(
            {
                "rank": label,
                "match": match,
                "amount": int(row["wnAmt"]),
                "payout": payout,
            }
        )

    bonus = next((r for r in rows if r.get("wnSqNo") == BONUS_SQ_NO), None)
    if bonus is not None:
        label, match, payout = BONUS_META
        prizes.append(
            {
                "rank": label,
                "match": match,
                "amount": int(bonus["wnAmt"]),
                "payout": payout,
            }
        )

    return prizes


def crawl() -> dict:
    draws = fetch_draws()
    latest = draws[-1]
    return {
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": RESULT_PAGE,
        "latestRound": latest["round"],
        "latestDate": latest["date"],
        "prizes": fetch_prizes(latest["round"]),
        "draws": draws,
    }


def _content(payload: dict) -> str:
    """수집 시각을 뺀 알맹이. 두 수집 결과가 같은지 비교하는 데 쓴다."""
    return json.dumps(
        {k: v for k, v in payload.items() if k != "updatedAt"},
        ensure_ascii=False,
        sort_keys=True,
    )


def save(payload: dict) -> bool:
    """내용이 실제로 바뀐 경우에만 파일을 다시 쓰고 True를 돌려준다.

    updatedAt은 돌릴 때마다 달라지므로 그것까지 변경으로 보면 새 회차가
    없는데도 매번 파일이 바뀐다. 주간 자동 갱신에서 빈 커밋이 쌓이지
    않도록 회차·당첨금이 그대로면 기존 파일을 건드리지 않는다.
    """
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    if DATA_FILE.exists():
        try:
            previous = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except ValueError:
            previous = None  # 깨진 파일은 새로 쓴다.
        if previous is not None and _content(previous) == _content(payload):
            return False

    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    DATA_FILE.write_text(text + "\n", encoding="utf-8", newline="\n")
    return True


if __name__ == "__main__":
    data = crawl()
    changed = save(data)
    print(
        f"{len(data['draws'])}개 회차 "
        f"({data['draws'][0]['round']}~{data['latestRound']}회, "
        f"{data['draws'][0]['date']}~{data['latestDate']}) · "
        + (f"{DATA_FILE} 갱신" if changed else "변경 없음")
    )
