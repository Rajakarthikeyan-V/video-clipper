import os
import sys
import shlex
import subprocess
from scenedetect import VideoManager, SceneManager
from scenedetect.detectors import ContentDetector
from tqdm import tqdm

YT_DLP = "yt-dlp"
FFMPEG = "ffmpeg"


# ---------------------------
# Download YouTube Video
# ---------------------------
def download(url):
    os.makedirs("downloads", exist_ok=True)
    out = os.path.join("downloads", "%(title)s.%(ext)s")

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", out,
        url
    ]

    print("Downloading video...")
    subprocess.check_call(cmd)
    files = sorted([os.path.join("downloads", f) for f in os.listdir("downloads")],
                   key=os.path.getmtime)
    latest = files[-1]
    return os.path.abspath(latest)


# ---------------------------
# Scene Detection
# ---------------------------
def detect_scenes(path):
    print("Detecting scenes...")
    video_manager = VideoManager([path])
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=30.0))

    video_manager.start()
    scene_manager.detect_scenes(frame_source=video_manager)
    scenes = scene_manager.get_scene_list()
    video_manager.release()

    return [(s[0].get_seconds(), s[1].get_seconds()) for s in scenes]


# ---------------------------
# Fallback Sequential Scenes
# ---------------------------
def get_video_length_seconds(path):
    try:
        out = subprocess.check_output([
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            path
        ]).decode().strip()
        return float(out)
    except Exception:
        return 0.0


def make_sequential_scenes(video_path, n, clip_len):
    total = int(get_video_length_seconds(video_path))
    starts = [i * clip_len for i in range(n)]
    scenes = [(s, min(s + clip_len, total)) for s in starts]
    return scenes


# ---------------------------
# Pick Top Scenes
# ---------------------------
def pick_top_scenes(scenes, n):
    if not scenes:
        return []
    scenes_sorted = sorted(scenes, key=lambda s: (s[1] - s[0]), reverse=True)
    return scenes_sorted[:n]


# ---------------------------
# Create Short via FFmpeg
# ---------------------------
def create_short(input_path, start, duration, out_path):
    input_abspath = os.path.abspath(input_path)
    out_abspath = os.path.abspath(out_path)
    print("FFmpeg input:", input_abspath)
    print("FFmpeg output:", out_abspath)

    cmd = [
        FFMPEG,
        "-ss", str(start),
        "-i", input_abspath,
        "-t", str(duration),
        "-y",
        "-filter_complex",
        "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,boxblur[bg];"
        "[0:v]scale=1080:-2[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]",
        "-map", "[v]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        out_abspath
    ]

    # Use subprocess.run to get useful output on failure
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        print("ffmpeg failed — stderr:")
        print(proc.stderr)
        raise subprocess.CalledProcessError(proc.returncode, cmd)

# ---------------------------
# MAIN PROGRAM
# ---------------------------
print("Paste YouTube link:")
url = input("> ").strip()

print("Number of shorts (default 5):")
try:
    n_shorts = int(input("> ").strip())
except:
    n_shorts = 5

print("Short duration in seconds (default 30):")
try:
    short_dur = int(input("> ").strip())
except:
    short_dur = 30

os.makedirs("shorts", exist_ok=True)

# 1. Download
if url.startswith("http"):
    video = download(url)
else:
    video = url

print("\nVideo downloaded at:", video)

# 2. Scene detection (or fallback)
scenes = detect_scenes(video)
if not scenes:
    print("No scenes detected. Using sequential fallback.")
    scenes = make_sequential_scenes(video, n_shorts, short_dur)

# 3. Pick best scenes
chosen = pick_top_scenes(scenes, n_shorts)

# 4. Create shorts
for i, (sstart, send) in enumerate(tqdm(chosen, desc="Creating shorts")):
    start = int(sstart)
    out = os.path.abspath(os.path.join("shorts", f"short_{i+1:02d}.mp4"))

    print("\nCreating short ->", out)
    create_short(video, start, short_dur, out)
    print("Finished ->", out)

print("\nDONE! Your shorts are inside the 'shorts' folder.")
