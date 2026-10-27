# podcast-digest

每天抓 `feeds.json` 裡節目的新集數，用 Whisper 轉逐字稿，每集一封信寄到指定信箱；摘要由另一個雲端排程從信箱讀取後撰寫。

逐字稿與音檔不存進本 repo。`state/seen.json` 只記錄已處理的集數識別碼。

需要的 secrets：`GMAIL_USER`、`GMAIL_APP_PASSWORD`、`MAIL_TO`。

流程：每天台北 17:00 開跑，逐集轉錄寄信。摘要由雲端排程任務「Podcast 每日摘要」每晚 21:52 執行一次，讀取當天的逐字稿信合成一封摘要。
