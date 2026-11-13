"""Static interface clues and optional Playwright runtime diagnostics."""

import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

from .common import Candidate, Report, read_bytes
from .encoding import FLAG


class Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.resources = []
        self.hidden = []
        self.comments = []
        self.scripts = []
        self.in_script = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.append(attributes["id"])
        for key in ("src", "href"):
            if attributes.get(key):
                self.resources.append((tag, attributes[key]))
        style = re.sub(r"\s+", "", attributes.get("style", "") or "").lower()
        if "hidden" in attributes or re.search(
            r"display:none|visibility:hidden|opacity:0(?:;|$)", style
        ):
            self.hidden.append({"tag": tag, "id": attributes.get("id"), "style": style})
        if tag == "script":
            self.in_script = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_script:
            self.scripts.append(data)

    def handle_comment(self, data):
        self.comments.append(data)


def inspect_html(text: str, base: Path | None = None) -> Report:
    document = Document()
    document.feed(text)
    report = Report(
        "web",
        facts={
            "mode": "static",
            "hidden_elements": document.hidden,
            "resources": document.resources,
        },
    )
    for name, occurrences in Counter(document.ids).items():
        if occurrences > 1:
            report.candidates.append(
                Candidate(
                    f"Duplicate id: {name}",
                    0.95,
                    [f"ID appears {occurrences} times; selectors may target the wrong element."],
                    "diagnosis",
                )
            )
    for element in document.hidden:
        report.candidates.append(
            Candidate(
                f"Hidden {element['tag']} #{element['id'] or '(no id)'}",
                0.65,
                [str(element)],
                "inspection clue",
            )
        )
    scripts = "\n".join(document.scripts)
    for match in re.finditer(
        r"""(?:querySelector\(\s*["']#([^"']+)["']|getElementById\(\s*["']([^"']+)["'])""", scripts
    ):
        name = match[1] or match[2]
        if name not in document.ids:
            report.candidates.append(
                Candidate(
                    f"Selector refers to absent id: {name}",
                    0.80,
                    [match[0], "Absent in static HTML; may be created dynamically."],
                    "diagnosis",
                )
            )
    for flag in FLAG.findall(text):
        report.candidates.append(
            Candidate(
                flag, 0.95, ["Flag-shaped text in HTML source; verify its role."], "source clue"
            )
        )
    for comment in document.comments:
        if re.search(r"(?i)secret|password|todo|fixme|flag", comment):
            report.candidates.append(
                Candidate(comment.strip()[:500], 0.70, ["HTML comment"], "source clue")
            )
    if base is not None:
        root = base.parent.resolve()
        for tag, resource in document.resources:
            parts = urlsplit(resource)
            if parts.scheme or parts.netloc or not parts.path or parts.path.startswith("/"):
                continue
            candidate = (root / unquote(parts.path)).resolve()
            if not candidate.is_relative_to(root):
                report.warnings.append(f"Skipped resource outside document directory: {resource}")
            elif not candidate.exists():
                report.candidates.append(
                    Candidate(
                        f"Missing local resource: {resource}",
                        0.9,
                        [f"{tag} references a file absent relative to {base.name}"],
                        "diagnosis",
                    )
                )
    report.warnings.append(
        "Static analysis does not execute JavaScript or compute CSS; dynamic selectors may be valid."
    )
    report.next_steps = [
        "Use --browser for runtime errors, failed requests, computed hidden elements, and an optional explicit --click selector."
    ]
    return report.rank()


def inspect(
    target: str, browser: bool = False, click: list[str] | None = None, timeout: float = 10
) -> Report:
    if not 0 < timeout <= 60:
        raise ValueError("Timeout must be greater than 0 and at most 60 seconds.")
    if click and not browser:
        raise ValueError("--click requires --browser.")
    remote = target.startswith(("http://", "https://"))
    path = None if remote else Path(target).resolve()
    url = target if remote else path.as_uri()
    http_status = None
    if remote:
        try:
            response = urlopen(
                Request(target, headers={"User-Agent": "OKTO-Toolkit/1.0"}), timeout=timeout
            )
        except HTTPError as exc:
            response = exc  # Retain useful HTML/error evidence, including 404 and 500 pages.
        with response:
            http_status = response.status
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError("HTML exceeds 2 MiB; save the relevant document locally.")
            text = raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    else:
        text = read_bytes(path, 2 * 1024 * 1024).decode("utf-8-sig", errors="replace")
    report = inspect_html(text, path)
    report.facts["target"] = target
    if http_status is not None:
        report.facts["http_status"] = http_status
        if http_status >= 400:
            report.candidates.append(
                Candidate(
                    f"HTTP {http_status}: {target}",
                    0.95,
                    ["Observed when fetching the page."],
                    "runtime evidence",
                )
            )
    if not browser:
        return report.rank()
    try:
        from playwright.sync_api import Error as BrowserError
        from playwright.sync_api import sync_playwright
    except ImportError:
        report.warnings.append(
            "Runtime inspection unavailable. Install the web extra and run: py -m playwright install chromium"
        )
        return report
    try:
        with sync_playwright() as playwright:
            instance = playwright.chromium.launch()
            try:
                page = instance.new_page()
                page.set_default_timeout(timeout * 1000)
                errors, failed, http_errors = [], [], []
                page.on(
                    "pageerror",
                    lambda error: errors.append(str(error)[:1000]) if len(errors) < 100 else None,
                )
                page.on(
                    "console",
                    lambda message: (
                        errors.append(message.text[:1000])
                        if message.type == "error" and len(errors) < 100
                        else None
                    ),
                )
                page.on(
                    "requestfailed",
                    lambda request: (
                        failed.append({"url": request.url, "error": request.failure})
                        if len(failed) < 100
                        else None
                    ),
                )
                page.on(
                    "response",
                    lambda response: (
                        http_errors.append({"url": response.url, "status": response.status})
                        if response.status >= 400 and len(http_errors) < 100
                        else None
                    ),
                )
                try:
                    page.goto(url, wait_until="load", timeout=timeout * 1000)
                    for selector in click or []:
                        page.locator(selector).click(timeout=timeout * 1000)
                    page.wait_for_timeout(750)
                except BrowserError as exc:
                    report.warnings.append(f"Navigation/action incomplete: {str(exc)[:500]}")
                runtime = {"errors": errors, "failed_requests": failed, "http_errors": http_errors}
                try:
                    runtime["hidden_elements"] = (
                        page.evaluate("""() => Array.from(document.querySelectorAll('body *')).slice(0, 10000).filter(el => {
                        const s = getComputedStyle(el); return s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity) === 0;
                    }).slice(0, 100).map(el => ({tag:el.tagName, id:el.id, text:(el.textContent || '').slice(0,200)}))""")
                    )
                except BrowserError as exc:
                    report.warnings.append(f"DOM inspection incomplete: {str(exc)[:300]}")
                report.facts.update(mode="browser", runtime=runtime)
                for error in errors:
                    report.candidates.append(
                        Candidate(
                            error,
                            0.95,
                            ["Observed browser error; root cause requires inspection."],
                            "runtime evidence",
                        )
                    )
                for failure in failed + http_errors:
                    report.candidates.append(
                        Candidate(
                            str(failure),
                            0.92,
                            ["Observed network failure after navigation/actions."],
                            "runtime evidence",
                        )
                    )
            finally:
                instance.close()
    except BrowserError as exc:
        report.warnings.append(
            f"Runtime inspection unavailable: {str(exc)[:500]}. Static results retained; verify Chromium installation."
        )
    report.next_steps = [
        "Inspect error locations and request responses; reproduce the broken flow with explicit --click selectors.",
        "Diagnostics suggest causes but do not automatically modify the site.",
    ]
    return report.rank()
