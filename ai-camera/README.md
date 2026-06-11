# AI 手感相機（Whisplay HAT 版）

單鍵 AI 相機：按一下按鈕 → 拍照 → 從三組提示詞隨機抽一組 → 丟給 OpenAI
`gpt-image-1` 做圖生圖 → 結果直接顯示在 Whisplay HAT 的 LCD 上。
每次按下快門，你都不知道會抽到哪種風格 —— 這就是「AI 手感」。

## 硬體清單

| 項目 | 說明 |
|---|---|
| Raspberry Pi Zero 2 W（或 Pi 4 / Pi 5） | 主機 |
| PiSugar Whisplay HAT | 1.69" 240×280 LCD、單顆自訂按鈕、RGB LED、WM8960 喇叭/麥克風 |
| 樹莓派官方 Camera Module 3（IMX708） | 12MP、自動對焦，系統**自動偵測，不用改 config.txt** |
| microSD 卡 32GB U3 | 最新 Raspberry Pi OS Bookworm |
| PiSugar 3 電池 | 帶出門用；3D 列印外殼含相機開孔 |

## 組裝

1. **先斷電**再接相機排線：金屬接點朝電路板方向插入 CSI 座，扣回卡扣
   （Pi Zero 需用 22-pin 細排線那一端）。
2. Whisplay HAT 疊上 40-pin 排針。
3. 上電開機。

## 安裝（在 Pi 上執行）

燒錄 Raspberry Pi OS Bookworm（用 Raspberry Pi Imager 先設好 Wi-Fi 與 SSH），
然後 SSH 進去：

```bash
git clone https://github.com/booke3c/minorquines-courtyard-3d.git
cd minorquines-courtyard-3d/ai-camera
sudo bash install.sh        # 裝依賴、Whisplay 驅動、相機 overlay、systemd 服務
sudo nano /etc/ai-camera.env   # 填入 OPENAI_API_KEY
sudo reboot
```

`install.sh` 做的事：

- `apt` 安裝 Pillow / numpy / requests / spidev / gpiod / Noto CJK 字型 / rpicam-apps
- clone 並安裝 [PiSugar/Whisplay](https://github.com/PiSugar/whisplay) 官方驅動（LCD、按鈕、LED、音效）
- 程式安裝到 `/opt/ai-camera`，並註冊開機自啟的 `ai-camera.service`

官方 Camera Module 3 接上即用，不需要動 `config.txt`。
（若日後改用第三方 IMX708 模組如 CAM109，改跑 `sudo bash install.sh --third-party-cam`）

## 驗證硬體

```bash
rpicam-hello -t 5000          # 應看到相機預覽（接 HDMI 螢幕時）
rpicam-jpeg -o test.jpg       # 拍一張確認
bash ~/Whisplay/example/run_test.sh   # 測 LCD / LED / 按鈕
```

## 使用方式

| 操作 | 行為 |
|---|---|
| 短按按鈕 | 拍照 → 隨機抽一組提示詞 → AI 生圖 → 顯示結果 |
| 結果顯示中再按 | 直接拍下一張 |
| 長按 3 秒 | 安全關機 |

LED 狀態：綠＝待機、白＝拍照中、紫色呼吸＝生成中、青＝完成、紅＝錯誤。
每次拍攝會在 `~/ai-camera-gallery/<時間戳>/` 留下
`photo.jpg`（原照）、`result.png`（AI 圖）、`prompt.txt`（抽到的提示詞）。

## 自訂三組提示詞

編輯 `/opt/ai-camera/prompts.json`（陣列幾組就隨機抽幾組，不限三組）：

```json
[
  { "name": "夢境水彩", "label": "Dream Watercolor", "prompt": "Transform this photo into ..." }
]
```

改完重啟服務：`sudo systemctl restart ai-camera`

## 調整與除錯

- 設定都在 `/etc/ai-camera.env`：模型、尺寸（`1024x1536` 直幅更貼近螢幕比例）、
  品質、`INPUT_FIDELITY=high`（人臉/細節保真，較貴）、拍照指令等。
- 看ログ：`journalctl -u ai-camera -f`
- 手動跑（先停服務）：`sudo systemctl stop ai-camera && sudo python3 /opt/ai-camera/camera_app.py`
- 相機點不亮：`rpicam-hello --list-cameras` 應列出 imx708；沒有的話檢查排線方向與卡扣
  （官方模組不需要任何 `config.txt` 設定，若曾手動加過 `camera_auto_detect=0` 請移除）。
- 生成一張約需 30–90 秒（視網路與 quality），Zero 2 W 上傳較慢屬正常。
