"""生成验收用媒体：h264/mp4 视频、wav/m4a 音频、png/jpg 图片。"""
from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path

import numpy as np
import av
from PIL import Image, ImageDraw


def make_video(path: Path, seconds: float = 2.0) -> None:
    width, height, fps = 320, 240, 24
    container = av.open(str(path), 'w')
    stream = container.add_stream('h264', rate=fps)
    stream.width, stream.height, stream.pix_fmt = width, height, 'yuv420p'
    for i in range(int(seconds * fps)):
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        arr[:, :, 2] = 120  # 深蓝底
        x = (i * 10) % (width - 40)
        arr[100:140, x:x + 40, :] = 255  # 白色移动块
        frame = av.VideoFrame.from_ndarray(arr, format='rgb24')
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def make_wav(path: Path, seconds: float = 2.0) -> None:
    with wave.open(str(path), 'w') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        for i in range(int(44100 * seconds)):
            value = int(15000 * math.sin(2 * math.pi * 440 * i / 44100))
            wav.writeframes(struct.pack('<h', value))


def make_m4a(path: Path, seconds: float = 2.0) -> None:
    container = av.open(str(path), 'w')
    stream = container.add_stream('aac', rate=44100)
    stream.layout = 'mono'
    t = np.arange(int(44100 * seconds))
    tone = (np.sin(2 * math.pi * 440 * t / 44100) * 0.3 * 32767).astype(np.int16)
    frame = av.AudioFrame.from_ndarray(tone[None, :], format='s16', layout='mono')
    frame.sample_rate = 44100
    for packet in stream.encode(frame):
        container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def make_images(png: Path, jpg: Path) -> None:
    image = Image.new('RGB', (640, 360), (30, 30, 60))
    draw = ImageDraw.Draw(image)
    for x in range(640):
        draw.line([(x, 0), (x, 360)], fill=(30 + x // 8, 60, 120 - x // 12))
    draw.rectangle([40, 40, 600, 320], outline=(255, 255, 255), width=4)
    draw.text((80, 160), 'Feel Test Image', fill=(255, 255, 0))
    image.save(png)
    image.resize((320, 240)).save(jpg, quality=90)


def main(out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    make_video(out / 'video.mp4')
    make_wav(out / 'audio.wav')
    make_m4a(out / 'audio.m4a')
    make_images(out / 'image.png', out / 'image.jpg')
    return out


if __name__ == '__main__':
    target = main(sys.argv[1] if len(sys.argv) > 1 else 'C:/tmp/scratch/feel-phase2/media')
    print('media generated at', target)
