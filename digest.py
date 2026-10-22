"""每日 podcast 新集數：偵測 → 下載 → Whisper 轉錄 → 每集一封逐字稿信寄到 Gmail。

雲端摘要任務（每天 21:00 前後）再從 Gmail 讀這些信寫摘要。

公開 repo 注意事項：
- 執行紀錄人人可看：只印集數、長度、耗時，不印逐字稿內容。
- 逐字稿與音檔一律不寫進 repo，只寄信。
- 收件與寄件信箱、Gmail 應用程式密碼都放在 secrets。

環境變數：
  GMAIL_USER / GMAIL_APP_PASSWORD / MAIL_TO   寄信用（secrets）
  DRYRUN=1      只偵測、不轉錄不寄信
  MAX_AGE_H     第一次執行（或某節目第一次出現）只收這麼多小時內的集數，預設 36
  TIME_BUDGET_MIN  本次轉錄總時間上限（分鐘），預設 300（GitHub 單次執行上限 6 小時）
"""
import calendar
import json
import os
import re
import smtplib
import ssl
import subprocess
import sys
import tempfile
import time
from email.message import EmailMessage
from pathlib import Path

import feedparser

ROOT = Path(__file__).parent
FEEDS = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))
STATE = ROOT / "state" / "seen.json"
MAX_AGE_H = float(os.environ.get("MAX_AGE_H", "36"))
TIME_BUDGET = float(os.environ.get("TIME_BUDGET_MIN", "300")) * 60
DRYRUN = os.environ.get("DRYRUN") == "1"
START = time.time()
ONLY = os.environ.get("ONLY", "")          # 測試用：只處理名稱含此字串的節目
LIMIT = int(os.environ.get("LIMIT", "0"))  # 測試用：最多處理幾集

PROMPT = "以下是台灣財經、科技節目的逐字稿，使用繁體中文與台灣用語，包含台積電、輝達、聯發科等公司名稱。"


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def dur_sec(s):
    v = 0
    for x in str(s or "0").split(":"):
        if x.strip().isdigit():
            v = v * 60 + int(x)
    return v


def enclosure(e):
    for l in e.get("links", []):
        if l.get("rel") == "enclosure":
            return l.get("href")
    return None


def strip_html(s):
    s = re.sub(r"<br\s*/?>|</p>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def find_new(state):
    now = time.time()
    todo = []
    for f in FEEDS:
        name = f["name"]
        if ONLY and ONLY not in name:
            continue
        d = feedparser.parse(f["feed"])
        if not d.entries:
            print(f"::warning::{name}：RSS 讀不到集數")
            continue
        seen = state.setdefault(name, {"guids": []})
        first_time = not seen["guids"]
        for e in d.entries[:15]:
            gid = e.get("id") or e.get("guid") or enclosure(e)
            if not gid or gid in seen["guids"]:
                continue
            t = e.get("published_parsed")
            ts = calendar.timegm(t) if t else now
            if first_time and now - ts > MAX_AGE_H * 3600:
                seen["guids"].append(gid)  # 首次只建基準，不補舊集
                continue
            url = enclosure(e)
            if not url:
                continue
            todo.append({
                "show": name, "guid": gid, "title": e.get("title", "").strip(),
                "published": time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts + 8 * 3600)),
                "ts": ts, "duration": dur_sec(e.get("itunes_duration")),
                "link": e.get("link", ""), "audio": url,
                "notes": strip_html(e.get("summary", "")),
            })
    todo.sort(key=lambda x: x["ts"])
    return todo[:LIMIT] if LIMIT else todo


_model = None
_cc = None

# Whisper 在無聲或片尾常幻聽出這類字幕組字樣，轉錄後刪除
HALLUCINATION = re.compile(r"(字幕(志願者|由|製作|提供)[^。\n]{0,20}|請不吝點贊[^。\n]{0,20}|明鏡與點點欄目|中文字幕[^。\n]{0,10})")


def to_trad(text):
    """Whisper 不帶前文時常吐簡體；統一轉成台灣正體與用語。"""
    global _cc
    if _cc is None:
        from opencc import OpenCC
        _cc = OpenCC("s2twp")
    return _cc.convert(text)


def transcribe(path):
    global _model
    from faster_whisper import WhisperModel
    if _model is None:
        _model = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8",
                              cpu_threads=os.cpu_count() or 2)
    segs, info = _model.transcribe(path, language="zh", vad_filter=True,
                                   initial_prompt=PROMPT, condition_on_previous_text=False)
    lines, last_mark = [], -600
    for s in segs:
        if s.start - last_mark >= 300:  # 每 5 分鐘插一個時間標記，方便回頭對照
            m = int(s.start // 60)
            lines.append(f"\n[{m // 60:02d}:{m % 60:02d}]")
            last_mark = s.start
        lines.append(s.text.strip())
    text = HALLUCINATION.sub("", to_trad("".join(lines)))
    return text.strip(), info.duration


def send(ep, transcript, audio_sec):
    user = os.environ["GMAIL_USER"].strip()
    pwd = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "").strip()
    to = os.environ["MAIL_TO"].strip()
    mins = round((audio_sec or ep["duration"]) / 60)
    body = (
        f"節目：{ep['show']}\n集名：{ep['title']}\n發布：{ep['published']}（台北時間）\n"
        f"長度：{mins} 分鐘\n連結：{ep['link']}\n\n"
        f"===== 節目說明（RSS）=====\n{ep['notes']}\n\n"
        f"===== 逐字稿（Whisper 自動轉錄，同音字錯誤未校正）=====\n{transcript}\n"
    )
    msg = EmailMessage()
    msg["Subject"] = f"[podcast-digest] {ep['show']}｜{ep['title']}"[:240]
    msg["From"] = user
    msg["To"] = to
    msg.set_content(body)
    for i in range(3):
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
                s.login(user, pwd)
                s.send_message(msg)
            return len(body)
        except Exception as ex:
            print(f"寄信第 {i + 1} 次失敗：{type(ex).__name__} {str(ex)[:200]}")
            time.sleep(20)
    raise RuntimeError("寄信失敗")


def check_smtp():
    """轉錄前先確認能登入 Gmail，避免轉完才發現寄不出去（10/22 首跑即因此白轉 4 集）。"""
    user = os.environ.get("GMAIL_USER", "").strip()
    pwd = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not user or not pwd or not os.environ.get("MAIL_TO", "").strip():
        sys.exit("::error::GMAIL_USER／GMAIL_APP_PASSWORD／MAIL_TO 有空值，請檢查 secrets")
    print(f"應用程式密碼長度：{len(pwd)}（Gmail 應為 16）")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
            s.login(user, pwd)
    except Exception as ex:
        sys.exit(f"::error::Gmail 登入失敗：{type(ex).__name__} {str(ex)[:200]}")
    print("Gmail 登入測試通過")


def main():
    state = load_state()
    todo = find_new(state)
    print(f"新集數 {len(todo)} 集，共約 {sum(e['duration'] for e in todo) / 60:.0f} 分鐘")
    for ep in todo:
        print(f"- {ep['show']}｜{ep['title']}（{ep['duration'] // 60} 分）")
    if DRYRUN:
        print("DRYRUN：不轉錄、不寄信、不更新狀態")
        return
    if todo:
        check_smtp()
    save_state(state)  # 先存「首次基準」

    def process(ep):
        with tempfile.TemporaryDirectory() as tmp:
            raw = f"{tmp}/a"
            t0 = time.time()
            subprocess.run(["curl", "-sSfL", "--retry", "3", "-o", raw, ep["audio"]], check=True)
            text, sec = transcribe(raw)  # faster-whisper 內建 PyAV 解碼，不需 ffmpeg
            n = send(ep, text, sec)
            print(f"完成 {ep['show']}｜{ep['title']}：音檔 {sec / 60:.0f} 分，耗時 {(time.time() - t0) / 60:.1f} 分，信件 {n} 字元")
        state[ep["show"]]["guids"].append(ep["guid"])
        state[ep["show"]]["guids"] = state[ep["show"]]["guids"][-50:]
        save_state(state)

    done, retry = 0, []
    for attempt, queue in ((1, todo), (2, None)):
        if attempt == 2:
            queue, retry = retry, []
            if queue:
                print(f"重試失敗的 {len(queue)} 集")
        for ep in queue:
            if time.time() - START > TIME_BUDGET:
                print(f"::warning::已達時間上限，剩下的集數留給下次")
                break
            try:
                process(ep)
                done += 1
            except Exception as ex:
                print(f"::warning::{ep['show']}｜{ep['title']} 第 {attempt} 次失敗：{type(ex).__name__}")
                retry.append(ep)
    print(f"本次完成 {done} 集，失敗 {len(retry)} 集")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"done={done}\nfailed={len(retry)}\n")


if __name__ == "__main__":
    main()
