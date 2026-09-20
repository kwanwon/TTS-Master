# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('version.json', '.'), ('core', 'core'), ('ui', 'ui'), ('utils', 'utils'), ('assets', 'assets')],
    hiddenimports=['PyQt6', 'pygame', 'pydub', 'requests', 'numpy', 'openai', 'huggingface_hub', 'PIL'],
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
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name='AIMaster_TTS_Mac',
)
app = BUNDLE(
    coll,
    name='AIMaster_TTS_Mac.app',
    icon='assets/icon.icns',
    bundle_identifier='com.aimaster.tts',
)
