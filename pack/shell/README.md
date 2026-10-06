# Windows shell — Open / Quick Preview

| Verb | What |
|------|------|
| **Open** (double-click) | Full Trainz Studio with the mesh |
| **Quick Preview** (context menu) | Fast `--preview` window (`Esc`/`Q` quit, `F` frame) |

Formats: `.trainzmesh` · `.fbx` · `.im` (`.im` = attachments only today)

Explorer **Preview pane (Alt+P)** is **off by default** — Win11 `prevhost` + managed/GL embed is unreliable (white / “can’t be previewed”). Use **Quick Preview** instead. Opt-in only: `register.ps1 -WithExplorerPane`.

## Register (per-user, no admin)

```bat
powershell -ExecutionPolicy Bypass -File trainz_studio\pack\shell\register.ps1 -Source
```

Frozen exe:

```bat
powershell -ExecutionPolicy Bypass -File trainz_studio\pack\shell\register.ps1
```

Unregister:

```bat
powershell -ExecutionPolicy Bypass -File trainz_studio\pack\shell\unregister.ps1
```

## Manual smoke

```bat
python -m trainz_studio --preview path\to\body.trainzmesh
```
