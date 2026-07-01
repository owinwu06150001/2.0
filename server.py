import os
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "你好 我活著"

def run():
    # 💡 優化 1：自動適應動態連接埠
    # Render 等雲端平台會動態分配 PORT，若硬編碼 8080 會導致部署失敗。
    # 這樣寫能確保在 Replit (預設 8080) 和 Render 上都能完美運行。
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    # 💡 優化 2：【核心妙招】從環境變數自動注入 YouTube Cookies
    # 雲端伺服器重啟時檔案常會遺失，且把 Cookie 檔案傳到 GitHub 非常不安全。
    # 這裡讓伺服器啟動時，自動將你在後台設定的「環境變數」轉換為機器人需要的 cookies.txt。
    try:
        cookie_content = os.environ.get("YOUTUBE_COOKIES")
        if cookie_content:
            with open("cookies.txt", "w", encoding="utf-8") as f:
                f.write(cookie_content)
            print("[Keep-Alive] 成功：已從環境變數自動生成 cookies.txt 檔案！")
        else:
            print("[Keep-Alive] 提示：未檢測到 YOUTUBE_COOKIES 環境變數，跳過 Cookie 注入。")
    except Exception as e:
        print(f"[Keep-Alive] 警告：自動寫入 cookies.txt 失敗 -> {e}")

    # 啟動 Flask 執行緒
    t = Thread(target=run)
    t.start()
