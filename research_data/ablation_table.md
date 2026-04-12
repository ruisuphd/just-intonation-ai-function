
## Ablation Study: Key Detection on ATEPP-319 Balanced Test Set

| Row | Model | Aug. | Weight | MIREX (95% CI) | Accuracy | Major | Minor | n |
|-----|-------|------|--------|----------------|----------|-------|-------|---|
| B_KK | Krumhansl Kessler | -- | -- | 0.679 (0.585--0.776) | 0.530 | -- | -- | 146,045 |
| B_TE | Temperley | -- | -- | 0.778 (0.677--0.873) | 0.710 | -- | -- | 146,045 |
| B_AS | Albrecht Shanahan | -- | -- | 0.776 (0.674--0.871) | 0.705 | -- | -- | 146,045 |
| B_EN | Ensemble | -- | -- | 0.788 (0.688--0.884) | 0.724 | -- | -- | 146,045 |
| BA_KK | Krumhansl Kessler (aligned) | -- | -- | 0.602 (0.461--0.754) | 0.501 | -- | -- | 230,656 |
| BA_TE | Temperley (aligned) | -- | -- | 0.630 (0.487--0.792) | 0.546 | -- | -- | 230,656 |
| BA_AS | Albrecht Shanahan (aligned) | -- | -- | 0.623 (0.481--0.789) | 0.543 | -- | -- | 230,656 |
| BA_BB | Bellman Budge (aligned) | -- | -- | 0.632 (0.489--0.792) | 0.546 | -- | -- | 230,656 |
| BA_AE | Aarden Essen (aligned) | -- | -- | 0.616 (0.477--0.771) | 0.517 | -- | -- | 230,656 |
| BA_EN | Ensemble (aligned) | -- | -- | 0.620 (0.476--0.785) | 0.537 | -- | -- | 230,656 |
| BA_E5 | Ensemble 5 (aligned) | -- | -- | 0.627 (0.481--0.794) | 0.550 | -- | -- | 230,656 |
| JKD_KK | JKD HMM Krumhansl Kessler (exponential10) | -- | HMM | 0.591 | 0.516 | -- | -- | 230,656 |
| JKD_TE | JKD HMM Temperley (exponential10) | -- | HMM | 0.668 | 0.592 | -- | -- | 230,656 |
| JKD_AS | JKD HMM Albrecht Shanahan (exponential10) | -- | HMM | 0.630 | 0.558 | -- | -- | 230,656 |
| JKD_BB | JKD HMM Bellman Budge (exponential10) | -- | HMM | 0.648 | 0.555 | -- | -- | 230,656 |
| JKD_AE | JKD HMM Aarden Essen (exponential10) | -- | HMM | 0.600 | 0.510 | -- | -- | 230,656 |
| E_GRU 24 | GRU 24-key balanced | ? | ? | 0.538 | 0.390 | -- | -- | 285,440 |
| E_Transf | Transformer+S-KEY PT | ? | ? | 0.523 | 0.373 | -- | -- | 285,440 |
| E_Transf | Transformer no-PT | ? | ? | 0.521 | 0.373 | -- | -- | 285,440 |
| A1 | ? (A1) | ? | ? | 0.531 (0.470--0.604) | 0.390 | 0.453 | 0.211 | 252,416 |
| A6 | BiGRU (A6) † | Yes | none | 0.575 (0.508--0.651) | 0.434 | 0.498 | 0.257 | 252,416 |
| A7 | GRU+PCP (A7) | Yes | none | 0.543 (0.475--0.619) | 0.408 | 0.450 | 0.277 | 252,416 |
| A8 | GRU (A8) | Yes | focal | 0.529 (0.469--0.604) | 0.387 | 0.444 | 0.212 | 252,416 |
| A9 | BiGRU+PCP (A9) † | Yes | focal | 0.599 (0.530--0.683) | 0.473 | 0.498 | 0.382 | 252,416 |
| PP_HMM | Best + HMM | -- | -- | 0.540 | 0.400 | -- | -- | 252,416 |
| PP_ENS | Neural+Classical (a=0.3) | -- | -- | 0.463 | 0.326 | -- | -- | 36,096 |

† Non-causal (bidirectional): offline upper bound only, not deployable in the real-time tuner.

Classical baseline profiles sourced from Nápoles (2019) "Key-Finding Based on an HMM and Key Profiles," DLfM 2019 (https://github.com/napulen/justkeydding). JKD HMM rows reproduce the algorithm in pure Python.