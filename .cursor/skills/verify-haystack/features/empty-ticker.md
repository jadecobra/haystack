# Empty ticker

Analyze stays disabled while the ticker field is blank. On first paint the input is empty, so the button is not clickable. Typing whitespace-only keeps it disabled (`!ticker.trim()`).

## Sub-features

- `empty-disabled` Analyze has `disabled` when `ticker` is empty.
- `empty-ssr` the SSR homepage already serializes that disabled button.
- `empty-whitespace` client handler also returns early if `!ticker.trim()`.

## How to get to it (user POV)

- Open `/` without typing a ticker.
- Clear the ticker field after typing.

## Driving it with verify-haystack

Preconditions:

- Isolated frontend is healthy at `$FRONTEND_ORIGIN`.
- `helpers/doctor` reports `DOCTOR PASS`.

- **GET homepage.** Run `FEATURE=empty-ticker .cursor/skills/verify-haystack/helpers/http empty-ticker`. HTTP 200. `button_disabled=yes` in `home.meta.txt`. Button text is `Analyze` (not `Analyzing...`).
- **Proof.** `artifacts/empty-ticker/home.html` contains a `<button` tag with a `disabled` attribute, placeholder `AAPL or TSLA`, and no `Financial Metrics` table.

## Gotchas

- Disabled is visible in SSR HTML; you do not need Playwright to prove first paint.
- After a ticker is entered the button enables; that state is client-only and is not in the first GET.
- Do not confuse a disabled Analyze with a failed fetch. Empty input never fires `/api/analyze`.
