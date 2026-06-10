#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


EDGE_PATHS = (
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
)
NODE_PATH = Path(
    "C:/Users/Bruger/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"
)
NODE_MODULES = Path(
    "C:/Users/Bruger/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules"
)
PNPM_NODE_MODULES = NODE_MODULES / ".pnpm" / "node_modules"
TARGET_URL = "https://rplace.live/"


def find_edge() -> str:
    override = os.environ.get("EDGE_PATH")
    if override and Path(override).is_file():
        return override

    for candidate in EDGE_PATHS:
        if candidate.is_file():
            return str(candidate)

    raise FileNotFoundError("Could not find Microsoft Edge. Set EDGE_PATH if needed.")


def build_runner_script(
    edge_path: str,
    user_data_dir: str,
    wait_after_button: float,
    hold_seconds: int,
    selector_state: str,
) -> str:
    return f"""\
const {{ chromium }} = require("playwright");

async function waitForCloseButton(page, state, timeoutMs) {{
  const deadline = Date.now() + timeoutMs;
  const context = page.context();

  async function currentPage() {{
    if (!page.isClosed()) {{
      return page;
    }}
    const pages = context.pages().filter((candidate) => !candidate.isClosed());
    if (pages.length) {{
      page = pages[pages.length - 1];
      return page;
    }}
    page = await context.newPage();
    await page.goto({TARGET_URL!r}, {{ waitUntil: "domcontentloaded" }});
    return page;
  }}

  while (Date.now() < deadline) {{
    const activePage = await currentPage();
    for (const frame of activePage.frames()) {{
      try {{
        const locator = frame.locator("#closebtn");
        const count = await locator.count();
        if (!count) {{
          continue;
        }}
        if (state === "attached") {{
          return;
        }}
        if (await locator.first().isVisible()) {{
          return;
        }}
      }} catch (error) {{
        if (!String(error).includes("Frame was detached")) {{
          throw error;
        }}
      }}
    }}
    await activePage.waitForTimeout(500);
  }}

  throw new Error(`Timed out waiting for #closebtn with state "${{state}}"`);
}}

(async () => {{
  const context = await chromium.launchPersistentContext({user_data_dir!r}, {{
    headless: false,
    executablePath: {edge_path!r},
    args: ["--new-window"],
  }});

  try {{
    const page = context.pages()[0] || await context.newPage();
    await page.goto({TARGET_URL!r}, {{ waitUntil: "domcontentloaded" }});
    await waitForCloseButton(page, {selector_state!r}, 90000);
    await page.waitForTimeout({int(wait_after_button * 1000)});
    await page.bringToFront();
    await page.keyboard.press("g");
    await page.keyboard.press("Enter");
    console.log("Pressed g and Enter on {TARGET_URL}");
    await page.waitForTimeout({hold_seconds * 1000});
  }} finally {{
    await context.close();
  }}
}})().catch((error) => {{
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}});
"""


def run_browser_sequence(
    edge_path: str,
    wait_after_button: float,
    hold_seconds: int,
    selector_state: str,
) -> None:
    if not NODE_PATH.is_file():
        raise FileNotFoundError(f"Could not find Node.js at {NODE_PATH}")
    if not NODE_MODULES.is_dir():
        raise FileNotFoundError(f"Could not find node_modules at {NODE_MODULES}")

    temp_dir = tempfile.mkdtemp(prefix="edge-bot-node-")
    user_data_dir = tempfile.mkdtemp(prefix="edge-bot-profile-")
    script_path = Path(temp_dir) / "run_rplace.js"
    script_path.write_text(
        build_runner_script(
            edge_path,
            user_data_dir=user_data_dir,
            wait_after_button=wait_after_button,
            hold_seconds=hold_seconds,
            selector_state=selector_state,
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["NODE_PATH"] = os.pathsep.join((str(NODE_MODULES), str(PNPM_NODE_MODULES)))

    try:
        subprocess.run(
            [str(NODE_PATH), str(script_path)],
            check=True,
            env=env,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        shutil.rmtree(user_data_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Open rplace.live in Edge, wait for #closebtn, then press g and Enter."
    )
    parser.add_argument(
        "--wait-after-button",
        type=float,
        default=5.0,
        help="Seconds to wait after #closebtn becomes visible before sending keys.",
    )
    parser.add_argument(
        "--hold-seconds",
        type=int,
        default=20,
        help="How long to leave Edge open after pressing Enter.",
    )
    parser.add_argument(
        "--selector-state",
        choices=("attached", "visible"),
        default="attached",
        help="Whether #closebtn must exist in the DOM or also be visible before continuing.",
    )
    args = parser.parse_args()

    try:
        edge_path = find_edge()
        run_browser_sequence(
            edge_path,
            wait_after_button=args.wait_after_button,
            hold_seconds=args.hold_seconds,
            selector_state=args.selector_state,
        )
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
