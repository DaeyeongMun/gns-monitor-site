# -*- coding: utf-8 -*-
"""site/app.html + build/data.json → 비밀번호로 봉인한 docs/index.html (GitHub Pages 배포본).

봉인 방식: PBKDF2-SHA256(200,000회) → AES-256-GCM. 브라우저가 WebCrypto로 푼다.
평문은 저장소에 올라가지 않는다. 비밀번호는 환경변수 SITE_PASSWORD 또는 기본값.
live.json(Actions가 만든 실시간 공시·뉴스)도 같은 방식으로 docs/live.enc 로 봉인한다.
"""
from __future__ import annotations

import base64
import gzip
import json
import os
import secrets
import sys

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

HERE = os.path.dirname(os.path.abspath(__file__))
PASSWORD = os.environ.get("SITE_PASSWORD", "gns900118")
ITER = 200_000


def seal(plain: bytes, password: str) -> dict:
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    key = PBKDF2HMAC(hashes.SHA256(), 32, salt, ITER).derive(password.encode("utf-8"))
    ct = AESGCM(key).encrypt(iv, gzip.compress(plain, 9), None)
    b = lambda x: base64.b64encode(x).decode("ascii")   # noqa: E731
    return {"salt": b(salt), "iv": b(iv), "ct": b(ct), "iter": ITER}


SHELL = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Genuone Monitor</title><meta name="robots" content="noindex,nofollow">
<style>html,body{height:100%%;margin:0;font-family:'Noto Sans KR',system-ui,sans-serif;background:#0f1b2d;color:#fff}
.box{max-width:360px;margin:18vh auto;padding:28px 24px;background:#16263d;border-radius:16px;box-shadow:0 10px 40px rgba(0,0,0,.4)}
h1{font-size:18px;margin:0 0 6px}p{font-size:12.5px;color:#9fb0c7;margin:0 0 18px}
input{width:100%%;box-sizing:border-box;padding:12px 14px;border-radius:10px;border:1px solid #2e4160;background:#0f1b2d;color:#fff;font-size:16px}
button{width:100%%;margin-top:12px;padding:12px;border:0;border-radius:10px;background:#2e75b6;color:#fff;font-size:15px;font-weight:700}
.err{color:#ff8a8a;font-size:12.5px;margin-top:10px;min-height:16px}.foot{font-size:10.5px;color:#6f819b;margin-top:18px;line-height:1.5}</style></head>
<body><div class="box"><h1>제뉴원사이언스 내/외부 환경 모니터</h1><p>경영진 전용 · 비밀번호를 입력하세요</p>
<input id="pw" type="password" placeholder="비밀번호" autocomplete="current-password"><button id="go">열기</button><div class="err" id="err"></div>
<div class="foot">본 페이지와 데이터의 권리는 제뉴원사이언스에 귀속됩니다. 임직원 내부 업무 목적으로만 사용하며 외부 반출·공개를 금합니다.</div></div>
<script>
const P=%s;
const b64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
async function unseal(pw,pk){const key=await crypto.subtle.deriveKey({name:'PBKDF2',salt:b64(pk.salt),iterations:pk.iter,hash:'SHA-256'},await crypto.subtle.importKey('raw',new TextEncoder().encode(pw),'PBKDF2',false,['deriveKey']),{name:'AES-GCM',length:256},false,['decrypt']);
 const pt=await crypto.subtle.decrypt({name:'AES-GCM',iv:b64(pk.iv)},key,b64(pk.ct));
 const ds=new Blob([pt]).stream().pipeThrough(new DecompressionStream('gzip'));return await new Response(ds).text();}
async function open(pw){try{const html=await unseal(pw,P);sessionStorage.setItem('gns_pw',pw);document.open();document.write(html);document.close();}
 catch(e){document.getElementById('err').textContent='비밀번호가 맞지 않습니다.';}}
document.getElementById('go').onclick=()=>open(document.getElementById('pw').value);
document.getElementById('pw').addEventListener('keydown',e=>{if(e.key==='Enter')open(e.target.value)});
const saved=sessionStorage.getItem('gns_pw');if(saved)open(saved);
</script></body></html>"""


def build_index():
    app = open(os.path.join(HERE, "site", "app.html"), encoding="utf-8").read()
    data = open(os.path.join(HERE, "build", "data.json"), encoding="utf-8").read()
    html = app.replace("/*__DATA__*/", "window.__DATA=" + data + ";")
    pk = seal(html.encode("utf-8"), PASSWORD)
    os.makedirs(os.path.join(HERE, "docs"), exist_ok=True)
    out = os.path.join(HERE, "docs", "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(SHELL % json.dumps(pk))
    open(os.path.join(HERE, "docs", ".nojekyll"), "w").close()
    print("봉인:", out, "%.1f MB" % (os.path.getsize(out) / 1e6))


def build_live(src: str, out: str):
    pk = seal(open(src, "rb").read(), PASSWORD)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(pk, f)
    print("봉인:", out)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "live":
        build_live(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "docs", "live.enc"))
    else:
        build_index()
