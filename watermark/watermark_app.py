import os
import sys
import json
import argparse
import gc
import uuid
import time
import threading
import psutil  # 用於監控記憶體使用量
from PIL import Image
import concurrent.futures

# 全域記憶體監控與計數參數（由命令列或配置文件設定）
MEMORY_CHECK_INTERVAL = 5  # 單位：秒，檢查間隔（預設 5 秒）
gc_memory_threshold = 500  # 單位：MB（預設值）
gc_batch_size = 20         # 每處理 20 張圖片進行一次 gc 檢查（預設值）

# 全域計數器與鎖
image_counter = 0
counter_lock = threading.Lock()

# 停止記憶體監控線程的事件
stop_event = threading.Event()

def get_unique_path(output_path, uuid_length=6):
    """
    根據指定的輸出檔案名稱，利用 UUID 產生唯一識別碼，
    只取前 uuid_length 個字符，重新命名檔案以避免重複。
    例如："image_mk.jpg" 轉為 "image_mk_<uuid>.jpg"
    """
    base, ext = os.path.splitext(output_path)
    unique_suffix = uuid.uuid4().hex[:uuid_length]  # 取前 uuid_length 個字符
    return f"{base}_{unique_suffix}{ext}"

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
      - 上側：水印頂端距離圖片上邊緣為 margin 像素；
      - 底側：水印有效內容的底部（扣除縮放後透明邊距 extra_bottom_scaled）距離圖片底邊緣為 margin 像素；
      - 左右側：各保留 margin 像素距離。
    回傳整數座標 (x, y)。
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
        x = (base_width - watermark_width) // 2
        y = base_height - margin - (watermark_height - extra_bottom_scaled)
    return (int(x), int(y))

class WatermarkProcessor:
    """
    負責載入與預處理水印圖像，並根據每張原圖生成縮放後的水印。
    """
    def __init__(self, watermark_path, opacity):
        self.watermark = Image.open(watermark_path).convert("RGBA")
        self.watermark = adjust_opacity(self.watermark, opacity)
    
    def get_scaled_watermark(self, base_image, scale):
        resized, ratio = resize_watermark(self.watermark, base_image, scale)
        bbox = self.watermark.getbbox()
        extra_bottom = self.watermark.height - bbox[3] if bbox else 0
        extra_bottom_scaled = extra_bottom * ratio
        return resized, extra_bottom_scaled

def process_image(file_path, output_path, watermark_processor, position, scale, quality, margin_vertical, margin_horizontal, enable_parallel, uuid_length):
    """
    處理單一圖片：打開圖片、生成縮放後的水印、合成並輸出至指定路徑。
    若平行處理啟用，則利用 get_unique_path 加入 UUID（長度由 uuid_length 決定）以避免檔名重複，
    否則直接使用原始輸出檔名。
    """
    try:
        with Image.open(file_path) as base_img:
            if base_img.mode != 'RGBA':
                base_img = base_img.convert('RGBA')
            margin_used = margin_vertical if base_img.width < base_img.height else margin_horizontal
            scaled_wm, extra_bottom_scaled = watermark_processor.get_scaled_watermark(base_img, scale)
            pos = get_position(position, base_img.size, scaled_wm.size, extra_bottom_scaled, margin_used)
            layer = Image.new('RGBA', base_img.size, (0, 0, 0, 0))
            layer.paste(scaled_wm, pos, scaled_wm)
            result = Image.alpha_composite(base_img, layer)
            ext = os.path.splitext(file_path)[1].lower()
            if ext in ['.jpg', '.jpeg']:
                result = result.convert('RGB')
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            # 若平行處理啟用，使用 UUID 重新命名；否則直接使用原始輸出檔名
            final_output_path = get_unique_path(output_path, uuid_length) if enable_parallel else output_path
            if ext in ['.jpg', '.jpeg'] and quality is not None:
                result.save(final_output_path, quality=quality)
            else:
                result.save(final_output_path)
            print(f"處理成功：{file_path} -> {final_output_path}")
    except Exception as e:
        print(f"處理失敗 {file_path}：{e}")

def iter_files(input_folder, recursive):
    """
    生成器：根據 input_folder 及是否遞迴處理，依序回傳符合條件的圖片檔案路徑。
    """
    if recursive:
        for root, _, files in os.walk(input_folder):
            for file in files:
                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                    yield os.path.join(root, file)
    else:
        for file in os.listdir(input_folder):
            file_path = os.path.join(input_folder, file)
            if os.path.isfile(file_path) and file.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                yield file_path

def memory_monitor(monitor_interval, memory_threshold_bytes):
    """
    記憶體監控線程：每隔 monitor_interval 秒檢查一次進程記憶體使用量，
    若超過 memory_threshold_bytes，則觸發 gc.collect()。
    """
    while not stop_event.is_set():
        time.sleep(monitor_interval)
        mem_used = psutil.Process(os.getpid()).memory_info().rss
        if mem_used > memory_threshold_bytes:
            print(f"[監控] 記憶體使用量達到 {mem_used/(1024*1024):.2f} MB，觸發垃圾回收...")
            gc.collect()

def process_single(file_path, input_folder, output_folder, watermark_processor, position, scale, quality, margin_vertical, margin_horizontal, enable_parallel, uuid_length):
    """
    處理單一圖片，根據是否啟用遞迴決定輸出路徑，並更新全域計數器（採用鎖保護）。
    """
    if os.path.isdir(input_folder):
        rel_path = os.path.relpath(os.path.dirname(file_path), input_folder)
        name, ext = os.path.splitext(os.path.basename(file_path))
        out_filename = f"{name}_mk{ext}"
        out_path = os.path.join(output_folder, rel_path, out_filename)
    else:
        name, ext = os.path.splitext(os.path.basename(file_path))
        out_filename = f"{name}_mk{ext}"
        out_path = os.path.join(output_folder, out_filename)
    
    process_image(file_path, out_path, watermark_processor, position, scale, quality, margin_vertical, margin_horizontal, enable_parallel, uuid_length)
    
    global image_counter
    with counter_lock:
        image_counter += 1

def main():
    parser = argparse.ArgumentParser(description="圖片浮水印添加應用程式")
    parser.add_argument("--config", "-c", type=str, default=None,
                        help="配置文件 (JSON 格式)，若存在 config.json 則自動讀取")
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
    parser.add_argument("--gc-batch-size", type=int, default=20,
                        help="每處理多少張圖片後進行垃圾回收檢查，預設 20 張")
    parser.add_argument("--gc-memory-threshold", type=int, default=500,
                        help="記憶體使用量超過此門檻值（MB）時觸發垃圾回收，預設 500 MB")
    parser.add_argument("--memory-check-interval", type=int, default=5,
                        help="記憶體監控線程檢查間隔（秒），預設 5 秒")
    parser.add_argument("--enable-mixed-mode", action="store_true", default=False,
                        help="是否啟用混合模式（先檢查記憶體使用量，再依據圖片數量作備用檢查）")
    parser.add_argument("--enable-parallel", action="store_true", default=False,
                        help="是否啟用平行處理功能（預設關閉）；啟用時會在檔案名稱中加入 UUID")
    parser.add_argument("--uuid-length", type=int, default=6,
                        help="平行處理時輸出檔名中 UUID 的長度，預設為 6")
    args = parser.parse_args()

    # 嘗試讀取配置文件（命令列參數具有較高優先權）
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
                "recursive": ["--recursive", "-r"],
                "gc_batch_size": ["--gc-batch-size"],
                "gc_memory_threshold": ["--gc-memory-threshold"],
                "memory_check_interval": ["--memory-check-interval"],
                "enable_mixed_mode": ["--enable-mixed-mode"],
                "enable_parallel": ["--enable-parallel"],
                "uuid_length": ["--uuid-length"]
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

    global gc_batch_size, gc_memory_threshold
    gc_batch_size = args.gc_batch_size
    gc_memory_threshold = args.gc_memory_threshold  # 單位 MB
    memory_check_interval = args.memory_check_interval
    memory_threshold_bytes = gc_memory_threshold * 1024 * 1024

    # 取得 uuid_length 參數
    uuid_length = args.uuid_length

    # 建立 WatermarkProcessor 物件
    watermark_processor = WatermarkProcessor(args.watermark, args.opacity)

    # 收集所有待處理圖片路徑
    files = list(iter_files(input_folder, args.recursive))

    # 啟動記憶體監控線程
    monitor_thread = threading.Thread(target=memory_monitor, args=(memory_check_interval, memory_threshold_bytes), daemon=True)
    monitor_thread.start()

    if args.enable_parallel:
        # 使用平行處理：ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(
                    process_single,
                    file_path,
                    input_folder,
                    output_folder,
                    watermark_processor,
                    args.position,
                    args.scale,
                    args.quality,
                    args.margin_vertical,
                    args.margin_horizontal,
                    args.enable_parallel,
                    uuid_length
                )
                for file_path in files
            ]
            concurrent.futures.wait(futures)
    else:
        # 順序處理
        for file_path in files:
            process_single(file_path, input_folder, output_folder, watermark_processor,
                           args.position, args.scale, args.quality, args.margin_vertical, args.margin_horizontal, args.enable_parallel, uuid_length)
    
    # 處理完畢後，停止記憶體監控線程
    stop_event.set()
    monitor_thread.join()

if __name__ == "__main__":
    main()
