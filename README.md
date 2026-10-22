# podcast-digest

每天抓 `feeds.json` 裡節目的新集數，用 Whisper 轉逐字稿，每集一封信寄到指定信箱；摘要由另一個雲端排程從信箱讀取後撰寫。

逐字稿與音檔不存進本 repo。`state/seen.json` 只記錄已處理的集數識別碼。

需要的 secrets：`GMAIL_USER`、`GMAIL_APP_PASSWORD`、`MAIL_TO`、`SUMMARY_FIRE_TOKEN`。

流程：每天台北 17:00 開跑，逐集轉錄寄信；全部完成後觸發雲端摘要任務（早於 20:40 完成則等到 20:40）。
