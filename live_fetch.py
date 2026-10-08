# -*- coding: utf-8 -*-
"""GitHub Actions에서 매일 도는 실시간 수집 — 공개 API만 (DART 공시 · KRX 주가/지수 · 네이버 뉴스 · RSS).
Claude 분석·사내 데이터는 쓰지 않는다. 결과를 docs/live.json 으로 쓰고 encrypt.py 가 live.enc 로 봉인한다.
필요 secrets: DART_API_KEY, DATA_GO_KR_KEY, NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, SITE_PASSWORD
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import xml.etree.ElementTree as ET

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
K = {k: os.environ.get(k, "") for k in ("DART_API_KEY", "DATA_GO_KR_KEY", "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET")}
SELF = [("제뉴원사이언스", "01560350"), ("제뉴파마", "01591022")]
PEERS = [("대원제약", "003220", "00111999"), ("동구바이오제약", "006620", "00114686"), ("알리코제약", "260660", "00447007"),
         ("안국약품", "001540", "00139205"), ("휴온스", "243070", "01159853"), ("서흥", "008490", "00131692"),
         ("한국유나이티드제약", "033270", "00158963"), ("한미약품", "128940", ""), ("종근당", "185750", ""),
         ("대웅제약", "069620", ""), ("유한양행", "000100", ""), ("JW중외제약", "001060", "00149947"),
         ("동아에스티", "170900", "00956930"), ("이연제약", "102460", "00145598")]
INDICES = ["코스피", "제약", "코스피 200 헬스케어", "코스닥 150 헬스케어"]
QUERIES = ["제뉴원사이언스", "CDMO 위탁생산", "제네릭 약가 인하", "제약 위수탁", "원료의약품 국산화", "식약처 행정처분 제약"]
RSS = [("약업신문", "https://www.yakup.com/rss/rss.html"), ("데일리팜", "https://www.dailypharm.com/rss/rss.php")]


def get(url, **kw):
    try:
        r = requests.get(url, timeout=30, **kw)
        r.raise_for_status()
        return r
    except Exception as e:  # noqa: BLE001
        print("  fail", url[:60], e)
        return None


def dart():
    out = []
    if not K["DART_API_KEY"]:
        return out
    end = dt.date.today()
    bgn = end - dt.timedelta(days=14)
    for name, code in SELF + [(n, c) for n, _, c in PEERS if c]:
        r = get("https://opendart.fss.or.kr/api/list.json", params={"crtfc_key": K["DART_API_KEY"], "corp_code": code,
                                                                   "bgn_de": bgn.strftime("%Y%m%d"), "end_de": end.strftime("%Y%m%d"), "page_count": 20})
        if not r:
            continue
        for it in (r.json().get("list") or []):
            out.append({"company": name, "title": it.get("report_nm"), "date": it.get("rcept_dt"),
                        "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + it.get("rcept_no", "")})
    return sorted(out, key=lambda x: x["date"] or "", reverse=True)[:60]


def quotes():
    out = {}
    if not K["DATA_GO_KR_KEY"]:
        return out
    end = dt.date.today()
    bgn = end - dt.timedelta(days=10)
    for name, sc, _ in PEERS:
        r = get("https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo",
                params={"serviceKey": K["DATA_GO_KR_KEY"], "resultType": "json", "numOfRows": 10, "pageNo": 1,
                        "beginBasDt": bgn.strftime("%Y%m%d"), "endBasDt": end.strftime("%Y%m%d"), "likeSrtnCd": sc})
        try:
            items = r.json()["response"]["body"]["items"]["item"]
            it = sorted(items, key=lambda x: x["basDt"])[-1]
            out[name] = {"date": it["basDt"], "close": float(it["clpr"]), "change_rate": float(it["fltRt"]), "market_cap": float(it.get("mrktTotAmt") or 0)}
        except Exception:  # noqa: BLE001
            pass
    idx = {}
    for nm in INDICES:
        r = get("https://apis.data.go.kr/1160100/service/GetMarketIndexInfoService/getStockMarketIndex",
                params={"serviceKey": K["DATA_GO_KR_KEY"], "resultType": "json", "numOfRows": 10, "pageNo": 1,
                        "beginBasDt": bgn.strftime("%Y%m%d"), "endBasDt": end.strftime("%Y%m%d"), "idxNm": nm})
        try:
            items = r.json()["response"]["body"]["items"]["item"]
            it = sorted(items, key=lambda x: x["basDt"])[-1]
            idx[nm] = {"date": it["basDt"], "close": float(it["clpr"]), "change_rate": float(it["fltRt"])}
        except Exception:  # noqa: BLE001
            pass
    return {"stocks": out, "indices": idx}


def news():
    out = []
    if K["NAVER_CLIENT_ID"]:
        for q in QUERIES:
            r = get("https://openapi.naver.com/v1/search/news.json", params={"query": q, "display": 15, "sort": "date"},
                    headers={"X-Naver-Client-Id": K["NAVER_CLIENT_ID"], "X-Naver-Client-Secret": K["NAVER_CLIENT_SECRET"]})
            if not r:
                continue
            for it in r.json().get("items", []):
                out.append({"query": q, "title": re.sub(r"<[^>]+>|&quot;", "", it.get("title", "")), "url": it.get("originallink") or it.get("link"),
                            "date": it.get("pubDate", "")[:16], "source": "네이버"})
    for name, url in RSS:
        r = get(url)
        if not r:
            continue
        try:
            root = ET.fromstring(r.content)
            for item in root.iter("item"):
                out.append({"query": name, "title": (item.findtext("title") or "").strip(), "url": item.findtext("link"),
                            "date": (item.findtext("pubDate") or "")[:16], "source": name})
        except Exception:  # noqa: BLE001
            pass
    seen, uniq = set(), []
    for a in out:
        if a["title"] in seen:
            continue
        seen.add(a["title"])
        uniq.append(a)
    return uniq[:120]


if __name__ == "__main__":
    data = {"fetched_at": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "dart": dart(), "market": quotes(), "news": news()}
    os.makedirs(os.path.join(HERE, "docs"), exist_ok=True)
    out = os.path.join(HERE, "build", "live.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print("live:", len(data["dart"]), "공시 ·", len(data["market"].get("stocks", {})), "종목 ·", len(data["news"]), "기사")
