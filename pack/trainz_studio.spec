# -*- mode: python ; coding: utf-8 -*-
# Build from trainz_studio/:
#   .venv\Scripts\python.exe -m PyInstaller --noconfirm pack\trainz_studio.spec
# Or: pack\build.bat

import os

block_cipher = None

_ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))  # trainz_studio/
_REPO = os.path.abspath(os.path.join(_ROOT, '..'))  # trs22/

a = Analysis(
    [os.path.join(SPECPATH, 'entry.py')],
    pathex=[_REPO, _ROOT],
    binaries=[
        # Assimp DLL for FBX (ctypes load via PKG_ROOT/vendor/…)
        (
            os.path.join(_ROOT, 'vendor', 'assimp', 'Release', 'assimp-vc143-mt.dll'),
            os.path.join('trainz_studio', 'vendor', 'assimp', 'Release'),
        ),
    ],
    datas=[
        (os.path.join(_ROOT, 'assets'), os.path.join('trainz_studio', 'assets')),
    ],
    hiddenimports=[
        'OpenGL',
        'OpenGL.GL',
        'OpenGL.GL.shaders',
        'OpenGL.GLU',
        'numpy',
        'PIL',
        'PIL.Image',
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtOpenGL',
        'PySide6.QtOpenGLWidgets',
        'trainz_studio',
        'trainz_studio.ui.boot',
        'trainz_studio.ui.mesh_preview',
        'trainz_studio.ui.app',
        'trainz_studio.ui.home',
        'trainz_studio.ui.editor',
        'trainz_studio.ui.sounds.studio',
        'trainz_studio.ui.engine',
        'trainz_studio.ui.engine.studio',
        'trainz_studio.ui.engine.throttle_panel',
        'trainz_studio.render.view3d',
        'trainz_studio.io.loaders',
        'trainz_studio.io.assimp_dll',
        'trainz_studio.lamps.bake',
        'trainz_studio.util.hw',
        'trainz_studio.lib',
        'trainz_studio.lib.engine_tuner',
        'trainz_studio.lib.engine_tuner.config_io',
        'trainz_studio.lib.engine_tuner.physics',
        'trainz_studio.lib.engine_tuner.throttle_round',
        'trainz_studio.lib.engine_tuner.autotune',
        'trainz_studio.lib.im_editor',
        'trainz_studio.lib.im_editor.core',
        'trainz_studio.lib.trainzmesh_viewer',
        'trainz_studio.lib.trainzmesh_viewer.parser',
        'trainz_studio.lib.trainzmesh_viewer.textures',
        'matplotlib',
        'matplotlib.backends.backend_qtagg',
        'matplotlib.backends.backend_qt',
        'matplotlib.backends.backend_qt5agg',
        'matplotlib.figure',
        'matplotlib.pyplot',
        'matplotlib.ticker',
        'matplotlib.patches',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'pytest',
        'cupy',
        'cupyx',
        'cuda',
        'numba',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
        'notebook',
        'pyassimp',  # we use ctypes vendor DLL, not pyassimp
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Drop accidental CUDA / CuPy pulls if Analysis still saw them in site-packages.
a.binaries = [
    b for b in a.binaries
    if not any(x in b[0].lower() for x in ('cupy', 'cuda', 'nvidia', 'cublas', 'cudnn'))
]
a.datas = [
    d for d in a.datas
    if not any(x in str(d[0]).lower() for x in ('cupy', 'cuda', 'nvidia'))
]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# onefile: everything in one exe (extracts to %TEMP% on launch)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MSTN_TrainzStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX + Qt/OpenGL DLLs often breaks; skip
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
