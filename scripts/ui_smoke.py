"""Drive one pair_survey session end to end in a real browser.

A manual aid, not part of the test suite: the pytest suite covers the config
and API, but the questions are only correct if they also render and gate the
Next button, and that needs the audio elements to actually reach 'ended'.
"""

from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright


def main() -> int:
    """Answer every trial for one rater, then submit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--rater", default="alice")
    parser.add_argument("--shot", default=None, help="write a screenshot here")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        page.goto(f"{args.url}/?rater={args.rater}")
        page.wait_for_selector(".question-block")

        labels = [el.inner_text() for el in page.locator(".audio-card-label").all()]
        print(f"player labels: {labels}")
        if labels != ["Source", "Generated"]:
            print(f"FAIL: expected Source/Generated players, got {labels}")
            return 1
        if page.locator(".stimulus-questions").count() != 0:
            print("FAIL: per-clip question blocks should not render")
            return 1

        total = int(page.locator(".page-counter").inner_text().split("/")[1])
        print(f"trials: {total}")
        print(f"question blocks on page 1: {page.locator('.question-block').count()}")
        print(f"audio cards: {page.locator('.audio-card').count()}")
        rating_locked = page.locator(".rating-btn").first.is_disabled()
        print(f"buttons disabled before playback: {rating_locked}")
        if not rating_locked:
            print("FAIL: rating buttons should stay locked until both clips play")
            return 1

        for trial in range(total):
            # Play both clips through; the buttons stay disabled until then.
            # Seeking near the end keeps the run short, but only once the
            # duration is known - with preload the metadata may not have
            # arrived yet, and currentTime rejects a NaN.
            page.evaluate(
                """async () => {
                    const audios = [...document.querySelectorAll('audio')];
                    await Promise.all(
                        audios.map((a) =>
                            Number.isFinite(a.duration)
                                ? null
                                : new Promise((r) => a.addEventListener('loadedmetadata', r, { once: true }))
                        )
                    );
                    for (const a of audios) {
                        a.currentTime = Math.max(0, a.duration - 0.05);
                        a.play();
                    }
                }"""
            )
            page.wait_for_function(
                "() => ![...document.querySelectorAll('.rating-btn')].some((b) => b.disabled)",
                timeout=10000,
            )
            if trial == 0 and args.shot:
                page.screenshot(path=args.shot, full_page=True)

            for block in page.locator(".question-block").all():
                block.locator(".rating-btn").nth(3).click()

            next_btn = page.locator("#btn-next")
            if next_btn.is_disabled():
                print(f"FAIL: Next still disabled after answering trial {trial + 1}")
                return 1
            next_btn.click()

        page.wait_for_selector(".complete-screen, h2", timeout=10000)
        print("final screen:", page.locator("h1, h2").last.inner_text())
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
