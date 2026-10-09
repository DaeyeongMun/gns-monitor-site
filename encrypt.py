# -*- coding: utf-8 -*-
"""봉인 셸(docs/index.html) 생성 + live.json 봉인.

docs/index.html = 비밀번호 입력 화면 + (봉인된 대시보드 원본) + fetch 가로채기(shim).
비밀번호 → PBKDF2-SHA256(200,000회) → AES-256-GCM 키. 대시보드와 docs/d/*.enc 청크를 같은 키로 푼다.
live.enc(Actions 가 매일 만드는 공시·주가·뉴스)는 seal() 로 따로 봉인되며 열람 시 겹쳐 보여준다.
"""
from __future__ import annotations

import base64
import gzip
import json
import os
import secrets
import sys

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

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
button{width:100%%;margin-top:12px;padding:12px;border:0;border-radius:10px;background:#00a29a;color:#fff;font-size:15px;font-weight:700}
.err{color:#ff8a8a;font-size:12.5px;margin-top:10px;min-height:16px}.foot{font-size:10.5px;color:#6f819b;margin-top:18px;line-height:1.5}</style></head>
<body><div class="box"><h1>제뉴원사이언스 내/외부 환경 모니터</h1><p>경영진 전용 · 비밀번호를 입력하세요</p>
<input id="pw" type="password" placeholder="비밀번호" autocomplete="current-password"><button id="go">열기</button><div class="err" id="err"></div>
<div class="foot">본 페이지와 데이터의 권리는 제뉴원사이언스에 귀속됩니다. 임직원 내부 업무 목적으로만 사용하며 외부 반출·공개를 금합니다.<br>데이터 기준 %s</div></div>
<script>
(function(){
const P=%s;
const b64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
const realFetch=window.fetch.bind(window);
let KEY=null, PW='', LIVE=null; const C={}, PEND={};
async function derive(pw,salt,iter){ return crypto.subtle.deriveKey({name:'PBKDF2',salt:b64(salt),iterations:iter,hash:'SHA-256'},await crypto.subtle.importKey('raw',new TextEncoder().encode(pw),'PBKDF2',false,['deriveKey']),{name:'AES-GCM',length:256},false,['decrypt']); }
async function dec(key,iv,ct){ const pt=await crypto.subtle.decrypt({name:'AES-GCM',iv},key,ct); const ds=new Blob([pt]).stream().pipeThrough(new DecompressionStream('gzip')); return await new Response(ds).text(); }
function h(s){ let a=0; for(const ch of String(s)) a+=ch.codePointAt(0); return a; }
function chunkOf(path,Q){
  if(path==='/api/products') return 'products_'+(Q.get('year')||'');
  if(path==='/api/ingredient-overview') return 'ingr_'+(Q.get('year')||'');
  if(path==='/api/backlog/opportunity') return 'oppty_'+(Q.get('year')||'');
  if(path==='/api/backlog/products') return 'bl';
  if(path.startsWith('/api/product/')) return 'pd_'+(h(path.split('/')[3])%%24);
  if(path==='/api/product-peers') return 'pd_'+(h(Q.get('code')||'')%%24);
  if(path==='/api/product-makers'||path==='/api/product-issues') return 'pq_'+(h(Q.get('q')||'')%%24);
  if(path==='/api/model/molecule') return 'mol_'+(h(Q.get('mol')||'')%%12);
  if(path.startsWith('/api/company-')||path==='/api/compare'||path==='/api/model/company') return 'co_'+(h(Q.get('target')||'')%%32);
  return 'core';
}
async function loadChunk(name){
  if(C[name]) return C[name];
  if(!P.chunks.includes(name)) return (C[name]={});
  if(!PEND[name]) PEND[name]=(async()=>{ const r=await realFetch('d/'+name+'.enc?v='+P.built); if(!r.ok) throw new Error('chunk '+name); const buf=new Uint8Array(await r.arrayBuffer()); return (C[name]=JSON.parse(await dec(KEY,buf.slice(0,12),buf.slice(12)))); })();
  return PEND[name];
}
async function loadLive(){ try{ const r=await realFetch('live.enc?v='+Date.now()); if(!r.ok) return; const pk=await r.json(); const k=await derive(PW,pk.salt,pk.iter); LIVE=JSON.parse(await dec(k,b64(pk.iv),b64(pk.ct))); }catch(e){ LIVE=null; } }
const fmtD=s=>{ const d=new Date(s); return isNaN(d)?String(s||''):d.getFullYear()+'.'+String(d.getMonth()+1).padStart(2,'0')+'.'+String(d.getDate()).padStart(2,'0'); };
const mapNews=n=>({title:n.title,link:n.url,pub_date:fmtD(n.date),source:n.source,query:n.query,summary:''});
function overlay(path,Q,obj){
  if(!LIVE||!obj||typeof obj!=='object') return obj;
  const mk=(LIVE.market||{}), st=mk.stocks||{}, ix=mk.indices||{};
  if(path==='/api/issues'){ const o={...obj};
    if((LIVE.news||[]).length) o.news=LIVE.news.map(mapNews).slice(0,30);
    if(LIVE.dart) o.self_disclosures=LIVE.dart.filter(d=>/제뉴원|제뉴파마/.test(d.company||'')).map(d=>({title:d.title,date:d.date,url:d.url,submitter:d.company}));
    o.peers=(o.peers||[]).map(p=>st[p.name]?{...p,latest:{...(p.latest||{}),...st[p.name],name:p.name}}:p);
    o.indices=(o.indices||[]).map(i=>ix[i.name]?{...i,latest:{...(i.latest||{}),...ix[i.name],name:i.name}}:i);
    if(LIVE.fetched_at) o.as_of=LIVE.fetched_at.slice(0,10); return o; }
  if(path==='/api/news'&&(LIVE.news||[]).length) return {...obj,articles:LIVE.news.map(mapNews),note:'GitHub 자동 수집 '+LIVE.fetched_at};
  if(path==='/api/company-quotes'){ const o={...obj}; for(const k in o){ if(st[k]&&o[k]) o[k]={...o[k],...st[k],name:k}; } return o; }
  if(path==='/api/company-brief'&&LIVE.dart){ const t=Q.get('target')||''; const d=LIVE.dart.filter(x=>x.company===t); const n=(LIVE.news||[]).filter(x=>x.query===t); const o={...obj}; if(d.length) o.disclosures=d; if(n.length) o.news=n.map(mapNews); return o; }
  if(path==='/api/data-status'){ const o={...obj}; o.items=(o.items||[]).map(it=>/주가|공시|뉴스/.test(it.name)?{...it,detail:'GitHub Actions 매일 07:30 자동',updated:(LIVE.fetched_at||'')+' 수집'}:it); return o; }
  return obj;
}
const J=(o,st)=>new Response(JSON.stringify(o),{status:st||200,headers:{'Content-Type':'application/json'}});
async function shim(input,init){
  const u=typeof input==='string'?input:(input&&input.url)||'';
  if(!u.startsWith('/api/')) return realFetch(input,init);
  const method=((init&&init.method)||'GET').toUpperCase();
  if(method!=='GET'){ const MSG='정적 배포본에서는 지원하지 않는 기능입니다 (사내 모니터 서버판 전용)';
    if(u.startsWith('/api/snapshot')) return new Response(MSG,{status:405});            // 스냅샷 저장: 화면이 '실패'로 표시
    return J({ok:false,state:'error',error:MSG,message:MSG},405); }                      // 업로드·조사: 화면이 메시지 표시
  let key; try{ key=decodeURIComponent(u); }catch(e){ key=u; } const path=key.split('?')[0]; const Q=new URLSearchParams(u.split('?')[1]||'');   // 쿼리는 인코딩된 원문으로 파싱 ('+' 보존)
  if(path==='/api/issues') key='/api/issues';
  if(path==='/api/news') key='/api/news';
  if(path==='/api/company-search'){ const t=(Q.get('q')||'').toLowerCase(); const co=(await loadChunk('core'))['/api/companies']||{groups:{}};
    const res=[]; for(const [cat,arr] of Object.entries(co.groups||{})) for(const x of arr) if(x.name.toLowerCase().includes(t)) res.push({name:x.name,category:cat,registered:true});
    return J({results:res.slice(0,12)}); }
  if(path.startsWith('/api/snapshot/')) return J({error:'정적 배포본에는 스냅샷이 없습니다'},404);
  let ch; try{ ch=await loadChunk(chunkOf(path,Q)); }catch(e){ return J({error:'데이터 청크를 불러오지 못했습니다: '+e.message},502); }
  let obj=ch[key];
  if(obj===undefined&&path==='/api/compare'){ obj=ch[key.replace(/&year=\\d+$/,'&year=')]; }
  if(obj===undefined) return J({error:'정적 배포본에 포함되지 않은 조회입니다 ('+key+')'},404);
  if(obj&&typeof obj==='object'&&obj.__st) return J(obj.__b,obj.__st);
  return J(overlay(path,Q,obj));
}
async function open(pw){
  const err=document.getElementById('err'); err.textContent='여는 중…';
  try{ KEY=await derive(pw,P.salt,P.iter); PW=pw; const app=b64(P.app); const html=await dec(KEY,app.slice(0,12),app.slice(12));
    sessionStorage.setItem('gns_pw',pw);
    await Promise.race([loadLive(),new Promise(r=>setTimeout(r,6000))]);
    window.fetch=shim; window.__GNS_STATIC={built:P.built,live:LIVE&&LIVE.fetched_at};
    document.open(); document.write(html); document.close();
  }catch(e){ err.textContent='비밀번호가 맞지 않습니다.'; }
}
document.getElementById('go').onclick=()=>open(document.getElementById('pw').value);
document.getElementById('pw').addEventListener('keydown',e=>{ if(e.key==='Enter') open(e.target.value); });
const saved=sessionStorage.getItem('gns_pw'); if(saved) open(saved);
})();
</script></body></html>"""


def write_shell(manifest: dict):
    """build_static.py 가 만든 manifest(salt·iter·built·app·chunks) → docs/index.html."""
    os.makedirs(os.path.join(HERE, "docs"), exist_ok=True)
    out = os.path.join(HERE, "docs", "index.html")
    built = manifest["built"]
    with open(out, "w", encoding="utf-8") as f:
        f.write(SHELL % (f"{built[:4]}-{built[4:6]}-{built[6:8]} {built[8:10]}:{built[10:12]} 빌드", json.dumps(manifest, ensure_ascii=False)))
    open(os.path.join(HERE, "docs", ".nojekyll"), "w").close()
    print("봉인 셸:", out, "%.2f MB" % (os.path.getsize(out) / 1e6))


def build_live(src: str, out: str):
    pk = seal(open(src, "rb").read(), PASSWORD)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(pk, f)
    print("봉인:", out)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "live":
        build_live(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "docs", "live.enc"))
    else:
        import build_static
        build_static.main()
