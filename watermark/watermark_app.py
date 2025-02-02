import os
import sys
import json
import argparse
from PIL import Image

def adjust_opacity(watermark, opacity):
    """
    調整浮水印圖片透明度（必須為 RGBA 模式）
    """
    if watermark.mode != 'RGBA':
        watermark = watermark.convert('RGBA')
    alpha = watermark.split()[3].point(lambda p: int(p * opacity))
    watermark.putalpha(alpha)
    return watermark

def get_resample_method():
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.ANTIALIAS

def resize_watermark(watermark, base_image, scale):
    """
    根據基底圖片較短邊的長度，將水印調整為指定百分比大小（scale 為百分比數值）。
    回傳縮放後的水印與縮放比例。
    """
    base_width, base_height = base_image.size
    base_dimension = min(base_width, base_height)
    target_width = int(base_dimension * scale / 100)
    orig_w, orig_h = watermark.size
    ratio = target_width / orig_w
    resample_method = get_resample_method()
    resized = watermark.resize((target_width, int(orig_h * ratio)), resample_method)
    return resized, ratio

def get_position(pos_option, base_size, watermark_size, extra_bottom_scaled=0, margin=15):
    """
    根據指定的位置與邊緣距離參數，計算水印貼上位置：
      - 上側位置：水印頂端距離圖片上邊緣為 margin 像素；
      - 底側位置：水印有效內容的底部（扣除縮放後的透明邊距 extra_bottom_scaled）距離圖片底邊緣為 margin 像素；
      - 左右側則分別保留 margin 像素的距離。
    最後將 x 與 y 座標轉為整數後回傳。
    """
    base_width, base_height = base_size
    watermark_width, watermark_height = watermark_size

    if pos_option == 'left_top':
        x, y = margin, margin
    elif pos_option == 'top':
        x = (base_width - watermark_width) // 2
        y = margin
    elif pos_option == 'right_top':
        x = base_width - watermark_width - margin
        y = margin
    elif pos_option == 'left_bottom':
        x = margin
        y = base_height - margin - (watermark_height - extra_bottom_scaled)
    elif pos_option == 'bottom':
        x = (base_width - watermark_width) // 2
        y = base_height - margin - (watermark_height - extra_bottom_scaled)
    elif pos_option == 'right_bottom':
        x = base_width - watermark_width - margin
        y = base_height - margin - (watermark_height - extra_bottom_scaled)
    else:
        # 若位置選項錯誤，則預設採用 bottom
        x = (base_width - watermark_width) // 2
        y = base_height - margin - (watermark_height - extra_bottom_scaled)
    return (int(x), int(y))

def get_available_path(output_path):
    """
    若指定的輸出檔案已存在，自動在檔名後加入數字後綴，避免覆蓋原檔
    """
    base, ext = os.path.splitext(output_path)
    counter = 1
    new_path = output_path
    while os.path.exists(new_path):
        new_path = f"{base}_{counter}{ext}"
        counter += 1
    return new_path

def process_image(file_path, output_path, watermark_path, opacity, position, scale, quality, margin_vertical, margin_horizontal):
    try:
        with Image.open(file_path) as base_img:
            # 轉換基底圖片為 RGBA 模式
            if base_img.mode != 'RGBA':
                base_img = base_img.convert('RGBA')

            # 判斷圖片方向：直向照片 (portrait) 寬 < 高；橫向照片 (landscape) 寬 >= 高
            margin_used = margin_vertical if base_img.width < base_img.height else margin_horizontal

            with Image.open(watermark_path) as wm:
                if wm.mode != 'RGBA':
                    wm = wm.convert('RGBA')
                # 取得水印中有效內容的邊界，用以計算底部透明邊距
                bbox = wm.getbbox()
                extra_bottom = wm.height - bbox[3] if bbox else 0

                # 調整水印透明度
                wm = adjust_opacity(wm, opacity)
                # 依原始水印尺寸計算縮放比例，取得縮放後的水印
                resized_wm, ratio = resize_watermark(wm, base_img, scale)
                extra_bottom_scaled = extra_bottom * ratio

                # 計算水印貼上位置
                pos = get_position(position, base_img.size, resized_wm.size, extra_bottom_scaled, margin_used)

                # 建立全透明圖層並貼上水印，再與原圖合成
                layer = Image.new('RGBA', base_img.size, (0, 0, 0, 0))
                layer.paste(resized_wm, pos, resized_wm)
                result = Image.alpha_composite(base_img, layer)

                # JPEG 格式需轉換為 RGB 模式
                ext = os.path.splitext(file_path)[1].lower()
                if ext in ['.jpg', '.jpeg']:
                    result = result.convert('RGB')

                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                output_path = get_available_path(output_path)
                if ext in ['.jpg', '.jpeg'] and quality is not None:
                    result.save(output_path, quality=quality)
                else:
                    result.save(output_path)
                print(f"處理成功：{file_path} -> {output_path}")
    except Exception as e:
        print(f"處理失敗 {file_path}：{e}")

def main():
    parser = argparse.ArgumentParser(description="圖片浮水印添加應用程式")
    parser.add_argument("--config", "-c", type=str, default=None,
                        help="配置文件 (JSON 格式)，若工作目錄中存在 config.json，則自動讀取")
    parser.add_argument("--input-folder", "-if", type=str, default="original",
                        help="輸入資料夾，預設為 original")
    parser.add_argument("--watermark", "-w", type=str, default="Logo.png",
                        help="浮水印圖片檔案（需支援 PNG），預設為 Logo.png")
    parser.add_argument("--opacity", "-o", type=float, default=0.65,
                        help="浮水印透明度（0~1），預設為 0.65")
    parser.add_argument("--position", "-p", type=str, default="bottom",
                        choices=["left_top", "top", "right_top", "left_bottom", "bottom", "right_bottom"],
                        help="浮水印位置，預設為 bottom（下方，水平置中）")
    parser.add_argument("--quality", "-q", type=int, default=100,
                        help="輸出圖片壓縮率（質量百分比），預設為 100（不壓縮，僅適用於 JPEG）")
    parser.add_argument("--scale", "-s", type=float, default=15,
                        help="浮水印縮放比例（相對於圖片較短邊的百分比），預設為 15")
    parser.add_argument("--margin-vertical", "-mv", type=int, default=20,
                        help="直向照片水印與圖片邊緣的間距（像素），預設為 20")
    parser.add_argument("--margin-horizontal", "-mh", type=int, default=15,
                        help="橫向照片水印與圖片邊緣的間距（像素），預設為 15")
    parser.add_argument("--output-folder", "-of", type=str, default="output",
                        help="輸出資料夾，預設為 output")
    parser.add_argument("--recursive", "-r", action="store_true", default=False,
                        help="是否遞迴處理子資料夾中的圖片，預設為不處理")
    args = parser.parse_args()

    # 讀取配置文件（命令列中明確指定的參數具有較高優先權）
    config_filename = args.config if args.config else "config.json"
    if os.path.exists(config_filename):
        try:
            with open(config_filename, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            flag_mapping = {
                "input_folder": ["--input-folder", "-if"],
                "watermark": ["--watermark", "-w"],
                "opacity": ["--opacity", "-o"],
                "position": ["--position", "-p"],
                "quality": ["--quality", "-q"],
                "scale": ["--scale", "-s"],
                "margin_vertical": ["--margin-vertical", "-mv"],
                "margin_horizontal": ["--margin-horizontal", "-mh"],
                "output_folder": ["--output-folder", "-of"],
                "recursive": ["--recursive", "-r"]
            }
            for key, value in config_data.items():
                if key in flag_mapping:
                    if not any(flag in sys.argv for flag in flag_mapping[key]):
                        setattr(args, key, value)
        except Exception as e:
            print(f"讀取配置文件失敗：{e}")
    else:
        print(f"找不到配置文件 '{config_filename}'，將使用預設值或命令列參數。")

    input_folder = args.input_folder
    output_folder = args.output_folder

    if args.recursive:
        # 遞迴遍歷輸入資料夾及所有子資料夾，並在 output_folder 中維持相同結構
        for root, _, files in os.walk(input_folder):
            for file in files:
                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(root, input_folder)
                    name, ext = os.path.splitext(file)
                    output_filename = f"{name}_mk{ext}"
                    output_path = os.path.join(output_folder, rel_path, output_filename)
                    process_image(file_path, output_path, args.watermark, args.opacity, args.position,
                                  args.scale, args.quality, args.margin_vertical, args.margin_horizontal)
    else:
        # 僅處理 input_folder 頂層的圖片，不遞迴子資料夾
        for file in os.listdir(input_folder):
            file_path = os.path.join(input_folder, file)
            if os.path.isfile(file_path) and file.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                name, ext = os.path.splitext(file)
                output_filename = f"{name}_mk{ext}"
                # 在非遞迴模式下，所有輸出檔案直接存放在 output_folder 下
                output_path = os.path.join(output_folder, output_filename)
                process_image(file_path, output_path, args.watermark, args.opacity, args.position,
                              args.scale, args.quality, args.margin_vertical, args.margin_horizontal)

if __name__ == "__main__":
    main()
