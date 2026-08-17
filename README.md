# 糖果屋之後 · After the Gingerbread House

白天餵飽他們，晚上他們才不會餓到吃掉葛蕾特。

一款用 **pygame** 做的黑暗童話生存遊戲：格林童話《糖果屋》之後——兄妹燒了女巫的屋子、帶著財寶回到村子，村子鬧饑荒，村民入夜會發狂想吃掉妹妹葛蕾特。白天分食、磨利提燈、添燈油、設陷阱；夜晚在只有光源可見的黑暗裡揮燈防守 50 秒。

國立成功大學「Python Programming for Interactive Game Design」課程 Capstone 專題。

## 玩

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e ".[test,display]"
.venv/bin/python -m gingerbread
```

- **WASD / 方向鍵**：移動
- **空白鍵**：揮燈攻擊（有冷卻、有方向性）
- **Shift**：衝刺
- 白天用滑鼠點行動卡、再點畫面放置

## 驗收

```bash
.venv/bin/python -m pytest -q                # 14 個聚焦測試
.venv/bin/python -m gingerbread --check       # 無畫面確定性檢查，輸出 JSON
```

`--check` 兩次執行的輸出逐位元組相同——這就是「可重現」的證據：不開視窗、不用人按鍵，也能驗證遊戲邏輯正確。

## 架構

這個專案照課程契約刻意把**規則**、**畫面**、**裝置**分成三層，互不越權：

```
src/gingerbread/
  model.py    純領域模型，完全不 import pygame，可離線測試
  render.py   唯讀渲染器，只觀察 State 並畫出來，不改任何結果
  game.py     pygame 外殼，唯一碰事件與按鍵的地方
```

一幀只有一個方向：

```
事件 + 按鍵 → InputAdapter → 動作字串
           → apply_action(state, action)   ← 模型擁有結果
           → Renderer.draw(state)          ← 唯讀
           → display.flip() → clock.tick()
```

### 契約函式（`model.py`）

依 Capstone 指引實作的四個介面：

| 函式 | 做什麼 |
|---|---|
| `new_game(seed)` | 回傳全新狀態，無顯示、無裝置依賴 |
| `apply_action(state, action)` | 回傳下一個狀態，**不改動傳入的 state** |
| `is_terminal(state)` | 只有撐到天亮或被抓走才回傳 True |
| `snapshot(state)` | 回傳穩定、可比對、JSON-safe 的證據 |

固定時間步（`FIXED_DT = 1/60`）、亂數收攏在 `State._rng`，由 `seed` 決定——所以「相同 seed + 相同動作序列 → 相同結果」永遠成立，這是 `tests/test_contract.py` 裡多數測試在驗證的事。

## 網頁版

```bash
.venv/bin/python -m pip install pygbag fonttools
.venv/bin/python build_web.py
```

編譯產物在 `web/build/web/`（`.gitignore` 排除，不進版本控制）。中文字型用 `fonttools` 從系統字型子集化到 `assets/GameCJK-Subset.ttf`（124 KB，只含遊戲實際用到的字），因為瀏覽器執行環境沒有系統字型可用。

> 部署到 Vercel 等靜態平台時**不要**加 `Cross-Origin-Embedder-Policy: require-corp`——會擋掉 pygbag 的 CDN 資源，導致頁面卡在載入畫面。

## 專案結構

```
src/gingerbread/    套件本體（model / render / game）
tests/              pytest 測試
assets/             網頁版用的字型子集
evidence/shots/     四個階段的畫面截圖（序章／白天／夜晚／結算）
build_web.py        組出 pygbag 可編譯的資料夾
pyproject.toml      套件設定；display / test 是選用相依
```

## 開發紀錄

完整的專業視角審查（八個角色：系統設計師、硬派玩家、UX 研究員、美術總監、音效設計師、發行顧問、QA、敘事設計師）與待辦路線圖，見專案外的 `遊戲審查_八位專業角色結論.md`。
