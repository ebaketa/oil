# OIL Development Handoff

Last updated: 2026-07-30

## Current baseline

- Latest published release: `v0.0.8`
- Release commit: `d0fad47`
- Active development branch: `testing`
- Production/server checkout: `/var/www/oil`
- Laptop checkout: `/opt/oil`

## Work completed after 0.0.8

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

- The latest complete run passed 181 tests.

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
