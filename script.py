
import os
import time
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

load_dotenv(Path(__file__).parent / ".env")
EMAIL    = os.environ.get("LINKEDIN_EMAIL", "")
PASSWORD = os.environ.get("LINKEDIN_PASSWORD", "")
HEADLESS = os.environ.get("HEADLESS", "true").lower() != "false"
LIKE_COUNT = int(os.environ.get("LIKE_COUNT", "10"))


def login(page):
    page.goto("https://www.linkedin.com/login/en-us/", wait_until="domcontentloaded")

    email_input = page.locator('input[autocomplete="username webauthn"]')
    email_input.click()
    email_input.press_sequentially(EMAIL, delay=80)

    password_input = page.locator('input[type="password"]:visible').first
    password_input.click()
    password_input.press_sequentially(PASSWORD, delay=80)

    page.get_by_role("button", name="Sign in", exact=True).filter(visible=True).click()

    try:
        page.wait_for_url("**/feed/**", timeout=15_000)
        print("✅ Logged in successfully.")
    except PlaywrightTimeoutError:
        # May land on an email verification page
        current = page.url
        if "checkpoint" in current or "challenge" in current:
            print("⚠️  LinkedIn is showing a security challenge.")
            print("   Open a browser manually, solve it once, then re-run the script.")
            page.pause()
        elif "feed" not in current:
            print(f"⚠️  Unexpected page after login: {current}")
            sys.exit(1)


def click_load_more(page) -> bool:
    """Click the Load more button if present. Returns True if clicked."""
    btn = page.locator('button:has(span:text-is("Load more"))').first
    try:
        btn.wait_for(state="visible", timeout=2_000)
        btn.scroll_into_view_if_needed()
        btn.click()
        print("  ↻ Clicked 'Load more'")
        time.sleep(2)
        return True
    except Exception:
        return False


def scroll_until_enough_posts(page, needed: int, max_scrolls: int = 30):
    """Scroll the feed until at least `needed` unliked Like buttons are visible,
    falling back to the Load more button when scrolling alone isn't enough."""
    for _ in range(max_scrolls):
        buttons = get_like_buttons(page)
        if len(buttons) >= needed:
            return buttons
        # Scroll down to reveal more posts / trigger the Load more button
        page.evaluate("window.scrollBy(0, 800)")
        time.sleep(1.5)
        # If a Load more button appeared, click it and keep going
        click_load_more(page)
    return get_like_buttons(page)


def get_like_buttons(page):
    """
    Return only the Like buttons that have NOT been pressed yet.
    LinkedIn uses aria-label="Reaction button state: no reaction" for unliked posts.
    Once liked it changes to e.g. "Reaction button state: like reaction".
    """
    return page.locator('button[aria-label="Reaction button state: no reaction"]').all()


def get_post_container(btn):
    return btn.evaluate_handle("""el => {
        let node = el;
        while (node) {
            // LinkedIn post containers have a componentkey and contain both
            // the like button and the author menu — look for the overflow menu
            if (node.querySelector && node.querySelector('[aria-label^="Open control menu for post by"]')) {
                return node;
            }
            node = node.parentElement;
        }
        return document.body;
    }""").as_element()


def like_posts(page, target: int):
    print(f"Looking for {target} posts to like …")
    scroll_until_enough_posts(page, target)

    liked = 0
    while liked < target:
        buttons = get_like_buttons(page)
        remaining = [b for b in buttons][: target - liked]

        if not remaining:
            print("❌ No more like buttons found.")
            break

        for btn in remaining:
            try:
                post = get_post_container(btn)

                # Author
                author = "Unknown"
                menu_btn = post.query_selector('[aria-label^="Open control menu for post by"]')
                if menu_btn:
                    label = menu_btn.get_attribute("aria-label") or ""
                    author = label.replace("Open control menu for post by", "").strip()

                # Preview
                preview = ""
                text_el = post.query_selector('[data-testid="expandable-text-box"]')
                if text_el:
                    preview = text_el.inner_text().strip().replace("\n", " ")[:200]

                btn.scroll_into_view_if_needed()
                btn.click()
                liked += 1
                print(f"  [{liked}/{target}] ✅ Liked")
                print(f"           Author : {author}")
                print(f"           Preview: {preview or '(no text)'}")
                print()
                time.sleep(1.2)

                if liked >= target:
                    break
            except Exception as exc:
                print(f"  ⚠️  Could not process a post: {exc}")

        # If we still need more, scroll/load more and retry
        if liked < target:
            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(1.5)
            click_load_more(page)

    print(f"\n✅ Done — liked {liked} post(s).")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        try:
            login(page)
            time.sleep(2)
            like_posts(page, LIKE_COUNT)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
