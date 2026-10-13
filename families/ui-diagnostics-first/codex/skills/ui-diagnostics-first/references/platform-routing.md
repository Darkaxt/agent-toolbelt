# Choose The Real Renderer

Read only the relevant platform guidance. These are implementation routes, not
installed integrations, runnable commands or permission to attach to a live target.

## Android Native Views And Compose

Use existing instrumented tests, View inspection or Compose semantics and the
application's debug interfaces. Prefer stable resource IDs/test tags and measured
coordinates to guessed taps. Dispatch supported actions on the UI thread and
observe the real application effect, not just test-tool command completion.

Compose's semantics tree is a test/accessibility representation, not the entire
pixel/layout tree. Merged semantics can hide children; inspect the appropriate
merged/unmerged representation and report custom-drawn or missing elements.
Combine semantics with measured layout and narrowly scoped application-state or
image-loading hooks when the required evidence is not already exposed. A node
existing in semantics does not prove its text/image has been successfully painted.

Tie timing hooks to the current action/data generation. Define data readiness,
actual measured layout, visible binding/image completion and the best available
frame observation separately. Do not pretend a UI-thread/frame callback proves
physical display presentation. Use the project's existing test synchronization and
event channels rather than new sleep-based loops or repeated Gradle builds.
Compose tests can advance a virtual clock; those values are not real loading times.
Use real monotonic application instrumentation for performance claims, and label
synthetic timing or host transport latency separately.

Do not silently fall back to bare UIAutomator dumps or change accessibility services
to obtain a tree. Follow the existing accessibility-preservation contract and
authorized endpoint selection; if unavailable, record the diagnostic gap.
Any required Windows Gradle command still uses its existing shared build gate.

Sources: [Compose semantics](https://developer.android.com/develop/ui/compose/testing/semantics),
[Compose synchronization](https://developer.android.com/develop/ui/compose/testing/synchronization).

## Web, Electron And Android WebView

Reuse the authorized persistent Playwright/CDP debugging session, including an
existing managed Helium instance when applicable. Verify the actual URL, asset/build
identity, window and viewport. Inspect the real DOM/accessibility tree, computed
styles, bounding rectangles, console errors and relevant request/render events.

Use normal locator/DOM actions, not direct API calls disguised as clicks. Record
actual event boundaries for loading, layout and required assets; perpetual network
activity must not become a global readiness requirement. DOM existence, image
download or a requestAnimationFrame callback alone is not proof of final visible
rendering. Retain the explicit limitations of the measurements used.

CDP inspects debuggable web content, not arbitrary native Android Views/Compose.
Enable WebView debugging only within the authorized debug build/session. A browser
recreation may be useful development work when explicitly required, but is not
acceptance evidence for the native Android application.

Source: [Remote debugging WebViews](https://developer.chrome.com/docs/devtools/remote-debugging/webviews).

## Other Native UI Frameworks

Use the framework's real widget/accessibility tree and event dispatch plus scoped
debug state/layout hooks. Preserve the distinction between accessible semantics,
measured geometry and pixels actually rendered. Reuse available tooling rather
than requiring a new cross-platform bridge solely for this skill.
