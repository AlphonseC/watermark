# watermark 使用說明

## 批次處理圖片浮水印

### 支持設定水印圖片、透明度、縮放比例及位置（支持左上、上、中下、右下等）。
## 本應用程式主要依賴下列模組：
### Pillow：進行圖片讀寫與處理
### psutil：用於監控記憶體使用量（GC 混合模式下必需）

---

## 1\. 配置文件 (config.ini) 格式與內容

您可使用 INI 格式設定參數，檔案可命名為 config.ini。範例如下：

```
[DEFAULT]
# 輸入資料夾，若不存在則自動建立
input_folder = original

# 浮水印圖片檔案（必須存在且支援 PNG）
watermark = Logo.png

# 浮水印透明度 (0~1)
opacity = 0.65

# 浮水印位置，允許值：left_top, top, right_top, bottom, right_bottom
position = bottom

# JPEG 輸出品質 (1-100)
quality = 100

# 浮水印縮放比例 (1-100)；代表圖片較短邊的百分比
scale = 15

# 直向圖片水印與圖片邊緣間距 (像素)
margin_vertical = 20

# 橫向圖片水印與圖片邊緣間距 (像素)
margin_horizontal = 15

# 輸出資料夾
output_folder = output

# 是否遞迴處理子資料夾中的圖片 (True 或 False)
recursive = False

# 每處理多少張圖片後進行一次垃圾回收檢查
gc_batch_size = 20

# 記憶體使用量門檻 (MB)，超過此值時觸發垃圾回收
gc_memory_threshold = 500

# 記憶體監控線程檢查間隔 (秒)
memory_check_interval = 5

# 是否啟用混合模式：先檢查記憶體使用量，再依據圖片數量作備用檢查
enable_mixed_mode = False

# 是否啟用平行處理 (True/False)
enable_parallel = False

# 平行處理時輸出檔名中 UUID 的長度 (4-36)
uuid_length = 6

# 是否啟用進階記憶體管理 (True/False)
enable_advanced_memory_management = False

# 進階記憶體管理：是否啟用預壓縮大型圖片 (True/False)
enable_precompression = False

# 當圖片寬或高超過此像素值時，啟用進階記憶體管理功能（預壓縮）的判斷，介於 100 至 10000 之間
large_image_threshold = 3000
```

* * *

## 2\. 參數說明

以下分項說明每個參數的功能與用途：

### 2.1 輸入與輸出相關

- **input\_folder**
    - **功能：** 指定待處理圖片的資料夾。
    - **驗證：** 若資料夾不存在，程式會自動建立。
    - **預設：** original
- **watermark**
    - **功能：** 指定用作浮水印的圖片檔案。
    - **驗證：** 檔案必須存在且支援 PNG 格式。
    - **預設：** Logo.png
- **output\_folder**
    - **功能：** 指定處理後圖片的儲存資料夾。
    - **預設：** output
- **recursive**
    - **功能：** 是否遞迴處理輸入資料夾中的子資料夾。
    - **預設：** False

### 2.2 浮水印與圖片處理

- **opacity**
    - **功能：** 設定浮水印透明度。
    - **驗證：** 必須介於 0 與 1 之間。
    - **預設：** 0.65
- **position**
    - **功能：** 指定浮水印在圖片中的位置。
    - **允許值：** left\_top, top, right\_top, bottom, right\_bottom
    - **預設：** bottom
- **quality**
    - **功能：** JPEG 輸出圖片的壓縮品質。
    - **驗證：** 整數介於 1 至 100 之間。
    - **預設：** 100
- **scale**
    - **功能：** 浮水印縮放比例（以圖片較短邊的百分比計算）。
    - **驗證：** 必須介於 1 至 100 之間。
    - **預設：** 15
- **margin\_vertical** 與 **margin\_horizontal**
    - **功能：** 分別設定直向和橫向圖片中，浮水印與圖片邊緣的間距。
    - **驗證：** 必須為非負整數。
    - **預設：** 20 與 15

### 2.3 記憶體管理相關

- **gc\_batch\_size**
    - **功能：** 每處理多少張圖片後進行一次垃圾回收檢查。
    - **驗證：** 必須大於 0。
    - **預設：** 20
- **gc\_memory\_threshold**
    - **功能：** 當進程記憶體使用量超過該 MB 值時，觸發垃圾回收。
    - **驗證：** 必須大於 0。
    - **預設：** 500
- **memory\_check\_interval**
    - **功能：** 記憶體監控線程檢查間隔（秒）。
    - **驗證：** 必須大於 0。
    - **預設：** 5
- **enable\_mixed\_mode**
    - **功能：** 是否啟用混合記憶體管理模式，即先檢查記憶體使用量，再依據圖片數量進行備用檢查。
    - **預設：** False

### 2.4 平行處理相關

- **enable\_parallel**
    - **功能：** 是否啟用平行處理（使用多線程或多進程進行圖片處理）。
    - **預設：** False
- **uuid\_length**
    - **功能：** 當啟用平行處理時，輸出檔名中附加的 UUID 的長度。
    - **驗證：** 必須介於 4 到 36 之間。
    - **預設：** 6

### 2.5 進階記憶體管理相關

- **enable\_advanced\_memory\_management**
    - **功能：** 是否啟用進階記憶體管理功能。
    - **預設：** False
    - **說明：** 若啟用，當圖片解析度超過 large\_image\_threshold 時，將根據選項對圖片進行預壓縮處理以降低記憶體占用（預壓縮會依比例縮小圖片尺寸）。
- **enable\_precompression**
    - **功能：** 是否啟用預壓縮功能。
    - **預設：** False
    - **說明：** 當啟用且圖片解析度超過 large\_image\_threshold 時，程式會依比例縮小圖片以降低記憶體占用。若畫質為首要考量，建議保持關閉。
- **large\_image\_threshold**
    - **功能：** 當圖片寬或高超過此像素值時，判斷該圖片為大型圖片。
    - **驗證：** 必須介於 100 至 10000 像素之間。
    - **預設：** 3000

* * *

## 3\. 運行方式

### 3.1 順序處理模式

直接執行：

```
python watermark_app.py
```

程式將依據配置文件或命令列參數，依序處理圖片，並根據設定進行記憶體檢查與垃圾回收。

### 3.2 平行處理模式

啟用平行處理：

```
python watermark_app.py --enable-parallel --uuid-length 6
```

此模式下，程式會利用多線程（或當同時啟用進階記憶體管理時，使用多進程）並行處理圖片，並在輸出檔名中加入 UUID 以避免檔名衝突。

### 3.3 進階記憶體管理

若需要在平行處理模式下對超大圖片進行預壓縮（當圖片寬或高超過 large\_image\_threshold）：

```
python watermark_app.py --enable-parallel --enable-advanced-memory-management --enable-precompression --large-image-threshold 3000 --uuid-length 6
```

此模式下，程式會判斷每張圖片的解析度，若超過設定的閾值則實際依比例縮小圖片以降低記憶體占用（改變圖片尺寸），從而有助於在資源受限時保持穩定性。  
_注意：進階記憶體管理功能在平行處理模式下會選用 ProcessPoolExecutor，讓各子進程獨立管理記憶體；若未啟用平行處理則依然使用順序模式。_

* * *

## 4\. 常見問題

### 4.1 參數錯誤如何處理？

所有參數在解析時均會進行驗證，若輸入錯誤（例如透明度不在 0～1 之間、UUID 長度不在 4～36 之間等），程式將立即終止，避免錯誤參數引起後續處理問題。

### 4.2 平行處理如何避免檔名衝突？

啟用平行處理時，每個輸出檔名會加入由 UUID 生成的唯一後綴，其長度可由 --uuid-length 指定。

### 4.3 進階記憶體管理功能會如何運作？

當同時啟用平行處理與進階記憶體管理時，程式將使用 ProcessPoolExecutor，各子進程在處理圖片時會檢查圖片解析度，若超過 --large-image-threshold 且啟用了預壓縮，則實際依比例縮小圖片，以降低記憶體占用。每個子進程亦會根據自身記憶體使用量進行垃圾回收檢查。
