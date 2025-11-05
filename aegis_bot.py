#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, json, time, re, hashlib, traceback, requests, pyotp, tempfile, shutil

TOKEN  = "8597122120:AAGUp_Zerivg4swO39_V8_prjmzYBtsAakA"
ADMINS = {6171834060}
ROOT   = os.path.expanduser("~/Christ SMS")

ALLOWED_PATH  = os.path.join(ROOT, "allowed_chats.json")
DISABLED_PATH = os.path.join(ROOT, "disabled_chats.json")
LABELS_PATH   = os.path.join(ROOT, "users_labels.json")
AEGIS_PATH    = os.path.join(ROOT, "aegis-export-plain-20251101-015408.json")
AEGIS_LATEST  = os.path.join(ROOT, "aegis-export-latest.json")

def safe_json(path, default):
    try:
        with open(path,"r",encoding="utf-8") as f: return json.load(f)
    except Exception:
        try: 
            os.makedirs(os.path.dirname(path),exist_ok=True)
            with open(path,"w",encoding="utf-8") as f: json.dump(default,f)
        except Exception: pass
        return default
def save_json(p,d):
    try:
        t=p+".tmp"
        with open(t,"w",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2)
        os.replace(t,p)
    except Exception: pass

def allowed(): return safe_json(ALLOWED_PATH,[])
def set_allowed(l): save_json(ALLOWED_PATH,sorted(set(l)))
def disabled(): return safe_json(DISABLED_PATH,{})
def set_disabled_map(m): save_json(DISABLED_PATH,m)
def labels(): return safe_json(LABELS_PATH,{})

def is_disabled(uid): return disabled().get(str(uid),False)
def add_allowed(uid): l=set(allowed()); l.add(uid); set_allowed(l)
def remove_allowed(uid): l=set(allowed()); l.discard(uid); set_allowed(l)
def disable_user(uid): m=disabled(); m[str(uid)]=True; set_disabled_map(m)
def enable_user(uid): m=disabled(); m.pop(str(uid),None); set_disabled_map(m)
def set_label(uid,label): m=labels(); m[str(uid)]=label.strip(); save_json(LABELS_PATH,m)
def get_label(uid): return labels().get(str(uid),"")

def send(method,json_data):
    for _ in range(3):
        try:
            r=requests.post(f"https://api.telegram.org/bot{TOKEN}/{method}",json=json_data,timeout=30)
            return r.json()
        except Exception: time.sleep(2)
    return {"ok":False}

def get(method,params=None):
    for _ in range(3):
        try:
            r=requests.get(f"https://api.telegram.org/bot{TOKEN}/{method}",params=params,timeout=30)
            return r.json()
        except Exception: time.sleep(2)
    return {"ok":False}

def send_msg(cid,text,markup=None):
    body={"chat_id":cid,"text":text,"disable_web_page_preview":True}
    if markup: body["reply_markup"]=markup
    send("sendMessage",body)

def get_file(fid):
    info=get("getFile",{"file_id":fid})
    if not info.get("ok"): raise Exception(info.get("description"))
    path=info["result"]["file_path"]
    u=f"https://api.telegram.org/file/bot{TOKEN}/{path}"
    d=requests.get(u,timeout=60).content
    return d

def digest_from_algo(a): return {"SHA1":hashlib.sha1,"SHA256":hashlib.sha256,"SHA512":hashlib.sha512}.get((a or"SHA1").upper(),hashlib.sha1)
def load_accounts(p):
    try: data=json.load(open(p,encoding="utf-8"))
    except Exception: return []
    ent=data.get("db",{}).get("entries") or data.get("entries") or data.get("accounts") or []
    res=[]
    for e in ent:
        i=e.get("info")or{}
        s=i.get("secret")or e.get("secret")or(e.get("data")or{}).get("secret")
        if not s: continue
        res.append({"secret":s,"name":(e.get("name")or i.get("name")or"").strip(),"issuer":(e.get("issuer")or i.get("issuer")or"").strip(),"digits":int(i.get("digits")or e.get("digits")or 6),"period":int(i.get("period")or e.get("period")or 30),"algo":(i.get("algo")or e.get("algo")or"SHA1").upper()})
    return res
def gen_code(e): return pyotp.TOTP(e["secret"],digits=e["digits"],interval=e["period"],digest=digest_from_algo(e["algo"])).now()
def find_entry(q):
    q=q.strip()
    if not q: return None
    p=re.compile(rf"^{re.escape(q)}($|[\s:/\-])",re.I)
    for e in ACCOUNTS:
        if p.search(e["name"]): return e
    return None

def resolve_chat(arg):
    arg=(arg or"").strip()
    if arg.lstrip("-").isdigit(): return int(arg)
    if arg.startswith("@"):
        r=get("getChat",{"chat_id":arg})
        if r.get("ok"): return int(r["result"]["id"])
        return None
    return None

def kb():
    return {"inline_keyboard":[
        [{"text":"📋 Список","callback_data":"list"}],
        [{"text":"➕ Разрешить","callback_data":"allow"},{"text":"➖ Удалить","callback_data":"unallow"}],
        [{"text":"⛔️ Отключить","callback_data":"off"},{"text":"✅ Включить","callback_data":"on"}],
        [{"text":"🏷 Метка","callback_data":"label"}],
        [{"text":"🔄 Обновить базу (Aegis)","callback_data":"reload"}]
    ]}

STATE={}
def process_admin(uid,cid,text):
    st=STATE.pop(uid,None)
    if not st: return False
    op=st
    try:
        if op in("allow","unallow","off","on","label"):
            if op=="label":
                p=text.split(maxsplit=1)
                if len(p)<2: send_msg(cid,"Формат: @user <имя>",kb());return True
                t=resolve_chat(p[0])
                if not t: send_msg(cid,"Ошибка username.",kb());return True
                set_label(t,p[1]); send_msg(cid,f"Метка сохранена {p[0]} ✔️",kb());return True
            t=resolve_chat(text)
            if not t: send_msg(cid,"Ошибка username или ID.",kb());return True
            if op=="allow": add_allowed(t); enable_user(t); send_msg(cid,f"{text} разрешён ✅",kb())
            elif op=="unallow": remove_allowed(t); enable_user(t); send_msg(cid,f"{text} удалён 🗑",kb())
            elif op=="off": disable_user(t); send_msg(cid,f"{text} отключён ⛔️",kb())
            elif op=="on": enable_user(t); send_msg(cid,f"{text} включён ✅",kb())
            return True
    except Exception as e: send_msg(cid,f"Ошибка: {e}",kb())
    return True

def render_list():
    l=allowed()
    if not l: return "Список пуст."
    m=labels(); d=disabled()
    out=[]
    for i in l:
        n=m.get(str(i),"")
        st="OFF" if d.get(str(i)) else "ON"
        out.append(f"{i} {n} [{st}]")
    return "Участники:\n"+"\n".join(out)

def handle_text(cid,uid,txt):
    if uid in ADMINS and process_admin(uid,cid,txt): return
    e=find_entry(txt)
    if not e: send_msg(cid,"Код не найден."); return
    try: send_msg(cid,gen_code(e))
    except Exception as e: send_msg(cid,f"Ошибка: {e}")

def notify_admins(t):
    for a in ADMINS:
        try: send_msg(a,t,kb())
        except Exception: pass

def main():
    global ACCOUNTS
    os.makedirs(ROOT,exist_ok=True)
    ACCOUNTS=load_accounts(AEGIS_PATH)
    notify_admins(f"✅ Бот запущен. {len(ACCOUNTS)} записей.")

    off=None
    while True:
        try:
            r=get("getUpdates",{"timeout":50,"offset":off})
            if not r.get("ok"): time.sleep(3); continue
            u=r.get("result",[])
            if u: off=u[-1]["update_id"]+1
            for x in u:
                cb=x.get("callback_query")
                if cb:
                    d=cb.get("data"); f=cb["from"]["id"]; c=cb["message"]["chat"]["id"]
                    if f not in ADMINS: continue
                    if d=="list": send_msg(c,render_list(),kb())
                    elif d in("allow","unallow","off","on","label"): STATE[f]=d; send_msg(c,"Введи @username или ID",kb())
                    elif d=="reload": send_msg(c,"Пришли .json из Aegis",kb())
                    continue
                m=x.get("message")or{}
                if not m: continue
                cid=m["chat"]["id"]; uid=(m.get("from")or{}).get("id"); txt=(m.get("text")or"").strip()
                if m.get("document") and uid in ADMINS:
                    try:
                        d=get_file(m["document"]["file_id"])
                        open(AEGIS_LATEST,"wb").write(d)
                        ACCOUNTS=load_accounts(AEGIS_LATEST)
                        send_msg(cid,f"База обновлена. {len(ACCOUNTS)} записей.",kb())
                    except Exception as e: send_msg(cid,f"Ошибка загрузки: {e}",kb())
                    continue
                if uid not in ADMINS:
                    if cid not in allowed(): send_msg(cid,"Доступ запрещён."); continue
                    if is_disabled(cid): continue
                if txt in("/start","/help","?") and uid in ADMINS: send_msg(cid,"Меню:",kb()); continue
                if txt: handle_text(cid,uid,txt)
        except Exception as e:
            print("loop err",e)
            time.sleep(3)

if __name__=="__main__":
    try: main()
    except KeyboardInterrupt: pass
