# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('version.json', '.'), ('core', 'core'), ('ui', 'ui'), ('utils', 'utils'), ('assets', 'assets'), ('effects', 'effects')],
    hiddenimports=['PyQt6', 'pygame', 'pydub', 'requests', 'numpy', 'soundfile', 'openai', 'huggingface_hub', 'PIL', 'edge_tts', 'aiohttp', 'tabulate', 'certifi'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AIMaster_TTS_Mac',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.icns',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='AIMaster_TTS_Mac',
)
app = BUNDLE(
    coll,
    name='AIMaster_TTS_Mac.app',
    icon='assets/icon.icns',
    bundle_identifier='com.aimaster.tts',
    info_plist={
        'CFBundleDisplayName': 'AIMaster_TTS_Mac',
        'CFBundleName': 'AIMaster_TTS_Mac',
        'CFBundleIconFile': 'icon',
        'NSHighResolutionCapable': True,
        'NSDesktopFolderUsageDescription': '배경음악 및 훈련 음원 파일을 불러오고 저장하기 위해 데스크톱 폴더 접근 권한이 필요합니다.',
        'NSDocumentsFolderUsageDescription': '훈련 템플릿 및 음원 파일을 불러오고 저장하기 위해 문서 폴더 접근 권한이 필요합니다.',
        'NSDownloadsFolderUsageDescription': '다운로드한 배경음악 파일을 불러오기 위해 다운로드 폴더 접근 권한이 필요합니다.',
    },
)
