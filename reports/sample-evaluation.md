# APKSmith evaluation report

Scores measure **agreement with an independent hand-written reference**, not truth. A high score means the pipeline found what a human reader of the documentation found. It does not mean the app is fully reconstructed.

## Summary

- Cases: **2**
- Mean F1 across cases: **0.810**

## Per-metric means

| Metric | Mean |
| --- | --- |
| data_f1 | 0.643 |
| data_precision | 0.750 |
| data_recall | 0.600 |
| features_f1 | 0.833 |
| features_precision | 0.800 |
| features_recall | 0.875 |
| network_f1 | 0.857 |
| network_precision | 1.000 |
| network_recall | 0.750 |
| purpose_token_overlap | 1.000 |
| screens_f1 | 0.833 |
| screens_matched | 0.857 |
| screens_precision | 0.812 |
| screens_recall | 0.857 |

## Per case

| App | Mean F1 | Screens F1 | Features F1 | Purpose overlap |
| --- | --- | --- | --- | --- |
| F-Droid | 0.619 | 0.667 | 0.667 | 1.000 |
| Simple expense tracker | 1.000 | 1.000 | 1.000 | 1.000 |

## Notes

- **F-Droid** — Screens in reference but not found: Preferences, Installed apps
- **F-Droid** — Screens reported but not in reference: Install, Donate, Categories
- **F-Droid** — Features missed: Share apps via links, Build apps from source

## How to read these numbers

- `recall` low means the pipeline missed real behaviour.
- `precision` low means it invented things. That is worse.
- A low `purpose_token_overlap` with good screen F1 means the structure was found but the model could not summarise it.

A suite of 2 apps is a demonstration, not a benchmark. Treat the numbers as a regression signal: if a change makes them worse, that change is bad.
