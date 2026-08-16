# DMM Panels

The Panels page lists registered instruments that publish measurement
capabilities. Opening a free instrument presents a responsive local-style DMM
front panel; opening an instrument owned by an active Task presents the same
values in read-only mode.

## Local operation

A free panel begins continuous measurement automatically. The Trigger button
performs a reading, Continuous starts or stops the one-second local trigger,
and the display reports `Auto Trigger` or `Manual Trigger`. The activity light
is invisible while idle and flashes for each completed trigger.

Function buttons are ordered as:

```text
DCV DCI ACV ACI 2W 4W Freq Cap Dio Cont Temp
```

Only capabilities implemented by the selected driver are enabled. Unsupported
front-panel functions remain visible but disabled.

Auto Range selects the smallest driver-published range that contains the
current absolute reading. The display shows both the mode and effective range,
for example `AUTO 20 V`. Range + and Range − select adjacent fixed ranges.
On a free Mock DMM, the Resolution button cycles through 3½, 3¾, 4½, 4¾, 5½,
and 6½-digit simulation profiles and updates ranges, quantization, and display
precision together. The corresponding modes span 2,000 through 1,200,000
counts; the original 50,000-count 4¾ profile is retained for saved-Task
compatibility. The control remains disabled for drivers that do not yet publish
an equivalent selectable resolution mode. While a Task owns the Mock DMM, the
same button may change local panel formatting, but it does not alter the Task
configuration, driver quantization, or stored readings.

## Display

The upper display row shows the selected function, trigger status, and sample
counter. The main reading always includes a sign. Readings with more than three
fractional digits include a half-character grouping gap, for example:

```text
+0.634 450
```

The lower display row shows the active range, Task ownership when applicable,
and the function-specific unit such as `VDC`, `VAC`, `ADC`, or `AAC`. MIN, MAX,
and AVG are calculated from acquired readings.

## Graph

The graph displays the latest 120 readings. Voltage scale bounds are calculated
automatically from display resolution and recent variation, using clean 1-2-5
division steps with ten divisions above and below the center. Zoom in and Zoom
out adjust that calculated span. Numeric scale labels reserve only their
measured text width plus a small gap, maximizing the trace area. The display and
graph area is capped at 320 pixels high; the reading section is 480 pixels wide
on desktop and the graph fills the remaining width.

## Active Task ownership

When a Task owns the instrument, measurement and configuration controls are
disabled. The panel polls stored Task readings instead of opening a competing
hardware connection. It displays the real Task sample index, task-wide
statistics for the selected reading, recent values, count-mode precision, and
the driver ranges supplied by the Task payload.
