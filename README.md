# House Duty

House Duty is a Home Assistant custom integration for a weekly, ordered household duty rotation. It reads garbage and chore calendars, skips households whose absence calendar overlaps the relevant duty week, and sends reminders through `notify` entities at a configurable time on the preceding evening.

An unavailable household is skipped for that turn. The missed duty is not deferred and does not need to be made up later. Assignments are persisted by duty period and reconciled from an explicit anchor after restarts or downtime, including across year and daylight-saving boundaries.

## Installation

### HACS

1. In HACS, open **Custom repositories**, add this GitHub repository, and select **Integration**.
2. Install **House Duty**, restart Home Assistant, then choose **Settings → Devices & services → Add integration → House Duty**.

### Manual

Copy `custom_components/house_duty` into the same directory under your Home Assistant configuration, restart, and add the integration from the UI. No YAML is required.

## Configuration

Select the garbage and chores calendar entities, reminder time (default 18:00), and broadcast title (default `Gelber Sack`). Add any number of households in rotation order. Every household needs a display name, a `notify` entity/group, and an absence calendar. Finally choose an anchor date and the household responsible for the week containing it.

Create holidays as all-day events in each household's absence calendar. Any timed or all-day event that overlaps any part of a Monday–Monday duty period makes that household unavailable for the whole period. Titles in absence calendars do not matter.

Normal and previously unknown garbage titles go to the assigned household. A normalized, case-insensitive match for the configured broadcast title goes to every household. Chore reminders use the source event title and go to the assigned household. Multiple events remain independent; persisted event keys prevent repeat delivery after a reload or restart.

Options let you change source calendars, reminder time, broadcast title, household details, membership, and order. A membership/order change invalidates old cursor assumptions, so House Duty visibly reports the reset and deterministically rebuilds from the original anchor instead of silently guessing. Use the `house_duty.reset_rotation` action to repair reality explicitly; provide the config-entry ID, an anchor date, and the household ID.

## Status and failures

The integration creates current-duty and next-duty sensors plus a problem binary sensor. Current-duty attributes include period bounds, the originally next household, and skipped households. Missing calendars/notify targets and invalidated rotation state create Home Assistant Repairs issues.

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
