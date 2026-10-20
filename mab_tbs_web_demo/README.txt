MAB + TBS BROWSER DEMOS
=======================

Open index.html in Chrome, Edge, Safari or Firefox.
No web server is needed to run locally. To share a link, upload index.html
inside this folder to GitHub Pages, Netlify Drop or another static web host.

SHORT PROTOCOL
MAB: 10 stable choices + 30 volatile choices (original 50+150).
TBS: 3 blocks x 8 choices (original 24 x 8).
The decision rules, probabilities, option tables, rewards and multiplier
logic come from FullExperiment_WORKING-20May2024.py.

EVENT TIMING / ERP LIMITS
-------------------------
No EEG is acquired; this cannot record any ERP. Browser software event markers
are logged when the evaluation and feedback screens are shown (after a paint
request) or at the commitment key response. The original Python parallel-port
trigger pulses are intentionally REMOVED. In the original script some pulses
were emitted before the corresponding draw and were followed by 200 ms waits.
Those delays are not reproduced. The short demos keep the 1 s fixation and
1 s feedback intervals but browser timing is not experimentally calibrated.
Browser timestamps are not reliable physical display-onset timestamps.
Markers correspond to original codes:
MAB: 3 evaluation display, 4 choice, 5 timeout, 6 feedback display.
TBS: 8 evaluation display, 9 choice, 10 timeout, 11 feedback display.

LOGS
----
Press Download Logs to export:
*_full.json: session metadata, all events, all trial snapshots, option records,
            block summaries (TBS), all task configs and random seed.
*_trials.csv: one detailed row per completed trial, including all available
              options with probabilities and values as JSON in a CSV column.
*_all_options.csv: one row PER AVAILABLE OPTION PER TRIAL, not only the choice.
*_events.csv: software marker events, trial IDs, ISO and monotonic timestamps.
*_blocks.csv (TBS): final-block target and multiplier results.

IMPORTANT
---------
MAB probabilities are hidden to the player but recorded in log files, including
all six arms on every trial. The log shows the current probabilities after any
volatility changes, as well as volatility checks. Outcomes are sampled only for
the chosen arm, reflecting the original protocol; counterfactual outcomes for
unselected arms are NOT generated or invented.
TBS logs capture all safe/risky options presented, with both probabilities and
amounts, regardless of which was selected. The final multiplier applies only
when the eighth trial wins, matching the original code.

Logs exist only in browser memory until downloaded. Browser demo is not validated
for research timing, hardware triggers, neurophysiology, or data acquisition.

MAB VISUAL / KEY MAPPING
------------------------
Options are grouped by their reward magnitudes, with keys ordered top to bottom:
Left row 1: Press 1, blue2, outcomes [+100,0,-100]
Left row 2: Press 2, blue3, outcomes [+100,0,-100]
Left row 3: Press 3, blue1, outcomes [+100,0,-100]
Right row 1: Press 7, red1, outcomes [+200,0,-200]
Right row 2: Press 8, red2, outcomes [+200,0,-200]
Right row 3: Press 9, red3, outcomes [+200,0,-200]
Neutral panels contain green (+), yellow (0) and red (-) open-topped containers.
One fixed-size ball represents one completed, recorded outcome of that option.
Timeout penalties do not add balls. Histories persist across stage changes and
reset with a new run. Full histories remain available by scrolling each container;
labels stay outside the scrolling area. Narrow screens stack the two groups.
Click anywhere in an option's panel, including its history, or press its number key.

TBS VISUALS
-----------
Equal-width rectangles share a bottom baseline. Total height is proportional to
possible points at a shared scale: the largest configured reward spans 160 pixels.
Each rectangle fills from the bottom by its actual win probability (SAFE green,
RISKY red), including empty/full fills for 0%/100%. Labels remain outside the
rectangles. Reward/probability tables, random sampling and scoring are unchanged.

VERIFICATION
------------
From the project root: node tests/test_demo_visuals.cjs
This runs the actual inline script with a minimal DOM and accelerated timers.
It checks grouping, shortcuts, outcome histories, full 200-ball packing, reset,
rectangle ratios/fills and complete short/full MAB/TBS runs with clicks, keyboard
choices and timeouts. It does not verify actual browser rendering or physical timing.
