# -*- coding: utf-8 -*-
"""정적 사이트용 데이터 번들 생성 — 서버(Flask)와 로더에서 필요한 것만 뽑아 build/data.json 으로.

실행 (DevPackage venv):  ..\\GenuoneMonitor_DevPackage\\.venv\\Scripts\\python.exe -X utf8 build_site.py
전제: 모니터 서버(localhost:5001)가 켜져 있으면 API에서 가져오고, 아니면 로더로 직접 계산한다.
출력: build/data.json  (이후 encrypt.py 가 docs/index.html 로 봉인)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEV = os.path.join(os.path.dirname(HERE), "GenuoneMonitor_DevPackage")
sys.path.insert(0, DEV)
os.chdir(DEV)

import config          # noqa: E402
import companies       # noqa: E402
from src.loaders import market_data, prebuilt   # noqa: E402
from src.analysis import data_inventory          # noqa: E402

API = "http://localhost:5001/api/"
OUR = ("제뉴원", "제뉴파마", "genuone")


def api(path, default=None):
    try:
        with urllib.request.urlopen(API + path, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        print("  API 실패:", path, e)
        return default


def slim(obj, maxlist=12, depth=0):
    """리스트는 앞 N개만, 깊이 6 이상은 자름 — 번들 크기 통제."""
    if depth > 6:
        return None
    if isinstance(obj, dict):
        return {k: slim(v, maxlist, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [slim(x, maxlist, depth + 1) for x in obj[:maxlist]]
    return obj


def _is_our(name) -> bool:
    s = str(name).lower()
    return any(k.lower() in s for k in OUR)


def molecules_and_forms():
    """IQVIA 원본에서 성분(MOLECULE)·제형(NFC) 시장을 계산한다."""
    import pandas as pd
    path = market_data.latest_file()
    if not path:
        return {}, {}, {}
    print("  IQVIA:", os.path.basename(path))
    head = pd.read_excel(path, sheet_name=0, nrows=0)
    amt = market_data._amount_cols(head.columns)
    dims = [c for c in ("MFR NAME KOR", "PRODUCT NAME KOR", "MOLECULE DESC", "ATC 2", "ATC 1 CODE",
                        "NFC 1 DESC", "NFC 2 DESC", "OTC/ETHICAL") if c in head.columns]
    df = pd.read_excel(path, sheet_name=0, usecols=dims + amt)
    for c in amt:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    latest = amt[-1]
    prev4 = amt[-5] if len(amt) >= 5 else amt[0]
    qlab = [re.search(r"(\d{4})\s*(\d)Q", c).group(0) for c in amt]
    df["_our"] = df["MFR NAME KOR"].map(_is_our)

    def block(sub, key_name):
        tot = float(sub[latest].sum())
        if tot <= 0:
            return None
        g = sub.groupby("MFR NAME KOR")[latest].sum().sort_values(ascending=False)
        top_prod = sub.groupby("PRODUCT NAME KOR")[latest].sum().sort_values(ascending=False).head(8)
        our = float(sub.loc[sub["_our"], latest].sum())
        yoy = (tot / float(sub[prev4].sum()) - 1) * 100 if float(sub[prev4].sum()) > 0 else None
        return {"name": key_name, "latest": tot, "yoy": None if yoy is None else round(yoy, 1),
                "trend": [float(sub[c].sum()) for c in amt],
                "makers": [{"name": str(k), "amount": float(v), "share": round(float(v) / tot * 100, 1)} for k, v in g.head(8).items()],
                "maker_count": int((g > 0).sum()),
                "products": [{"name": str(k), "amount": float(v), "share": round(float(v) / tot * 100, 1)} for k, v in top_prod.items()],
                "our_amount": our, "our_share": round(our / tot * 100, 2),
                "our_products": [{"name": str(k), "amount": float(v)} for k, v in sub.loc[sub["_our"]].groupby("PRODUCT NAME KOR")[latest].sum().sort_values(ascending=False).head(6).items()],
                "atc2": str(sub["ATC 2"].mode().iloc[0]) if "ATC 2" in sub.columns and len(sub) else "",
                "nfc1": str(sub["NFC 1 DESC"].mode().iloc[0]) if "NFC 1 DESC" in sub.columns and len(sub) else ""}

    # 성분 — 최신 분기 상위 400 + 우리 품목이 있는 성분 전부
    mol_tot = df.groupby("MOLECULE DESC")[latest].sum().sort_values(ascending=False)
    our_mols = set(df.loc[df["_our"], "MOLECULE DESC"].unique())
    keys = list(mol_tot.head(400).index) + [m for m in our_mols if m not in set(mol_tot.head(400).index)]
    mols = {}
    for m in keys:
        b = block(df[df["MOLECULE DESC"] == m], str(m))
        if b:
            mols[str(m)] = b
    # 제형 — NFC 1 / NFC 2
    forms = {}
    for col, lvl in (("NFC 1 DESC", 1), ("NFC 2 DESC", 2)):
        if col not in df.columns:
            continue
        for f_, sub in df.groupby(col):
            b = block(sub, str(f_))
            if b and b["latest"] > 1e9:
                b["level"] = lvl
                forms[("L%d|" % lvl) + str(f_)] = b
    total = float(df[latest].sum())
    meta = {"quarters": qlab, "latest_q": qlab[-1], "total": total,
            "our_total": float(df.loc[df["_our"], latest].sum()),
            "molecule_count": int(len(mol_tot)), "file": os.path.basename(path)}
    return mols, forms, meta


def company_detail():
    """회사별 분석 번들 — company_profiles 캐시 + 레지스트리 메타."""
    prof = (prebuilt.load("company_profiles.json") or {}).get("companies", {})
    out = {}
    for c in [companies.BASE] + companies.REGISTRY:
        name = c["name"]
        p = prof.get(name)
        if not p:
            continue
        keep = {k: v for k, v in p.items() if k not in ("market_by_year", "channels_by_year")}
        out[name] = {"category": c.get("category", "self"), "listed": c.get("listed", False),
                     "stock_code": c.get("stock_code", ""), "note": c.get("note", ""), "profile": slim(keep, 10)}
    return out


def main():
    print("1) 서버 API")
    companies_json = api("companies")
    market = api("market/summary")
    issues = api("issues") or {}
    news = api("news") or {}
    cmo = api("cmo-landscape") or {}
    ing = api("ingredient-overview?year=%d" % config.PROFIT_YEAR) or {}
    prods = api("products?year=%d" % config.PROFIT_YEAR) or {}
    backlog = api("backlog") or {}

    print("2) 성분·제형 시장")
    mols, forms, mmeta = molecules_and_forms()
    print("   성분 %d · 제형 %d" % (len(mols), len(forms)))

    print("3) 회사 번들")
    cos = company_detail()
    print("   회사 %d" % len(cos))

    # 품목 — 매출 상위 400
    plist = prods.get("products") or []
    key = next((k for k in ("sales", "매출", "amount", "revenue") if plist and k in plist[0]), None)
    if key:
        plist = sorted(plist, key=lambda x: x.get(key) or 0, reverse=True)
    plist = [slim(x, 6) for x in plist[:400]]
    # 성분 오버뷰 — 상위 300
    ilist = ing.get("ingredients") or []
    ikey = next((k for k in ("sales", "매출", "amount", "total") if ilist and k in ilist[0]), None)
    if ikey:
        ilist = sorted(ilist, key=lambda x: x.get(ikey) or 0, reverse=True)
    ilist = [slim(x, 6) for x in ilist[:300]]

    bundle = {
        "built_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "company": companies.BASE["name"],
        "companies": companies_json,
        "market": market, "market_meta": mmeta,
        "issues": slim({k: v for k, v in issues.items()}, 40),
        "news": slim(news, 40),
        "cmo": slim(cmo, 150),
        "ingredients": {"year": ing.get("year"), "total": ing.get("total"), "items": ilist},
        "products": {"year": prods.get("year"), "count": prods.get("count"), "items": plist},
        "backlog": slim(backlog, 60),
        "inventory": data_inventory.build(),
        "molecules": mols, "forms": forms, "companies_detail": cos,
    }
    os.makedirs(os.path.join(HERE, "build"), exist_ok=True)
    out = os.path.join(HERE, "build", "data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, separators=(",", ":"))
    print("저장:", out, "%.1f MB" % (os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
