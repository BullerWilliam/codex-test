import asyncio

from playwright.async_api import async_playwright


URL = "https://rplace.live/"
CLOSE_BUTTON_SELECTOR = "#closebtn.noselect"


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            await page.goto(URL, wait_until="domcontentloaded")
            await page.wait_for_selector(CLOSE_BUTTON_SELECTOR, state="visible", timeout=30000)
            await page.wait_for_timeout(5000)
            await page.locator("body").focus()
            await page.keyboard.press("g")
            await page.keyboard.press("Enter")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
