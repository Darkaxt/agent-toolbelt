# Browser routing for public FedEx pages

Use the available browser tool's current documentation. Do not launch a separate headless browser merely because a generic retrieval tool failed; an existing normal public tab may already contain the needed details.

## Codex cua_repl

On the first call or after a kernel reset, execute exactly the permitted entry point, for example:

```javascript
await cua.getState();
```

Inspect the returned inventory. Match the official FedEx tab and requested tracking number even if the open URL has extra query parameters. Select it with the observed tab and browser IDs:

```javascript
let trackingTab = await cua.getTab(observedTabId, {browser: observedBrowserId});
```

Read the returned API documentation and initial accessibility state. Follow browser session naming instructions. Use documented semantic controls grounded in that state, for example when this exact button is present:

```javascript
await trackingTab.playwright.getByRole("button", {
  name: "View more details", exact: true
}).click();
```

Read the resulting DOM snapshot or rendered screenshot through the documented API. If a DOM/CDP read errors after a click, inspect the screenshot before repeating the action:

```javascript
await nodeRepl.emitImage(await trackingTab.screenshot({fullPage: true}));
```

A full-page screenshot can show shipment facts beneath travel history, but may not include every row of an internally scrolling piece table. Use documented read-only scrolling/locators where available; otherwise report the omitted rows. Do not claim a screenshot proves hidden content was read.

For a tool error, consult its browser troubleshooting documentation and use only documented alternatives. Do not guess hidden methods, inspect application secrets or swap to an unapproved control mechanism. Keep the selected browser binding unless it is explicitly disconnected. Do not repeatedly perform URL-only discovery when tab inventory already identifies the page. Leave the user's existing tab open; close only task-created disposable tabs under the browser tool's lifecycle rules.
