# Multi Mouse Overlay

A Windows-only Python prototype that tracks multiple physical mice independently with the Raw Input API and draws an always-on-top overlay cursor for each mouse.

## What it does

- Shows a Tkinter control window with an **Enable / Disable** button.
- Registers for Windows Raw Input mouse packets so separate wired/Bluetooth mice can be tracked independently.
- Draws a transparent click-through overlay cursor per physical mouse.
- Keeps the real Windows cursor synchronized to the current main mouse so normal `GetCursorPos` calls report that cursor.
- Lets you middle-click any mouse to make that mouse the main cursor.
- Optionally requests `RIDEV_NOLEGACY` while enabled, which asks Windows not to produce legacy mouse messages for this app's raw-input registration.
- Optionally injects best-effort left/right click and scroll events for non-main overlay cursors at their overlay positions.

## Important limitation

Windows exposes only one real desktop cursor to normal applications. A user-mode Python app cannot perfectly force every existing Windows app, browser, or HTML element to natively understand multiple independent hover cursors. For perfect behavior across all apps, you would need a kernel-mode HID/filter driver or per-application integration such as a browser extension/game plugin.

This app therefore uses the best user-mode approximation:

1. The selected main mouse controls the real Windows cursor, so calls like `GetCursorPos` report that cursor.
2. Extra mice get visual overlay cursors.
3. Extra mouse clicks and scrolls are injected as normal Windows mouse input at the extra cursor position when the option is enabled.

## Run from source

```powershell
python app.py
```

Use Windows 10/11 and run from a normal desktop session. If another elevated app is focused, start this app as administrator so Windows allows input injection into that elevated app.

## Build an exe

```powershell
python -m pip install pyinstaller
pyinstaller --noconsole --onefile --name MultiMouseOverlay app.py
```

The exe will be created in `dist\MultiMouseOverlay.exe`.
