# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（onedir）。

用法：.venv/Scripts/python.exe -m PyInstaller --noconfirm --clean fell.spec
产物：dist/Fell/Fell.exe（可整目录压缩分发）。

注意：
- OCR 在 ProcessPoolExecutor 子进程里跑，main.py 已调用 freeze_support()；
- rapidocr 的模型文件是包数据，必须 collect_all，否则 exe 里 OCR 直接报找不到模型；
- 系统 site-packages 里装着 transformers/torch 等大件，显式排除，避免产物膨胀。
"""
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for package in (
    'qfluentwidgets',
    'qframelesswindow',
    'rapidocr_onnxruntime',
    'onnxruntime',
    'av',
    'cv2',
):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

hiddenimports += [
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 本机 site-packages 里同时有全局 PyQt5（其他项目用）与 PySide6，
        # PyInstaller 遇到两个 Qt binding 会直接拒绝构建，必须显式排除。
        'PyQt5',
        'PyQt6',
        'PySide2',
        'onnxruntime.transformers',
        'onnxruntime.tools',
        'tkinter',
        'matplotlib',
        'pandas',
        'scipy',
        'torch',
        'transformers',
        'tensorflow',
        'IPython',
        'jupyter',
        'pytest',
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Fell',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='Fell',
)
