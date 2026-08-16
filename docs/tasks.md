# Automation Tasks

Automation Tasks coordinate one or more registered instruments on a shared
trigger clock. A Task stores its configuration, lifecycle state, synchronized
samples, and the readings produced by every configured instrument.

## Task types and trigger clock

- **Single** performs one trigger.
- **Continuous** runs until stopped or until a finite supply program finishes.
- **Loop** performs the configured number of triggers.

The interval uses absolute monotonic deadlines, so instrument communication
time does not accumulate as timing drift. Acquisition time is stored separately
for each sample. Closing or reloading the browser does not stop the runner.

## Power-supply programs

Power-supply assignments support:

- **Fixed** with one set voltage.
- **Sweep** from Start Voltage to Stop Voltage using Voltage Step.
- **Sweep Back** to append the return path to the starting voltage.
- **Cycle** for a configured number of complete up/down cycles.

The Mock RND Lab 320-3005P supports configurable output tolerance with `µV`,
`mV`, or `V` input units and optional voltage readback after each trigger. Its
readback follows the physical instrument's two-decimal display precision.

## Mock DMM resolution

Mock DMM DC voltage tasks can select:

| Mode | Full-scale ranges | Resolution by range |
| --- | --- | --- |
| 2,000 count (3½ digit) | 0.2, 2, 20, 200, 1000 V | 100 µV, 1 mV, 10 mV, 100 mV, 1 V |
| 4,000 count (3¾ digit) | 0.4, 4, 40, 400, 1000 V | 100 µV, 1 mV, 10 mV, 100 mV, 1 V |
| 20,000 count (4½ digit) | 0.2, 2, 20, 200, 1000 V | 10 µV, 100 µV, 1 mV, 10 mV, 100 mV |
| 50,000 count (4¾ digit) | 0.5, 5, 50, 500 V | 10 µV, 100 µV, 1 mV, 10 mV |
| 60,000 count (4¾ digit) | 0.6, 6, 60, 600, 1000 V | 10 µV, 100 µV, 1 mV, 10 mV, 100 mV |
| 200,000 count (5½ digit) | 0.2, 2, 20, 200, 1000 V | 1 µV, 10 µV, 100 µV, 1 mV, 10 mV |
| 1,200,000 count (6½ digit) | 0.12, 1.2, 12, 120, 1000 V | 0.1 µV, 1 µV, 10 µV, 100 µV, 1 mV |

The selected mode controls quantization and the decimal places used by the Task
table, DMM panel, and CSV export. These are simulation profiles; physical
drivers expose their own model-specific capabilities.

## Charts and temperature

Every result column is assigned to the primary chart axis by default. Raspberry
Pi CPU temperature can instead use the secondary axis, allowing temperature and
voltage to remain visually centered at different scales. The Raspberry Pi
driver reads `/sys/class/thermal/thermal_zone0/temp` and reports degrees Celsius
to two decimal places.

## Restart recovery

At application startup, OIL schedules persisted Pending and Running tasks that
do not have a stop request. A resumed Running task:

1. preserves completed samples and readings;
2. marks a sample interrupted while Acquiring as failed;
3. continues with the next sample index;
4. skips the original start delay; and
5. reconnects and prepares its instruments before acquisition continues.

This recovery targets the supplied single-process service. Multiple application
workers still require centralized task claiming and inter-process instrument
locking.

## CSV export

Task CSV files contain one row per trigger and a column for every configured
instrument output. They use a UTF-8 BOM, semicolon delimiter, decimal comma,
CRLF line endings, and an ISO 8601 timestamp with milliseconds. Export currently
uses the `Europe/Berlin` zone explicitly:

```text
ID;Time;Acquisition Time (s);Mock RND — Set voltage (V);Mock RND — Read voltage (V);Mock DMM (V);RPi CPU Temperature (°C)
125;2026-08-11T14:32:05.174+02:00;0,174;5,00;5,00;4,9999;48,75
```
