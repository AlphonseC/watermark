import os
import sys
import argparse
import gc
import uuid
import time
import threading
import psutil  # 用於監控記憶體使用量
from PIL import Image
import concurrent.futures
import configparser

# -----------------------------
# 自訂型別函式 (參數驗證)
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

def large_image_threshold_type(value):
    ivalue = positive_int(value)
    if ivalue < 100 or ivalue > 10000:
        raise argparse.ArgumentTypeError("large_image_threshold 必須介於 100 至 10000 之間")
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
# 進階記憶體管理功能
# -----------------------------
def advanced_memory_management(file_path, base_img, enable_precompression, large_image_threshold):
    if base_img.width > large_image_threshold or base_img.height > large_image_threshold:
        if enable_precompression:
            factor = min(large_image_threshold / base_img.width, large_image_threshold / base_img.height)
            new_width = int(base_img.width * factor)
            new_height = int(base_img.height * factor)
            print(f"預壓縮：將圖片 {base_img.size} 縮小至 ({new_width}, {new_height})")
            base_img = base_img.resize((new_width, new_height), Image.ANTIALIAS)
    return base_img

def check_and_collect_gc(threshold_bytes):
    mem_used = psutil.Process(os.getpid()).memory_info().rss
    if mem_used > threshold_bytes:
        print(f"[子進程] 記憶體使用量 {mem_used/(1024*1024):.2f} MB 超過門檻，觸發 gc.collect()")
        gc.collect()

# -----------------------------
# 記憶體監控線程
# -----------------------------
def memory_monitor(monitor_interval, memory_threshold_bytes):
    while not stop_event.is_set():
        time.sleep(monitor_interval)
        mem_used = psutil.Process(os.getpid()).memory_info().rss
        if mem_used > memory_threshold_bytes:
            print(f"[監控] 記憶體使用量達到 {mem_used/(1024*1024):.2f} MB，觸發垃圾回收...")
            gc.collect()

# -----------------------------
# 圖片處理功能
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

def process_image(file_path, output_path, watermark_processor, position, scale, quality, margin_vertical, margin_horizontal,
                  enable_parallel, uuid_length, enable_adv_mem, enable_precompression, large_image_threshold, use_process_pool, mem_threshold_bytes):
    try:
        with Image.open(file_path) as base_img:
            if base_img.mode != 'RGBA':
                base_img = base_img.convert('RGBA')
            if enable_adv_mem:
                base_img = advanced_memory_management(file_path, base_img, enable_precompression, large_image_threshold)
            margin_used = margin_vertical if base_img.width < base_img.height else margin_horizontal
            scaled_wm, extra_bottom_scaled = watermark_processor.get_scaled_watermark(base_img, scale)
            pos = get_position(position, base_img.size, scaled_wm.size, extra_bottom_scaled, margin_used)
            result = base_img.copy()
            result.paste(scaled_wm, pos, scaled_wm.split()[3])
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
            if use_process_pool:
                check_and_collect_gc(mem_threshold_bytes)
    except Exception as e:
        print(f"處理失敗 {file_path}：{e}")
        sys.exit(1)

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

def process_single(file_path, input_folder, output_folder, watermark_processor, position, scale, quality,
                   margin_vertical, margin_horizontal, enable_parallel, uuid_length, enable_adv_mem, enable_precompression,
                   large_image_threshold, use_process_pool, mem_threshold_bytes):
    if os.path.isdir(input_folder):
        rel_path = os.path.relpath(os.path.dirname(file_path), input_folder)
        name, ext = os.path.splitext(os.path.basename(file_path))
        out_filename = f"{name}_mk{ext}"
        out_path = os.path.join(output_folder, rel_path, out_filename)
    else:
        name, ext = os.path.splitext(os.path.basename(file_path))
        out_filename = f"{name}_mk{ext}"
        out_path = os.path.join(output_folder, out_filename)
    process_image(file_path, out_path, watermark_processor, position, scale, quality, margin_vertical, margin_horizontal,
                  enable_parallel, uuid_length, enable_adv_mem, enable_precompression, large_image_threshold, use_process_pool, mem_threshold_bytes)
    global image_counter
    with counter_lock:
        image_counter += 1

# -----------------------------
# 配置文件與命令列參數整合
# -----------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="圖片浮水印添加應用程式")
    parser.add_argument("--input-folder", "-if", type=existing_folder, default="original",
                        help="輸入資料夾，若不存在則自動建立。預設為 original")
    parser.add_argument("--watermark", "-w", type=existing_file, default="Logo.png",
                        help="浮水印圖片檔案（必須存在且支援 PNG），預設為 Logo.png")
    parser.add_argument("--opacity", "-o", type=opacity_type, default="0.65",
                        help="浮水印透明度（0~1），預設為 0.65")
    parser.add_argument("--position", "-p", type=str, default="bottom",
                        choices=["left_top", "top", "right_top", "bottom", "right_bottom"],
                        help="浮水印位置，預設為 bottom（下方，水平置中）")
    parser.add_argument("--quality", "-q", type=quality_type, default="100",
                        help="輸出圖片壓縮率（1-100），預設為 100")
    parser.add_argument("--scale", "-s", type=scale_type, default="15",
                        help="浮水印縮放比例（1-100），預設為 15")
    parser.add_argument("--margin-vertical", "-mv", type=non_negative_int, default="20",
                        help="直向照片水印與圖片邊緣的間距（像素），預設為 20")
    parser.add_argument("--margin-horizontal", "-mh", type=non_negative_int, default="15",
                        help="橫向照片水印與圖片邊緣的間距（像素），預設為 15")
    parser.add_argument("--output-folder", "-of", type=str, default="output",
                        help="輸出資料夾，預設為 output")
    parser.add_argument("--recursive", "-r", action="store_true", default=False,
                        help="是否遞迴處理子資料夾中的圖片，預設為不處理")
    parser.add_argument("--gc-batch-size", type=positive_int, default="20",
                        help="每處理多少張圖片後進行垃圾回收檢查，預設為 20 張")
    parser.add_argument("--gc-memory-threshold", type=positive_int, default="500",
                        help="記憶體使用量超過此門檻值（MB）時觸發垃圾回收，預設為 500 MB")
    parser.add_argument("--memory-check-interval", type=positive_int, default="5",
                        help="記憶體監控線程檢查間隔（秒），預設為 5 秒")
    parser.add_argument("--enable-mixed-mode", action="store_true", default=False,
                        help="是否啟用混合模式（先檢查記憶體使用量，再依據圖片數量作備用檢查）")
    parser.add_argument("--enable-parallel", action="store_true", default=False,
                        help="是否啟用平行處理功能（預設關閉）；啟用時會在檔案名稱中加入 UUID")
    parser.add_argument("--uuid-length", type=uuid_length_type, default="6",
                        help="平行處理時輸出檔名中 UUID 的長度（4-36），預設為 6")
    parser.add_argument("--enable-advanced-memory-management", action="store_true", default=False,
                        help="是否啟用進階記憶體管理功能（在多線程模式下對超大圖片進行進階管理）")
    parser.add_argument("--enable-precompression", action="store_true", default=False,
                        help="進階記憶體管理模式下是否啟用預壓縮大型圖片（降低解析度），預設為關閉")
    parser.add_argument("--large-image-threshold", type=large_image_threshold_type, default="3000",
                        help="當圖片寬或高超過此像素值時啟用進階記憶體管理功能（預壓縮）的判斷，介於 100 至 10000 之間，預設為 3000")
    parser.add_argument("--config", "-c", type=str, default=None,
                        help="配置文件 (INI 格式)，若存在則自動讀取")
    return parser.parse_args()

def merge_config(args):
    config_filename = args.config if args.config else "config.ini"
    if os.path.exists(config_filename):
        config = configparser.ConfigParser()
        try:
            config.read(config_filename, encoding="utf-8")
            defaults = config["DEFAULT"]
            arg_map = {
                "input_folder": ("--input-folder", existing_folder, "original"),
                "watermark": ("--watermark", existing_file, "Logo.png"),
                "opacity": ("--opacity", opacity_type, "0.65"),
                "position": ("--position", str, "bottom"),
                "quality": ("--quality", quality_type, "100"),
                "scale": ("--scale", scale_type, "15"),
                "margin_vertical": ("--margin-vertical", non_negative_int, "20"),
                "margin_horizontal": ("--margin-horizontal", non_negative_int, "15"),
                "output_folder": ("--output-folder", str, "output"),
                "recursive": ("--recursive", lambda x: x.lower() in ["true", "1", "yes"], "False"),
                "gc_batch_size": ("--gc-batch-size", positive_int, "20"),
                "gc_memory_threshold": ("--gc-memory-threshold", positive_int, "500"),
                "memory_check_interval": ("--memory-check-interval", positive_int, "5"),
                "enable_mixed_mode": ("--enable-mixed-mode", lambda x: x.lower() in ["true", "1", "yes"], "False"),
                "enable_parallel": ("--enable-parallel", lambda x: x.lower() in ["true", "1", "yes"], "False"),
                "uuid_length": ("--uuid-length", uuid_length_type, "6"),
                "enable_advanced_memory_management": ("--enable-advanced-memory-management", lambda x: x.lower() in ["true", "1", "yes"], "False"),
                "enable_precompression": ("--enable-precompression", lambda x: x.lower() in ["true", "1", "yes"], "False"),
                "large_image_threshold": ("--large-image-threshold", large_image_threshold_type, "3000")
            }
            for key, (flag, typ, default_val) in arg_map.items():
                if not any(flag in sys.argv for flag in [flag.split()[0]]):
                    raw_val = defaults.get(key, default_val)
                    if key in ["recursive", "enable_mixed_mode", "enable_parallel", "enable_advanced_memory_management", "enable_precompression"]:
                        setattr(args, key, defaults.getboolean(key, False))
                    else:
                        setattr(args, key, typ(raw_val))
        except Exception as e:
            print(f"讀取配置文件失敗：{e}")
            sys.exit(1)
    else:
        print(f"找不到配置文件 '{config_filename}'，將使用命令列參數或預設值。")
    return args

def main():
    args = merge_config(parse_args())
    mem_threshold_bytes = args.gc_memory_threshold * 1024 * 1024

    # 選擇平行處理執行器：若啟用平行處理且進階記憶體管理同時啟用，使用 ProcessPoolExecutor
    use_process_pool = args.enable_parallel and args.enable_advanced_memory_management
    if args.enable_parallel:
        Executor = concurrent.futures.ProcessPoolExecutor if use_process_pool else concurrent.futures.ThreadPoolExecutor
    else:
        Executor = None

    watermark_processor = WatermarkProcessor(args.watermark, args.opacity)
    files = list(iter_files(args.input_folder, args.recursive))

    monitor_thread = threading.Thread(target=memory_monitor, args=(args.memory_check_interval, mem_threshold_bytes), daemon=True)
    monitor_thread.start()

    if args.enable_parallel:
        with Executor() as executor:
            futures = [
                executor.submit(
                    process_single,
                    file_path,
                    args.input_folder,
                    args.output_folder,
                    watermark_processor,
                    args.position,
                    args.scale,
                    args.quality,
                    args.margin_vertical,
                    args.margin_horizontal,
                    args.enable_parallel,
                    args.uuid_length,
                    args.enable_advanced_memory_management,
                    args.enable_precompression,
                    args.large_image_threshold,
                    use_process_pool,
                    mem_threshold_bytes
                )
                for file_path in files
            ]
            concurrent.futures.wait(futures)
    else:
        for file_path in files:
            process_single(file_path, args.input_folder, args.output_folder, watermark_processor,
                           args.position, args.scale, args.quality, args.margin_vertical, args.margin_horizontal,
                           args.enable_parallel, args.uuid_length,
                           args.enable_advanced_memory_management, args.enable_precompression, args.large_image_threshold,
                           False, mem_threshold_bytes)
    
    # 程式結束前，釋放資源並呼叫 gc.collect()
    del files, watermark_processor
    gc.collect()
    stop_event.set()
    monitor_thread.join()
    sys.exit(0)

if __name__ == "__main__":
    main()
