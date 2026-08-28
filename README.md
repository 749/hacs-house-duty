# House Duty

House Duty is a Home Assistant custom integration for a weekly, ordered household duty rotation. It reads garbage and chore calendars, skips households whose absence calendar overlaps the relevant duty week, and sends reminders through `notify` entities at a configurable time on the preceding evening.

An unavailable household is skipped for that turn. The missed duty is not deferred and does not need to be made up later. Assignments are persisted by duty period and reconciled from an explicit anchor after restarts or downtime, including across year and daylight-saving boundaries.

## Installation

### HACS

1. In HACS, open **Custom repositories**, add this GitHub repository, and select **Integration**.
2. Install **House Duty**, restart Home Assistant, then choose **Settings → Devices & services → Add integration → House Duty**.

### Manual

Copy `custom_components/house_duty` into the same directory under your Home Assistant configuration, restart, and add the integration from the UI. No YAML is required.

## Step-by-step setup

### 1. Prepare the source calendars

Create or identify two Home Assistant calendar entities:

1. A **garbage calendar** containing collection events. The event summary becomes the garbage type shown in notifications. No whitelist is needed; unknown titles are handled automatically.
2. A **chores calendar** containing shared jobs such as `Clean front door porch`. The event summary becomes the chore text.

House Duty reads these calendars only. It does not create, edit, or delete their events.

### 2. Prepare household notification targets (optional)

For each household that should receive messages, create or identify a Home Assistant `notify` entity. A notify group is useful when one household has several recipients.

This field is optional. A household without a notification target still participates in the rotation, but House Duty cannot deliver its assigned or broadcast messages anywhere.

### 3. Prepare absence calendars (optional)

Create a separate calendar for each household whose holidays should affect the rotation. Add holidays as all-day events; event titles do not matter. A timed event also works.

Any absence event overlapping any part of a Monday–Monday duty period makes that household unavailable for the entire period. A household without an absence calendar is always considered available.

### 4. Add House Duty

Go to **Settings → Devices & services → Add integration → House Duty**, then configure:

1. Select the garbage calendar.
2. Select the chores calendar.
3. Choose the reminder time. The default is 18:00 on the evening before an event starts.
4. Enter one or more garbage event titles that should notify everyone. The default list contains `Gelber Sack`. Matching ignores case and repeated whitespace.
5. Review the preview. House Duty displays up to the next three matching garbage events per broadcast title found during the coming year. An em dash means no match was found or the calendar preview was unavailable; it does not prevent setup.

### 5. Add households in rotation order

For every household:

1. Enter its display name.
2. Optionally select its notification target.
3. Optionally select its absence calendar.
4. Choose whether to add another household.

The number of households is not limited. Their setup order is their initial rotation order.

### 6. Anchor the rotation

Choose a past or current date and the household that was actually responsible during the Monday–Sunday week containing that date. This confirmed anchor assignment is authoritative. House Duty reconstructs subsequent weeks from it and persists the resulting assignments across restarts and upgrades.

Example: if Apartment B is responsible this week, select any date in this week and choose **Apartment B**.

### 7. Verify the entities

After setup, check the House Duty device for:

- **Current duty household** — the current assignment and any households skipped for this period.
- **Next duty household** — a preview that considers known absences.
- **Problem** — active when assignment or configured resources need attention.

## Notification and rotation behavior

Normal and previously unknown garbage titles go to the assigned household. A normalized match for any configured broadcast title goes to every household that has a notification target. Chore reminders use the source event title and go to the assigned household. Multiple events remain independent; persisted per-recipient delivery keys prevent repeat messages after a reload or restart.

An unavailable household is skipped for that occurrence of its turn. The missed duty is not deferred and does not need to be made up later.

## Changing the setup

Open the integration's **Configure** dialog to:

- change calendars, reminder time, broadcast-title list, or rotation order;
- preview the next three matching broadcast events after editing the list;
- add, rename, edit, or remove households;
- add, clear, or change optional notification targets and absence calendars;
- explicitly repair or re-anchor the rotation.

A membership/order change invalidates old cursor assumptions, so House Duty reports the reset and deterministically rebuilds from the anchor instead of silently guessing. The `house_duty.reset_rotation` action provides the same explicit repair capability for automations or Developer Tools; provide the config-entry ID, anchor date, and household ID.

## Status and failures

The integration creates current-duty and next-duty sensors plus a problem binary sensor. Current-duty attributes include period bounds, the originally next household, and skipped households. Missing calendars/notify targets and invalidated rotation state create Home Assistant Repairs issues.

If an absence calendar cannot be read while the next week is being previewed, the sensor keeps a best-effort assignment instead of becoming `Unknown`. Its `unavailable_absence_calendars` attribute identifies calendars whose absence information could not be considered, and Home Assistant creates a Repair for each one.

During a Home Assistant restart, House Duty waits for startup to complete before querying calendars. This allows calendar-providing integrations to register their entities before reconciliation begins.

### Debug logging

To troubleshoot calendar reads or assignment state, add this to `configuration.yaml` and restart Home Assistant:

```yaml
logger:
  logs:
    custom_components.house_duty: debug
```

Reload House Duty once, then inspect **Settings → System → Logs**. Debug output includes queried calendar IDs and time ranges, event counts, reconciliation cursors, resolved household IDs, sensor values, and unreadable calendars. Event contents and notification messages are not logged.

## Releases

Releases are derived from Conventional Commits on `main`. Release Please maintains a release pull request containing the changelog and semantic version bump (`fix` → patch, `feat` → minor, and `BREAKING CHANGE` → major). Merging that pull request creates the version tag and GitHub release automatically and updates the integration manifest, Python project metadata, and lockfile together.

If everyone is absent, nobody is assigned. House Duty creates a Repairs issue and fires `house_duty_assignment_problem`; it consumes one complete cycle without changing who is originally next for the following week. Arrange that week manually and use the reset action only if the real rotation changed.

## Upgrading and troubleshooting

Upgrade in HACS and restart or reload the integration. If reminders do not arrive, check the problem entity, Repairs dashboard, calendar visibility, notify-entity availability, Home Assistant time zone, and the configured reminder time. House Duty catches up a reminder due later than its configured time when Home Assistant starts that evening.

## Development

Use Python 3.14.2 or newer. Install the test extra, then run:

```shell
pytest
ruff check .
```

GitHub Actions also runs HACS validation and Hassfest. A public GitHub repository, repository description/topics/issues, brand registration, and an actual GitHub release are host-side publication steps that cannot be represented by files alone.

Maintainers create a release by pushing a version tag matching the integration manifest, for example `v0.1.0`. The release workflow publishes a GitHub release with generated notes; tags without the `v` prefix do not trigger publication.
