# User activity logs

Open **Activity log** in the sidebar. Users can read/export their own history;
administrators can choose any account, including deleted accounts. **Users →
Activity** opens that user's timeline. Filter by user, date range, and category.
CSV and text downloads include all matching actions (up to 100,000 per export).
Spreadsheet formula prefixes are escaped in CSV exports.

The overview reports successful sign-ins, distinct images involved, event counts,
action categories, and most active images. The timeline uses browser-local time;
exports use UTC. Date filters are inclusive local calendar dates in the UI and
exclusive UTC end boundaries at the API. The category filter applies to the
timeline, while overview statistics retain the whole selected user/date period.

## What is recorded

- Server: sign-ins and sign-outs, password/account changes, uploads, imports,
  analysis requests and completion, measurements, notes/drawings, enhancement
  previews and saves, supporting images, saved workspaces, exports, administrator
  image review, and library/research actions. Failed attributable requests are
  marked failed; unknown usernames are not assigned to an account.
- Browser: selected tools, local labels/probes/supporting-image placement,
  undo/redo, page navigation, display controls, and image closing.
- Presence: each browser page visit, last contact, last page, and estimated
  foreground time. The application visibly discloses tracking in the sidebar.

Request bodies, passwords, session tokens, note contents, keystrokes, and mouse
trails are not copied into the log. Image names and account usernames identify
the work. Browser-originated events are explicitly labelled and are not proof
of human productivity. Authenticated clients may omit or falsify those reports;
server actions are recorded independently. Exports and app UI never expose the
session hash used internally to associate visits with revocable sessions.

## Timing and reliability

The browser reports presence every 30 seconds and on page/visibility changes.
Visible heartbeat gaps up to 90 seconds contribute estimated foreground time.
Long gaps contribute no time. Multiple tabs have independent visits; overlapping
time is not deduplicated. The overview includes time for visits started within
the selected period, rather than claiming precise time worked during the dates.

Explicit sign-out and access revocation end visits on the server. Page closing
or reloading is best-effort browser reporting. After five minutes without contact,
the last contact is the estimated end. Stale visits are finalized when presence
or logs are next requested, not by a background scheduler. A suspended browser,
network loss, or crash cannot provide an exact closing time. Browser event
delivery is best effort; the sidebar indicates interrupted activity connectivity.

## Storage and deployment

Migration 0003 adds `activity_events` and `activity_visits` to the existing SQLite
database. It does not change existing images or ownership. Old activity cannot
be reconstructed. Existing signed-in accounts start recording browser visits
after loading the new frontend; future authenticated server actions are logged
immediately. Administrator account deletion preserves prior activity records.

Migration 0004 adds an enabled-by-default per-user recording switch.
Administrators can use **Manage recording & storage** to toggle recording and
list all-time event/visit counts for every account, including deleted users.
Disabling recording closes active visits and stops server events, browser events,
and presence storage. Re-enabling starts a new visit on the next heartbeat.
No activity is backfilled for disabled periods.

Administrators may preview and confirm deletion for one user or all users,
within explicit dates or all history. Deletion always covers every event category
and visits whose start time falls in the range. It preserves images, inspections,
accounts, and authentication sessions. A fixed preview end time excludes later
activity. Active browsers can start new visits after deletion if recording stays on.
Users cannot manage recording or delete logs. A cleanup summary is recorded in the
administrator's own log if their recording is enabled. No logs are deleted merely
by installing this update. There is no automatic retention policy.

Deleted SQLite pages are reused by future writes; the physical database need not
shrink immediately. Backups and downloaded logs retain their own copies. No live
VACUUM or backup deletion is performed by these controls. The database and
backups remain accessible to trusted server operators; this is not a tamper-proof
external audit store. No automatic retention deletion is configured. Monitor
database/backups as usage grows. Audit-write failures are reported in server logs
without turning a successfully completed user action into a false failure.
