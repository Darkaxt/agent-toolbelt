# Outlook Folder Inventory Design

## Problem

The Outlook helper currently discovers folders by recursively enumerating every
`Folder.Folders` collection. Outlook can materialize that hierarchy in the
visible navigation pane, so read-only searches and incremental cache refreshes
can leave every mailbox branch expanded, including folders used by mail rules.
The helper does not call Explorer or navigation APIs, and Outlook does not
expose a reliable expanded-state restoration API. The correct fix is to avoid
unnecessary hierarchy enumeration.

## Design

The SQLite cache will persist each known folder's `EntryID` together with its
existing `StoreID`, account, selector, and path. Normal cache refresh and
cache-guided search will resolve folders directly with
`NameSpace.GetFolderFromID(entry_id, store_id)`. Default folders may continue to
use `Store.GetDefaultFolder` because that does not enumerate the hierarchy.

Folder discovery becomes explicit. `find-folders` searches the cached folder
inventory by default. `find-folders --rediscover-folders` performs one live
recursive discovery and updates the inventory. `cache-refresh` refreshes known
folders by default; `cache-refresh --rediscover-folders` refreshes the inventory
before reading messages. `sync-mail --refresh-cache` follows the same rule.

If a cached custom folder identity is stale or unavailable, the helper skips it
with a structured warning. It does not silently fall back to a full recursive
scan. The caller can explicitly request rediscovery. A newly empty cache still
includes the standard Inbox, Sent, Drafts, and Trash folders without discovery;
custom folders require one explicit rediscovery.

## Diagnostics

Folder-sensitive operations return `folder_hierarchy_enumerated`,
`folder_inventory_source`, and inventory counts. The value is true only when
the current invocation recursively enumerated live Outlook folders. Warnings
identify stale cached folders and recommend `--rediscover-folders`.

## Safety

- No mail, folder, rule, or navigation state is mutated.
- No attempt is made to programmatically collapse Outlook's navigation pane.
- Existing folder routing and rule destinations remain unchanged.
- Outlook COM execution remains single-lane.
- Recursive discovery is bounded to an explicit user or agent choice.

## Acceptance Criteria

- A warm `cache-refresh` resolves custom folders by EntryID without accessing a
  live `Folders` collection.
- Default `find-folders` returns cached matches without live hierarchy
  enumeration.
- Explicit rediscovery enumerates the hierarchy, persists folder identities,
  and reports that enumeration occurred.
- Stale folder identities produce warnings and do not trigger hidden fallback
  discovery.
- Existing search, draft, cache, and wrapper tests remain green.

