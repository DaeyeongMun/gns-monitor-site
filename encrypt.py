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
def _password() -> str:
    """SITE_PASSWORD 환경변수(Actions secret) > build/.site_password (로컬, git 제외). 코드에 비밀번호를 두지 않는다."""
    pw = os.environ.get("SITE_PASSWORD")
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", ".site_password")
    if not pw and os.path.exists(f):
        pw = open(f, encoding="utf-8").read().strip()
    if not pw:
        sys.exit("비밀번호 없음: SITE_PASSWORD 환경변수 또는 build/.site_password 필요")
    return pw


PASSWORD = _password()
ITER = 200_000


def seal(plain: bytes, password: str) -> dict:
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    key = PBKDF2HMAC(hashes.SHA256(), 32, salt, ITER).derive(password.encode("utf-8"))
    ct = AESGCM(key).encrypt(iv, gzip.compress(plain, 9), None)
    b = lambda x: base64.b64encode(x).decode("ascii")   # noqa: E731
    return {"salt": b(salt), "iv": b(iv), "ct": b(ct), "iter": ITER}


SHELL = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Genuone Monitor</title><meta name="robots" content="noindex,nofollow">
<style>html,body{min-height:100%%;margin:0;font-family:'Noto Sans KR',system-ui,sans-serif;background:#f4f6f8;color:#14202e}
.wrap{max-width:380px;margin:11vh auto 40px;padding:0 16px;text-align:center}
.brand{font-size:12px;font-weight:800;color:#00a29a;letter-spacing:1.5px}
h1{font-size:28px;margin:6px 0 2px;letter-spacing:.5px}.sub{font-size:12.5px;color:#6b7a8c}
.bar{width:36px;height:3px;background:#00a29a;margin:12px auto 22px;border-radius:2px}
.card{background:#fff;border-radius:14px;box-shadow:0 4px 24px rgba(20,32,46,.08);padding:22px 20px;text-align:left}
.card h2{font-size:15px;margin:0 0 14px;display:flex;gap:9px;align-items:center}
.ic{width:30px;height:30px;border-radius:9px;background:#e6f6f5;display:inline-flex;align-items:center;justify-content:center;font-size:14px}
input{width:100%%;box-sizing:border-box;padding:12px 14px;border-radius:10px;border:1px solid #d5dde6;background:#fff;color:#14202e;font-size:15px;margin-bottom:8px}
input:focus{outline:2px solid #00a29a;border-color:#00a29a}
button{width:100%%;margin-top:4px;padding:12px;border:0;border-radius:10px;background:#14202e;color:#fff;font-size:15px;font-weight:700;cursor:pointer}
.err{color:#d64545;font-size:12.5px;margin-top:10px;min-height:16px}
.links{font-size:12px;color:#6b7a8c;margin-top:6px;text-align:center}.links a{color:#00a29a;cursor:pointer;font-weight:600}
.req{font-size:12px;color:#14202e;background:#f4f6f8;border-radius:8px;padding:10px 12px;margin-top:10px;line-height:1.6}
.note{font-size:11px;color:#6b7a8c;margin-top:18px;line-height:1.7}</style></head>
<body><div class="wrap"><div class="brand">GENUONE SCIENCE</div><h1>Monitor</h1><div class="sub">제뉴원사이언스 내/외부 환경 모니터</div><div class="bar"></div>
<div class="card"><h2><span class="ic">🔒</span><span id="lead">로그인</span></h2>
<input id="uid" placeholder="사번" autocomplete="username" style="display:none">
<input id="pw" type="password" placeholder="비밀번호" autocomplete="current-password"><button id="go">로그인</button><div class="err" id="err"></div>
<div class="links" id="links" style="display:none"><a id="reqA">사용 신청</a></div>
<div class="req" id="req" style="display:none">전략기획팀에 사번·이름을 알려 주세요. 초기 비밀번호는 사번입니다.</div></div>
<div class="note">본 페이지와 데이터의 권리는 제뉴원사이언스에 귀속됩니다. 임직원 내부 업무 목적으로만 사용하며 외부 반출·공개를 금합니다.<br>데이터 기준 %s</div></div>
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
  if(path==='/api/cso-tree') return 'cso';
  if(path.startsWith('/api/product/')) return 'pd_'+(h(path.split('/')[3])%%24);
  if(path==='/api/product-peers') return 'pd_'+(h(Q.get('code')||'')%%24);
  if(path==='/api/product-makers'||path==='/api/product-issues') return 'pq_'+(h(Q.get('q')||'')%%24);
  if(path==='/api/model/molecule') return 'mol_'+(h(Q.get('mol')||'')%%12);
  if(path.startsWith('/api/company-')||path==='/api/compare'||path==='/api/model/company') return 'co_'+(h(Q.get('target')||'')%%32);
  if(path.startsWith('/api/tool/')) return 'tool_'+path.split('/')[3];
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
// 사용자 = docs/users.json {ks, users:{해시(사번): {봉인, role, menus, m}}} — 빌드 없이 관리자 화면이 GitHub에 바로 저장한다.
// 봉인 = '사번:비밀번호'로 열리는 {사이트 비밀번호, 사번, 이름} · m = 사이트 키(ks)로 봉인한 {사번, 이름, 등록일…} (관리자 목록용)
let USERS={}, KS='', UMODE=false, UREADY=null;
const LS={get:k=>{ try{ return localStorage.getItem(k); }catch(e){ return null; } }, set:(k,v)=>{ try{ localStorage.setItem(k,v); }catch(e){} }, del:k=>{ try{ localStorage.removeItem(k); }catch(e){} }};
const e64=u=>{ let s=''; u.forEach(c=>s+=String.fromCharCode(c)); return btoa(s); };
const TE=new TextEncoder();
async function hid(s){ const b=await crypto.subtle.digest('SHA-256',TE.encode('gns:'+s)); return [...new Uint8Array(b)].map(x=>x.toString(16).padStart(2,'0')).join('').slice(0,16); }
async function kdf(secret,salt,iter,use){ return crypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:iter,hash:'SHA-256'},await crypto.subtle.importKey('raw',TE.encode(secret),'PBKDF2',false,['deriveKey']),{name:'AES-GCM',length:256},false,use); }
async function unwrap(w,id,pw){ return JSON.parse(await dec(await derive(id+':'+pw,w.salt,w.iter),b64(w.iv),b64(w.ct))); }
async function wrapNew(id,pw,info){
  const salt=crypto.getRandomValues(new Uint8Array(16)), iv=crypto.getRandomValues(new Uint8Array(12)), k=await kdf(id+':'+pw,salt,P.iter,['encrypt']);
  const gz=new Uint8Array(await new Response(new Blob([JSON.stringify(info)]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer());
  return {salt:e64(salt),iv:e64(iv),ct:e64(new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM',iv},k,gz))),iter:P.iter};
}
const loadUsers=async()=>{ const r=await realFetch('users.json?v='+Date.now(),{cache:'no-store'}); if(!r.ok) throw new Error('users '+r.status); const j=await r.json(); USERS=j.users||{}; KS=j.ks||''; UMODE=Object.keys(USERS).length>0; };
UREADY=loadUsers();
// 이 기기에서 바꾼 비밀번호: 관리자가 반영하기 전까지 localStorage 봉인(base = 그때 공개 봉인)을 쓴다. 공개 봉인이 바뀌면 버린다.
function localWrap(h){ try{ const o=JSON.parse(LS.get('gns_wrap:'+h)||'null'); if(o&&o.base===USERS[h].ct) return o; if(o) LS.del('gns_wrap:'+h); }catch(e){} return null; }
async function secApi(user){
  if(!user) return null;
  const sk=KS?await kdf(PW,b64(KS),P.iter,['encrypt','decrypt']):null;
  return {
    seal:async o=>{ const iv=crypto.getRandomValues(new Uint8Array(12)), ct=new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM',iv},sk,TE.encode(JSON.stringify(o)))); const a=new Uint8Array(12+ct.length); a.set(iv); a.set(ct,12); return e64(a); },
    unseal:async s=>{ const a=b64(s); return JSON.parse(new TextDecoder().decode(await crypto.subtle.decrypt({name:'AES-GCM',iv:a.slice(0,12)},sk,a.slice(12)))); },
    wrap:(id,pw,name)=>wrapNew(id,pw,{pw:PW,id,name}),
    hid, ks:KS,
    pwChange:async(cur,nw)=>{ const h=await hid(user.id), pub=USERS[h], lw=localWrap(h);
      await unwrap(lw||pub,user.id,cur);
      const w=await wrapNew(user.id,nw,{pw:PW,id:user.id,name:user.name});
      LS.set('gns_wrap:'+h,JSON.stringify({...w,base:pub.ct})); user.dflt=false; LS.set('gns_user',JSON.stringify(user));
      return btoa(JSON.stringify({id:user.id,wrap:w})); }
  };
}
async function open(pw,user){
  const err=document.getElementById('err'); err.textContent='여는 중…';
  try{ KEY=await derive(pw,P.salt,P.iter); PW=pw; const app=b64(P.app); const html=await dec(KEY,app.slice(0,12),app.slice(12));
    LS.set('gns_pw',pw); if(user) LS.set('gns_user',JSON.stringify(user));
    await Promise.race([loadLive(),new Promise(r=>setTimeout(r,6000))]);
    window.fetch=shim; window.__GNS_STATIC={built:P.built,live:LIVE&&LIVE.fetched_at}; window.__GNS_USER=user||null;
    window.__GNS_SEC=await secApi(user);
    document.open(); document.write(html); document.close();
  }catch(e){ LS.del('gns_pw'); LS.del('gns_user'); err.textContent=UMODE?'사번 또는 비밀번호가 맞지 않습니다.':'비밀번호가 맞지 않습니다.'; }
}
// 이름·직급 = 관리자 목록용 봉인(m) (사이트 키로 연다)
async function metaOf(pw,pub){ try{ const sk=await kdf(pw,b64(KS),P.iter,['decrypt']), a=b64(pub.m); return JSON.parse(new TextDecoder().decode(await crypto.subtle.decrypt({name:'AES-GCM',iv:a.slice(0,12)},sk,a.slice(12)))); }catch(e){ return {}; } }
async function login(){
  const err=document.getElementById('err'), id=document.getElementById('uid').value.trim(), pw=document.getElementById('pw').value;
  try{ await UREADY; }catch(e){ err.textContent='사용자 목록을 불러오지 못했습니다. 잠시 뒤 다시 시도하세요.'; return; }
  if(!UMODE) return open(pw);
  err.textContent='확인 중…';
  try{ const h=await hid(id); let pub=USERS[h], lw=localWrap(h), info=null;
    try{ if(!pub) throw 0; info=await unwrap(lw||pub,id,pw); }
    catch(e){ await loadUsers(); pub=USERS[h]; if(!pub) throw 0; lw=localWrap(h); info=await unwrap(lw||pub,id,pw); }   // 방금 등록·변경된 사용자 — 목록을 다시 받아 한 번 더
    const mt=await metaOf(info.pw,pub);                             // 이름·직급은 관리자가 고친 값(m) 우선
    await open(info.pw,{id:info.id,name:mt.name||info.name,rank:mt.rank||'',role:pub.role,menus:pub.menus,dflt:!lw&&pw===id});
  }catch(e){ err.textContent='사번 또는 비밀번호가 맞지 않습니다.'; }
}
document.getElementById('go').onclick=login;
['uid','pw'].forEach(i=>document.getElementById(i).addEventListener('keydown',e=>{ if(e.key==='Enter') login(); }));
document.getElementById('reqA').onclick=()=>{ const r=document.getElementById('req'); r.style.display=r.style.display?'':'none'; };
(async()=>{ try{ await UREADY; }catch(e){ document.getElementById('err').textContent='사용자 목록을 불러오지 못했습니다. 새로고침 해 주세요.'; return; }
  if(UMODE){ document.getElementById('uid').style.display=''; document.getElementById('lead').textContent='로그인'; document.getElementById('links').style.display=''; }
  const saved=LS.get('gns_pw'); if(!saved) return; let su=null; try{ su=JSON.parse(LS.get('gns_user')||'null'); }catch(e){}
  if(!UMODE) return open(saved);
  const pub=su&&USERS[await hid(su.id)]; if(!pub){ LS.del('gns_pw'); LS.del('gns_user'); return; }   // 삭제된 사용자 → 다시 로그인
  const mt=await metaOf(saved,pub); open(saved,{...su,name:mt.name||su.name,rank:mt.rank||'',role:pub.role,menus:pub.menus}); })();
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
