# podcast-digest

每天抓 `feeds.json` 裡節目的新集數，用 Whisper 轉逐字稿，每集一封信寄到指定信箱；摘要由另一個雲端排程從信箱讀取後撰寫。

逐字稿與音檔不存進本 repo。`state/seen.json` 只記錄已處理的集數識別碼。

需要的 secrets：`GMAIL_USER`、`GMAIL_APP_PASSWORD`、`MAIL_TO`。
