# watermark 使用說明

## 批次處理圖片浮水印

### 支持設定水印圖片、透明度、縮放比例及位置（支持左上、上、中下、右下等）。
### 自行安裝 Python、Pillow。

---

## 一、參數說明

本應用程式支援透過命令列參數或 JSON 配置文件設定各項參數。以下為所有參數的完整說明與其簡寫：

1. **--config (-c)**  
   - **說明：** 指定配置文件（JSON 格式），用以設定預設參數值。若該文件存在，程式會讀取並更新參數；命令列中明確指定的參數將覆蓋配置文件中的值。  
   - **預設值：** 無（若不指定，則僅使用命令列預設值）。

2. **--input-folder (-if)**  
   - **說明：** 指定待處理圖片的輸入資料夾。程式將從該資料夾中尋找圖片。  
   - **預設值：** "original"

3. **--watermark (-w)**  
   - **說明：** 指定浮水印圖片檔案（建議使用 PNG 格式），將作為浮水印添加到原圖上。  
   - **預設值：** "Logo.png"

4. **--opacity (-o)**  
   - **說明：** 設定浮水印透明度，數值介於 0（全透明）到 1（完全不透明）之間。  
   - **預設值：** 0.65

5. **--position (-p)**  
   - **說明：** 指定浮水印在圖片上的位置。可選項目如下：  
     - "left_top"（左上角）  
     - "top"（上方，水平置中）  
     - "right_top"（右上角）  
     - "left_bottom"（左下角）  
     - "bottom"（下方，水平置中）  
     - "right_bottom"（右下角）  
   - **預設值：** "bottom"

6. **--quality (-q)**  
   - **說明：** 設定輸出圖片的壓縮品質（僅適用於 JPEG 格式），100 表示無壓縮。  
   - **預設值：** 100

7. **--scale (-s)**  
   - **說明：** 指定浮水印縮放比例（以圖片較短邊的百分比計算），決定浮水印在圖片中的相對大小。  
   - **預設值：** 15

8. **--margin-vertical (-mv)**  
   - **說明：** 設定直向（portrait）照片中，浮水印與圖片邊緣間的間距（單位：像素）。  
   - **預設值：** 20

9. **--margin-horizontal (-mh)**  
   - **說明：** 設定橫向（landscape）照片中，浮水印與圖片邊緣間的間距（單位：像素）。  
   - **預設值：** 15

10. **--output-folder (-of)**  
    - **說明：** 指定處理後圖片的輸出資料夾。若啟用遞迴處理，程式將在此資料夾中建立與輸入資料夾相同的目錄結構。  
    - **預設值：** "output"

11. **--recursive (-r)**  
    - **說明：** 控制是否遞迴處理輸入資料夾中的子資料夾。  
      - 若加上此旗標（值為 True），則程式會遞迴處理所有子資料夾，並在輸出資料夾中維持原有的資料夾結構。  
      - 若不加（預設為 False），則僅處理輸入資料夾頂層的圖片，所有輸出檔案直接存放於輸出資料夾中。  
    - **預設值：** false

---

## 二、配置文件 (config.json)

```json
{
    "input_folder": "original",
    "watermark": "Logo.png",
    "opacity": 0.65,
    "position": "bottom",
    "quality": 100,
    "scale": 15,
    "margin_vertical": 20,
    "margin_horizontal": 15,
    "output_folder": "output",
    "recursive": false
}
```

---

## 三、如何運行程式

### 1. 基本運行
若所有設定皆使用預設值（或配置文件中設定的值），請將程式碼存為 `watermark_app.py`，並將待處理圖片放入 `original` 資料夾中，執行以下命令：
```bash
python watermark_app.py
```

### 2. 指定配置文件
假設您的配置文件名稱為 config.json，請使用：
```bash
python watermark_app.py --config config.json
```

### 3. 自訂參數運行
例如，若您希望：
- 使用浮水印圖片 `MyLogo.png`，
- 透明度設為 0.8，
- 浮水印位置設定在右下角，
- 浮水印縮放比例為 20，
- 輸出資料夾為 `my_output`，
- 且僅處理輸入資料夾頂層（不遞迴處理子資料夾），

則執行：
```bash
python watermark_app.py -w MyLogo.png -o 0.8 -p right_bottom -s 20 -of my_output
```

若要啟用遞迴處理子資料夾，則加上 `--recursive` 或 `-r`：
```bash
python watermark_app.py -w MyLogo.png -o 0.8 -p right_bottom -s 20 -of my_output -r
```

### 4. 使用配置文件與命令列參數混合
您也可以先在 config.json 中設定大部分預設值，再在命令列中僅指定部分參數以覆蓋配置文件中的設定。例如：
```bash
python watermark_app.py --config config.json -o 0.75
```
上例中，程式會使用 config.json 中的所有設定，但將透明度改為 0.75。

---

## 四、注意事項

- **資料夾結構：**  
  - 若未啟用遞迴處理（--recursive 為 False），則只處理輸入資料夾頂層的圖片，所有處理結果會直接存放在輸出資料夾中。  
  - 若啟用遞迴處理（--recursive 為 True），則程式會保留原輸入資料夾的結構，在輸出資料夾中建立相同的目錄，以避免檔名衝突。

- **命令列優先順序：**  
  若同時指定配置文件與命令列參數，命令列參數將優先使用。

- **圖片格式：**  
  本程式支援 PNG、JPG、JPEG、BMP、GIF 等格式。對於 JPEG 格式，輸出時可設定壓縮品質（--quality）。

- **輸出格式：**
  輸出格式與輸入相同，暫不支持輸出格式自訂。
