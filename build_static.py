# -*- coding: utf-8 -*-
"""모니터 서버(:5001)의 API 응답을 전부 긁어 봉인된 청크로 저장 — 정적(GitHub Pages) 배포용.

dashboard/index.html 은 손대지 않는다. 배포본은 같은 화면을 띄우고, fetch('/api/…') 를
가로채서 미리 긁어 둔 청크에서 응답을 돌려준다(encrypt.py 의 shim). 따라서 화면·기능이 서버판과 같다.

청크 = {url: 응답} JSON → gzip → AES-256-GCM(비밀번호 PBKDF2 키) → docs/d/<name>.enc
청크 이름 규칙은 encrypt.py 의 chunkOf() 와 반드시 같아야 한다.
"""
from __future__ import annotations

import base64
import concurrent.futures as cf
import datetime as dt
import gzip
import json
import os
import secrets
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("GNS_API", "http://localhost:5001")
DOCS = os.path.join(HERE, "docs")
BUILD = os.path.join(HERE, "build")
PASSWORD = os.environ.get("SITE_PASSWORD", "gns900118")
ITER = 200_000
NOW = dt.date.today().year
QUOTE_CATS = ["cdmo", "major", "api", "excipient,packaging", "bio,cro"]
FAIL: list = []


def get_raw(path: str, timeout=300) -> bytes | None:
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return r.read()
    except Exception as e:  # noqa: BLE001
        FAIL.append((path, str(e)[:80]))
        return None


def get(path: str):
    """200 → JSON 그대로. 4xx/5xx 에 JSON 본문이 있으면 {"__st": 코드, "__b": 본문} (shim 이 같은 상태코드로 돌려준다)."""
    try:
        with urllib.request.urlopen(BASE + path, timeout=300) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return {"__st": e.code, "__b": json.loads(e.read())}
        except Exception:  # noqa: BLE001
            FAIL.append((path, f"HTTP {e.code}"))
            return None
    except Exception as e:  # noqa: BLE001
        FAIL.append((path, str(e)[:80]))
        return None


def q(s) -> str:
    return urllib.parse.quote(str(s), safe="")


def hsh(s) -> int:
    return sum(ord(c) for c in str(s))


def chunk_of(path: str, params: dict) -> str:
    """encrypt.py chunkOf() 와 동일 규칙."""
    if path == "/api/products":
        return "products_" + params.get("year", "")
    if path == "/api/ingredient-overview":
        return "ingr_" + params.get("year", "")
    if path == "/api/backlog/opportunity":
        return "oppty_" + params.get("year", "")
    if path == "/api/backlog/products":
        return "bl"
    if path.startswith("/api/product/"):
        return "pd_%d" % (hsh(path.split("/")[3]) % 24)
    if path == "/api/product-peers":
        return "pd_%d" % (hsh(params.get("code", "")) % 24)
    if path in ("/api/product-makers", "/api/product-issues"):
        return "pq_%d" % (hsh(params.get("q", "")) % 24)
    if path == "/api/model/molecule":
        return "mol_%d" % (hsh(params.get("mol", "")) % 12)
    if path.startswith("/api/company-") or path in ("/api/compare", "/api/model/company"):
        return "co_%d" % (hsh(params.get("target", "")) % 32)
    return "core"


def key_of(url: str) -> str:
    """저장 키 = 퍼센트 인코딩을 푼 URL (브라우저 쪽은 decodeURIComponent)."""
    return urllib.parse.unquote(url)


def parse(url: str):
    path, _, qs = url.partition("?")
    return path, dict(urllib.parse.parse_qsl(qs, keep_blank_values=True))


CACHE = os.path.join(BUILD, "cache")
MODE = ("--fresh" if "--fresh" in sys.argv else ("--quick" if "--quick" in sys.argv else "--default"))
# 캐시 재사용 정책: --fresh 전부 새로 / --quick 캐시에 없는 것만 / 기본 = 가벼운 청크(core·bl·연도별·model)만 새로, pd_·pq_·co_·mol_ 은 캐시
REFRESH_FAMILIES = ("core", "bl", "products_", "ingr_", "oppty_")


def _family_refresh(chunk: str) -> bool:
    return MODE == "--fresh" or (MODE == "--default" and chunk.startswith(REFRESH_FAMILIES))


class Crawl:
    def __init__(self):
        self.chunks: dict[str, dict] = {}
        self.todo: list[str] = []
        self.cache: dict[str, dict] = {}
        if MODE != "--fresh" and os.path.isdir(CACHE):
            for fn in os.listdir(CACHE):
                if fn.endswith(".json"):
                    self.cache[fn[:-5]] = json.load(open(os.path.join(CACHE, fn), encoding="utf-8"))
            print(f"캐시 {len(self.cache)}청크 ({MODE})")

    def add(self, url: str):
        path, params = parse(url)
        ch = chunk_of(path, params)
        k = key_of(url)
        if not _family_refresh(ch) and k in self.cache.get(ch, {}):
            self.chunks.setdefault(ch, {})[k] = self.cache[ch][k]
            return
        self.todo.append(url)

    def save(self):
        os.makedirs(CACHE, exist_ok=True)
        for name, data in self.chunks.items():
            with open(os.path.join(CACHE, name + ".json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

    def run(self, workers=8):
        urls = list(dict.fromkeys(self.todo))
        self.todo = []
        if not urls:
            print("   (캐시 재사용)")
            return
        t = time.time()
        done = 0
        with cf.ThreadPoolExecutor(workers) as ex:
            for url, obj in zip(urls, ex.map(lambda u: get(u), urls)):
                done += 1
                if obj is None:
                    continue
                path, params = parse(url)
                self.chunks.setdefault(chunk_of(path, params), {})[key_of(url)] = obj
                if done % 500 == 0:
                    print(f"   {done}/{len(urls)}  {time.time()-t:.0f}s", flush=True)
        print(f"   {len(urls)}건 {time.time()-t:.0f}s", flush=True)


def crawl() -> Crawl:
    c = Crawl()
    print("[1] 기본 엔드포인트")
    core = ["/api/companies", "/api/cmo-landscape", "/api/backlog", "/api/market/summary", "/api/news", "/api/issues",
            "/api/data-status", "/api/data-inventory", "/api/price-match/status", "/api/drug-prices/status",
            "/api/health", "/api/version", "/api/snapshots", "/api/model/signals", "/api/model/forms", "/api/model/companies",
            "/api/backlog/products?site=&form=&equip="]
    core += ["/api/company-quotes?cats=" + q(cat) for cat in QUOTE_CATS]
    core += [f"/api/self-overview?year={y}" for y in range(NOW - 5, NOW + 1)]
    for u in core:
        c.add(u)
    c.run()
    companies = c.chunks["core"]["/api/companies"]
    names = [x["name"] for g in companies["groups"].values() for x in g]
    backlog = c.chunks["core"].get("/api/backlog") or {}
    signals = c.chunks["core"].get("/api/model/signals") or {}
    rank = (c.chunks["core"].get("/api/model/companies") or {}).get("rows") or []

    print("[2] 연도별 대용량 (품목·주성분·수주전환) + 설비별 잔고")
    for y in range(NOW - 3, NOW + 1):
        c.add(f"/api/products?year={y}&limit=5000")
        c.add(f"/api/ingredient-overview?year={y}")
        c.add(f"/api/backlog/opportunity?year={y}")
    for e in backlog.get("equips") or []:
        c.add(f"/api/backlog/products?site={q(e['site'])}&form={q(e['form'])}&equip={q(e['equip'])}")
    c.run(4)

    print(f"[3] 기업 {len(names)}사 × 전 엔드포인트")
    for n in names:
        t = q(n)
        for ep in ("brief", "trend", "products", "forms", "forms-sales", "manufacturing", "toll", "channels", "clinical", "dossier", "dossier/status"):
            c.add(f"/api/company-{ep}?target={t}")
        c.add(f"/api/model/company?target={t}")
        for y in [str(y) for y in range(NOW - 5, NOW)]:
            c.add(f"/api/compare?target={t}&year={y}")
            for ep in ("risk", "exports", "corp-profile"):
                c.add(f"/api/company-{ep}?target={t}&year={y}")
    for r in rank:
        if r["name"] not in names:
            c.add(f"/api/model/company?target={q(r['name'])}")
    c.run()

    print("[4] 품목 상세 · 약가 포지션 · 생산처 · 이슈 기사")
    makers_q, issue_q = set(), set()
    for y in range(NOW - 3, NOW + 1):
        d = c.chunks.get(f"products_{y}", {}).get(f"/api/products?year={y}&limit=5000") or {}
        for p in d.get("products") or []:
            c.add(f"/api/product/{p['code']}?year={y}")
            c.add(f"/api/product-peers?code={q(p['code'])}")
            makers_q.add(p.get("approval_name") or p.get("product"))
            issue_q.add((p.get("ingredient") or "").split(",")[0].strip() or p.get("approval_name") or p.get("product"))
    for s in makers_q:
        if s:
            c.add("/api/product-makers?q=" + q(s))
    for s in issue_q:
        if s:
            c.add("/api/product-issues?q=" + q(s))
    c.run()

    print(f"[5] 성분 상세 {len(signals.get('rows') or [])}건")
    for r in signals.get("rows") or []:
        c.add("/api/model/molecule?mol=" + q(r["mol"]))
    c.run()
    return c


def derive_key(password: str, salt: bytes) -> bytes:
    return PBKDF2HMAC(hashes.SHA256(), 32, salt, ITER).derive(password.encode("utf-8"))


def seal_bytes(key: bytes, plain: bytes) -> bytes:
    iv = secrets.token_bytes(12)
    return iv + AESGCM(key).encrypt(iv, gzip.compress(plain, 6), None)


def app_html() -> str:
    """서버의 대시보드 원본 그대로 + 로고 인라인."""
    html = get_raw("/").decode("utf-8")
    logo = get_raw("/logo.png")
    if logo:
        html = html.replace('src="/logo.png"', 'src="data:image/png;base64,' + base64.b64encode(logo).decode("ascii") + '"')
    return html


def main():
    if get("/api/health") is None:
        sys.exit("모니터 서버(localhost:5001)가 켜져 있어야 합니다.")
    html = app_html()
    c = crawl()
    c.save()
    salt = secrets.token_bytes(16)
    key = derive_key(PASSWORD, salt)
    ddir = os.path.join(DOCS, "d")
    if os.path.isdir(ddir):
        shutil.rmtree(ddir)
    os.makedirs(ddir)
    built = dt.datetime.now().strftime("%Y%m%d%H%M")
    sizes = {}
    for name, data in c.chunks.items():
        blob = seal_bytes(key, json.dumps(data, ensure_ascii=False).encode("utf-8"))
        with open(os.path.join(ddir, name + ".enc"), "wb") as f:
            f.write(blob)
        sizes[name] = len(blob)
    app_blob = seal_bytes(key, html.encode("utf-8"))
    manifest = {"salt": base64.b64encode(salt).decode("ascii"), "iter": ITER, "built": built,
                "app": base64.b64encode(app_blob).decode("ascii"), "chunks": sorted(c.chunks)}
    os.makedirs(BUILD, exist_ok=True)
    with open(os.path.join(BUILD, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in manifest.items() if k != "app"} | {"sizes": sizes, "urls": sum(len(v) for v in c.chunks.values())}, f, ensure_ascii=False, indent=1)
    import encrypt
    encrypt.write_shell(manifest)
    total = sum(sizes.values()) / 1e6
    print(f"\n청크 {len(sizes)}개 {total:.1f}MB, URL {sum(len(v) for v in c.chunks.values()):,}건, 실패 {len(FAIL)}건")
    for p, e in FAIL[:15]:
        print("   실패:", p[:90], e)


if __name__ == "__main__":
    main()
