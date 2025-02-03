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

# -----------------------------
# 自訂型別函式，用於參數驗證
# -----------------------------
def positive_int(value):
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value} 不是一個整數")
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(f"{value} 必須大於 0")
    return ivalue

def non_negative_int(value):
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value} 不是一個整數")
    if ivalue < 0:
        raise argparse.ArgumentTypeError(f"{value} 不能小於 0")
    return ivalue

def positive_float(value):
    try:
        fvalue = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value} 不是一個浮點數")
    if fvalue <= 0:
        raise argparse.ArgumentTypeError(f"{value} 必須大於 0")
    return fvalue

def opacity_type(value):
    try:
        fvalue = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value} 不是一個浮點數")
    if fvalue < 0 or fvalue > 1:
        raise argparse.ArgumentTypeError("透明度必須介於 0 與 1 之間")
    return fvalue

def quality_type(value):
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value} 不是一個整數")
    if ivalue < 1 or ivalue > 100:
        raise argparse.ArgumentTypeError("品質必須介於 1 至 100 之間")
    return ivalue

def scale_type(value):
    try:
        fvalue = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value} 不是一個浮點數")
    if fvalue < 1 or fvalue > 100:
        raise argparse.ArgumentTypeError("縮放比例必須介於 1 至 100 之間")
    return fvalue

def uuid_length_type(value):
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value} 不是一個整數")
    if ivalue < 4 or ivalue > 36:
        raise argparse.ArgumentTypeError("UUID 長度必須介於 4 至 36 之間")
    return ivalue

def existing_file(value):
    if not os.path.isfile(value):
        raise argparse.ArgumentTypeError(f"{value} 不是一個存在的檔案")
    return value

def existing_folder(value):
    if not os.path.isdir(value):
        print(f"警告：輸入資料夾 '{value}' 不存在，將自動建立。")
        os.makedirs(value, exist_ok=True)
    return value

# -----------------------------
# 全域記憶體監控參數與計數
# -----------------------------
MEMORY_CHECK_INTERVAL = 5  # 預設 5 秒
gc_memory_threshold = 500  # 預設 500 MB
gc_batch_size = 20         # 預設每 20 張圖片檢查一次

image_counter = 0
counter_lock = threading.Lock()
stop_event = threading.Event()

# -----------------------------
# 功能函式
# -----------------------------
def get_unique_path(output_path, uuid_length=6):
    base, ext = os.path.splitext(output_path)
    unique_suffix = uuid.uuid4().hex[:uuid_length]
    return f"{base}_{unique_suffix}{ext}"

def adjust_opacity(watermark, opacity):
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
    base_width, base_height = base_image.size
    base_dimension = min(base_width, base_height)
    target_width = int(base_dimension * scale / 100)
    orig_w, orig_h = watermark.size
    ratio = target_width / orig_w
    resample_method = get_resample_method()
    resized = watermark.resize((target_width, int(orig_h * ratio)), resample_method)
    return resized, ratio

def get_position(pos_option, base_size, watermark_size, extra_bottom_scaled=0, margin=15):
    base_width, base_height = base_size
    watermark_width, watermark_height = watermark_size
    allowed_positions = ["left_top", "top", "right_top", "bottom", "right_bottom"]
    if pos_option not in allowed_positions:
        raise argparse.ArgumentTypeError(f"位置參數必須是 {', '.join(allowed_positions)} 其中之一")
    if pos_option == 'left_top':
        x, y = margin, margin
    elif pos_option == 'top':
        x = (base_width - watermark_width) // 2
        y = margin
    elif pos_option == 'right_top':
        x = base_width - watermark_width - margin
        y = margin
    elif pos_option == 'bottom':
        x = (base_width - watermark_width) // 2
        y = base_height - margin - (watermark_height - extra_bottom_scaled)
    elif pos_option == 'right_bottom':
        x = base_width - watermark_width - margin
        y = base_height - margin - (watermark_height - extra_bottom_scaled)
    return (int(x), int(y))

class WatermarkProcessor:
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
            final_output_path = get_unique_path(output_path, uuid_length) if enable_parallel else output_path
            if ext in ['.jpg', '.jpeg'] and quality is not None:
                result.save(final_output_path, quality=quality)
            else:
                result.save(final_output_path)
            print(f"處理成功：{file_path} -> {final_output_path}")
    except Exception as e:
        print(f"處理失敗 {file_path}：{e}")
        sys.exit(1)  # 一旦出現錯誤，立即終止程式

def iter_files(input_folder, recursive):
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
    while not stop_event.is_set():
        time.sleep(monitor_interval)
        mem_used = psutil.Process(os.getpid()).memory_info().rss
        if mem_used > memory_threshold_bytes:
            print(f"[監控] 記憶體使用量達到 {mem_used/(1024*1024):.2f} MB，觸發垃圾回收...")
            gc.collect()

def process_single(file_path, input_folder, output_folder, watermark_processor, position, scale, quality, margin_vertical, margin_horizontal, enable_parallel, uuid_length):
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
    parser.add_argument("--input-folder", "-if", type=existing_folder, default="original",
                        help="輸入資料夾，若不存在則自動建立。預設為 original")
    parser.add_argument("--watermark", "-w", type=existing_file, default="Logo.png",
                        help="浮水印圖片檔案（必須存在且支援 PNG），預設為 Logo.png")
    parser.add_argument("--opacity", "-o", type=opacity_type, default=0.65,
                        help="浮水印透明度（0~1），預設為 0.65")
    parser.add_argument("--position", "-p", type=str, default="bottom",
                        choices=["left_top", "top", "right_top", "bottom", "right_bottom"],
                        help="浮水印位置，預設為 bottom（下方，水平置中）")
    parser.add_argument("--quality", "-q", type=quality_type, default=100,
                        help="輸出圖片壓縮率（1-100），預設為 100")
    parser.add_argument("--scale", "-s", type=scale_type, default=15,
                        help="浮水印縮放比例（1-100），預設為 15")
    parser.add_argument("--margin-vertical", "-mv", type=non_negative_int, default=20,
                        help="直向照片水印與圖片邊緣的間距（像素），預設為 20")
    parser.add_argument("--margin-horizontal", "-mh", type=non_negative_int, default=15,
                        help="橫向照片水印與圖片邊緣的間距（像素），預設為 15")
    parser.add_argument("--output-folder", "-of", type=str, default="output",
                        help="輸出資料夾，預設為 output")
    parser.add_argument("--recursive", "-r", action="store_true", default=False,
                        help="是否遞迴處理子資料夾中的圖片，預設為不處理")
    parser.add_argument("--gc-batch-size", type=positive_int, default=20,
                        help="每處理多少張圖片後進行垃圾回收檢查，預設為 20 張")
    parser.add_argument("--gc-memory-threshold", type=positive_int, default=500,
                        help="記憶體使用量超過此門檻值（MB）時觸發垃圾回收，預設為 500 MB")
    parser.add_argument("--memory-check-interval", type=positive_int, default=5,
                        help="記憶體監控線程檢查間隔（秒），預設為 5 秒")
    parser.add_argument("--enable-mixed-mode", action="store_true", default=False,
                        help="是否啟用混合模式（先檢查記憶體使用量，再依據圖片數量作備用檢查）")
    parser.add_argument("--enable-parallel", action="store_true", default=False,
                        help="是否啟用平行處理功能（預設關閉）；啟用時會在檔案名稱中加入 UUID")
    parser.add_argument("--uuid-length", type=uuid_length_type, default=6,
                        help="平行處理時輸出檔名中 UUID 的長度（4-36），預設為 6")
    parser.add_argument("--config", "-c", type=str, default=None,
                        help="配置文件 (JSON 格式)，若存在則自動讀取")
    args = parser.parse_args()

    # 讀取配置文件（命令列參數具有較高優先權）
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
            sys.exit(1)
    else:
        print(f"找不到配置文件 '{config_filename}'，將使用預設值或命令列參數。")

    # 印出參數摘要（確認後直接進入批量處理，不等待用戶確認）
    params = {
        "input_folder": args.input_folder,
        "watermark": args.watermark,
        "opacity": args.opacity,
        "position": args.position,
        "quality": args.quality,
        "scale": args.scale,
        "margin_vertical": args.margin_vertical,
        "margin_horizontal": args.margin_horizontal,
        "output_folder": args.output_folder,
        "recursive": args.recursive,
        "gc_batch_size": args.gc_batch_size,
        "gc_memory_threshold": args.gc_memory_threshold,
        "memory_check_interval": args.memory_check_interval,
        "enable_mixed_mode": args.enable_mixed_mode,
        "enable_parallel": args.enable_parallel,
        "uuid_length": args.uuid_length
    }
    print("參數驗證通過，參數設定如下：")
    for key, value in params.items():
        print(f"  {key}: {value}")

    input_folder = args.input_folder
    output_folder = args.output_folder

    global gc_batch_size, gc_memory_threshold
    gc_batch_size = args.gc_batch_size
    gc_memory_threshold = args.gc_memory_threshold
    memory_check_interval = args.memory_check_interval
    memory_threshold_bytes = gc_memory_threshold * 1024 * 1024

    uuid_length = args.uuid_length

    # 建立 WatermarkProcessor 物件
    watermark_processor = WatermarkProcessor(args.watermark, args.opacity)

    # 收集所有待處理圖片路徑
    files = list(iter_files(input_folder, args.recursive))

    # 啟動記憶體監控線程
    monitor_thread = threading.Thread(target=memory_monitor, args=(memory_check_interval, memory_threshold_bytes), daemon=True)
    monitor_thread.start()

    if args.enable_parallel:
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
        for file_path in files:
            process_single(file_path, input_folder, output_folder, watermark_processor,
                           args.position, args.scale, args.quality, args.margin_vertical, args.margin_horizontal, args.enable_parallel, uuid_length)
    
    stop_event.set()
    monitor_thread.join()

if __name__ == "__main__":
    main()
