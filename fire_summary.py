"""逐字稿全部寄出後，直接觸發雲端「Podcast 每日摘要」排程任務。

token 在 claude.ai/code/routines 的該任務編輯頁產生，存成 GitHub secret SUMMARY_FIRE_TOKEN。
任務 ID 不是機密（沒有 token 無法觸發），直接寫在程式裡。
此 API 沒有防重複：只在連線錯誤、429、5xx 時重試，2xx 之後絕不重送。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

token = os.environ.get("SUMMARY_FIRE_TOKEN", "").strip()
ROUTINE_ID = "trig_019wDiDrwTe4nCPZ5RnckCHX"  # 雲端任務「Podcast 摘要（GitHub 觸發）」
routine = os.environ.get("SUMMARY_ROUTINE_ID", "").strip() or ROUTINE_ID
if not token:
    print("::error::缺少 secret SUMMARY_FIRE_TOKEN，無法觸發摘要")
    sys.exit(1)

url = f"https://api.anthropic.com/v1/claude_code/routines/{routine}/fire"
body = json.dumps({"text": "GitHub 逐字稿已全部寄出，請開始今天的摘要。"}).encode("utf-8")
headers = {
    "Authorization": f"Bearer {token}",
    "anthropic-version": "2023-06-01",
    "Content-Type": "application/json",
}

for attempt in range(1, 5):
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            r.read()
        print("已觸發摘要任務")
        sys.exit(0)
    except urllib.error.HTTPError as e:
        print(f"第 {attempt} 次觸發失敗：HTTP {e.code}")
        if not (e.code == 429 or e.code >= 500):
            print("::error::摘要觸發失敗（不可重試，請檢查 token）")
            sys.exit(1)
        wait = int(e.headers.get("Retry-After") or 0) or 30 * attempt
    except TimeoutError:
        print("::error::觸發請求逾時，無法確認是否已觸發，不重送（23:30 保底排程會補上）")
        sys.exit(1)
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            print("::error::觸發請求逾時，無法確認是否已觸發，不重送（23:30 保底排程會補上）")
            sys.exit(1)
        print(f"第 {attempt} 次觸發失敗（連線錯誤）")
        wait = 30 * attempt
    time.sleep(min(wait, 120))

print("::error::摘要觸發失敗（重試 4 次）")
sys.exit(1)
