# OIL Development Handoff

Last updated: 2026-07-31

## Current baseline

- Latest published release: `v0.0.8`
- Release commit: `d0fad47`
- Active development branch: `testing`
- Production/server checkout: `/var/www/oil`
- Laptop checkout: `/opt/oil`

## Work completed after 0.0.8

- Added the physical RND Lab 320-KA3005P power-supply driver over its
  documented 9600-baud serial protocol, with voltage/current programming,
  output control, readback, validation, and safe disconnect behavior.
- Renamed the generic Mock instrument to Mock DMM and migrated existing driver
  keys and Mock DMM address schemes.
- Added an authenticated, read-only instrument detail page and restricted
  instrument management and driver tests to administrators.
- New instruments must pass a connection test for their current driver and
  address before they can be saved.
- Added administrator instrument deletion with protected-use handling.
- Added selectable keyboard and double-click navigation to instrument and
  measurement tables.
- Simplified the new-task form to use a task name and optional short
  description.
- Added Single, Continuous, and Loop task execution modes.
  - Single records one synchronized sample.
  - Continuous records samples at the selected interval until stopped.
  - Loop records the selected number of samples at the selected interval.
- New tasks are inserted into the Task list immediately and their status,
  start time, and measurement count update without a page reload.
- Added owner-only deletion of inactive tasks with confirmation.
- Changed task-reading cleanup to cascade so a task and its stored readings can
  be deleted together.
- Moved Stop beside Running and added a confirmation prompt.
- Added an owner-only Mark as completed action for stopped tasks.
- Standardized the completed Task list label as Completed.
- Added cache-busting versions to the Tasks JavaScript asset.

## Database changes after 0.0.8

- `tasks.0003_automationtask_description`
- `tasks.0004_automationtask_measurement_mode`
- `tasks.0005_alter_taskreading_task_instrument`
- `main.0013_rename_mock_driver_to_mock_dmm`
- `main.0014_rename_mock_dmm_address_scheme`
- `main.0015_alter_instrument_driver`

Always run:

```bash
.venv/bin/python manage.py migrate
```

after pulling these changes.

## Verification

- JavaScript syntax:

  ```bash
  node --check tasks/static/tasks/js/task_tabs.js
  ```

- Django project:

  ```bash
  .venv/bin/python manage.py check
  .venv/bin/python manage.py makemigrations --check --dry-run
  .venv/bin/python manage.py test
  ```

- The latest complete run passed 205 tests.

## Data synchronization context

The laptop SQLite database contains the development user, three Mock
instruments, four tasks, 132 task samples, and ten generic task readings.

The server SQLite database contains two users, two physical instruments, 528
stored measurements, and no task records. Instrument primary keys overlap
between databases, so the SQLite files must not be copied over one another and
fixtures must not be loaded without remapping.

Safe merge rules:

1. Back up both SQLite databases.
2. Keep all existing server users, physical instruments, and measurements.
3. Match the laptop owner to the server user by username (`ebaketa`), not by
   numeric primary key.
4. Add the three Mock instruments as new server records and assign new server
   primary keys.
5. Remap task instrument relationships to those new keys.
6. Import the laptop tasks, samples, assignments, and readings.
7. Verify row counts and foreign-key integrity before restarting OIL.

## Next development step

Complete the controlled laptop-to-server data merge, verify the imported task
history in the UI, and then continue refining task and instrument
configuration.
