# QuickJet AI 展會相機 — 專案交接文件

> 給接手的 AI 助手：這份文件是完整的專案狀態。使用者的電腦可直接存取 SD 卡（Windows 下通常是 `D:\`），請優先自行讀取檔案，不要要求使用者貼上你能自己讀的內容。回覆使用繁體中文，語氣簡潔實務。

## 專案目標

2026 年 7 月中國展會用的 AI 拍照相機：客戶在 QuickJet（CNC 工具機**製造商**，非加工端）攤位拍照，生成有品牌感的紀念照。手機開 web app 按快門或按機身實體鈕 → Pi 拍照 → 隨機/選定提示詞 → OpenAI gpt-image 生圖 → 手機 Gallery 顯示下載。

## 程式碼

Repo：`booke3c/minorquines-courtyard-3d`，分支 `claude/camera-hardware-setup-tuqf1m`（全部已推送）

| 目錄 | 內容 |
|---|---|
| `imagegencam/` | **展會用主程式**。Vendor 自 openai/imagegencam（Apache-2.0）並已改造：`IMAGEGENCAM_DISPLAY=whisplay` 顯示後端（240×280 LCD 鏡像、單鈕＝快門、LED 對應）、`IMAGEGENCAM_HEADLESS=1` 無螢幕模式、手機 web 快門 `POST /api/shutter`、三組 QuickJet 提示詞、logo overlay 預留（`data/assets/quickjet-logo.png`）。測試 34 項全過：`PYTHONPATH=software/src python -m unittest discover -s software/tests` |
| `ai-camera/` | 早期的單機簡易版（單鈕、無 web）。展會不用它，但其 `install.sh` 可代裝 Whisplay 驅動＋相機 overlay。兩套服務不可同時跑（搶相機） |
| `courtyard_3d_interactive.html` 等 | 無關的舊專案檔，忽略 |

## 硬體（已組裝完成）

- Raspberry Pi Zero 2 W（排針已焊）＋ PiSugar 3 電池（背面 pogo pin 供電，USB-C 充電）
- PiSugar **Whisplay HAT**（240×280 ST7789 LCD、單顆按鈕、RGB LED、WM8960）— 驅動：https://github.com/PiSugar/whisplay
- 相機：**第三方 IMX708 模組**（CAM109，板印 "IMX708 Camera"，等同 Camera Module 3 感光元件）。經短轉接排線（15→22pin）接 Zero 的 CSI。**非官方模組，必須在 config.txt 設**：`camera_auto_detect=0` ＋ `dtoverlay=imx708,cam0`，且系統需 2025-10 之後版本（kernel 6.12+）
- 堆疊順序（上→下）：Whisplay HAT / Zero 2W / PiSugar 3 / 電池。組裝已驗證 OK
- 網路：展會用 DJB eSIM 手機熱點，Pi 連熱點，手機瀏覽器開 `http://<Pi IP>:8000`

## 目前進度（接手點）

賣家提供了預燒系統的 32G SD 卡。已從 boot 分割區檔案清單確認是 **2025-10 後的 Raspberry Pi OS（Trixie，有 cloud-init 的 user-data/network-config/meta-data）**，版本夠新。

**下一步＝檢查 SD 卡（插在使用者電腦上，請直接讀檔）：**

1. 讀 `D:\config.txt` → 確認有無 `dtoverlay=imx708`、`camera_auto_detect=0`、`dtparam=spi=on`、Whisplay 音效 overlay
2. 讀 `D:\issue.txt` → 燒錄日期版本
3. 讀 `D:\network-config`、`D:\user-data` → 看賣家設的帳號與 Wi-Fi；評估能否直接把使用者手機熱點寫進去（注意：賣家若已開機過，cloud-init 不會自動重跑；可考慮清 `/var/lib/cloud` 或改用其他方式設 Wi-Fi）
4. 判斷：賣家系統可直接用（補設定即可）vs 用 Raspberry Pi Imager 重燒（重燒不損失任何功能，我們的腳本會補齊驅動；Imager 設定：hostname=`imagegencam`、Wi-Fi=手機熱點、開 SSH）

## SD 卡能開機連線後的安裝流程

```bash
# 1) 驅動（若賣家未裝）：Whisplay 驅動 + 相機 overlay
git clone https://github.com/PiSugar/Whisplay.git --depth 1 ~/Whisplay
cd ~/Whisplay && sudo bash install_driver.sh
# config.txt 補 camera_auto_detect=0 與 dtoverlay=imx708,cam0 後 reboot

# 2) 硬體驗收
rpicam-hello --list-cameras   # 必須列出 imx708
rpicam-jpeg -o test.jpg
bash ~/Whisplay/example/run_test.sh

# 3) 主程式
git clone https://github.com/booke3c/minorquines-courtyard-3d.git
cd minorquines-courtyard-3d/imagegencam/software
bash scripts/setup.sh
cp .env.example .env   # 填 OPENAI_API_KEY；IMAGEGENCAM_DISPLAY=whisplay
# IMAGE_GEN_QUALITY=low、IMAGE_GEN_SIZE=1536x1024、WHISPLAY_DIR=/home/<user>/Whisplay
bash scripts/install_service.sh   # 開機自啟
```

## 待辦清單

- [ ] SD 卡判讀（上述下一步）
- [ ] 開機、SSH、驅動與相機驗收
- [ ] 部署 imagegencam、填 API key、手機實測完整流程
- [ ] 取得 QuickJet 透明 logo PNG → `data/assets/quickjet-logo.png`，並把 prompts 裡的 logo 文字段落移除（PNG overlay 比 prompt 生成穩定）
- [ ] 3D 外殼總組裝（撕螢幕保護膜）、展會壓力測試（連拍、弱網重試、電池續航）

## 原則

- API key 只放 `.env` / `/etc`，不貼對話
- 改 imagegencam 程式保持最小改動，跑 `unittest` 驗證
- web app 僅限區網使用，勿暴露公網
