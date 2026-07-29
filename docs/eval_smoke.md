# Eval smoke report

Variant: `backtest`  
Matches: **34**  
Seasons: 2024-25 .. 2024-25

## Model

| Metric | Value |
|--------|------:|
| RPS | 0.1631 |
| Log loss | 0.7734 |
| Brier | 0.4384 |

## Benchmarks

| Name | n | RPS | Log loss | Brier |
|------|--:|----:|---------:|------:|
| closing_devig | 34 | 0.1646 | 0.7750 | 0.4415 |
| opening_devig | 34 | 0.1599 | 0.7646 | 0.4341 |
| base_rates_insample | 34 | 0.2457 | 0.9718 | 0.5952 |
| home_always | 34 | 0.4706 | 18.2852 | 1.0588 |

## Bootstrap RPS (season resample)

- mean: **0.1631**
- 95% CI: [0.1631, 0.1631]
- seasons: 1, boots: 200

_Note: fewer than 2 seasons — CI is not meaningful yet (Day 13 full backtest will fix this)._

## Per season

 season  n      rps  logloss    brier
2024-25 34 0.163143 0.773384 0.438415

## Calibration (5pp bins, sample)

outcome  bin_lo  bin_hi  n  mean_predicted  realised_freq
   home    0.15    0.20  6        0.186555       0.000000
   home    0.30    0.35  4        0.335255       0.000000
   home    0.35    0.40  8        0.375338       0.500000
   home    0.40    0.45  2        0.417298       0.000000
   home    0.45    0.50  4        0.472481       1.000000
   home    0.55    0.60  4        0.571448       0.500000
   home    0.75    0.80  2        0.765003       1.000000
   home    0.80    0.85  2        0.818436       1.000000
   home    0.90    0.95  2        0.938629       1.000000
   draw    0.05    0.10  2        0.061327       0.000000
   draw    0.10    0.15  4        0.132048       0.000000
   draw    0.15    0.20  2        0.193624       0.000000
   draw    0.20    0.25 16        0.227163       0.250000
   draw    0.25    0.30 10        0.269460       0.000000
   away    0.00    0.05  2        0.000044       0.000000
   away    0.05    0.10  4        0.076232       0.000000
   away    0.15    0.20  2        0.182910       0.000000
   away    0.20    0.25  2        0.226700       1.000000
   away    0.25    0.30  4        0.277099       0.000000
   away    0.30    0.35  6        0.339242       0.333333

