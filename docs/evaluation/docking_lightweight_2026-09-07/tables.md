| Protocol | Ligands × poses | Molecular kernel ms | Total client ms | Kernel fraction | Warm verifier ms | Client→server KiB |
|---|---:|---:|---:|---:|---:|---:|
| B | 1 × 4096 | 14.9 | 18.1 | 89.3% | 1.68 | 42.8 |
| B | 4 × 4096 | 59.5 | 62.7 | 95.4% | 2.57 | 112.1 |
| B | 16 × 4096 | 251.8 | 262.9 | 95.8% | 6.94 | 380.0 |
| C | 1 × 4096 | 14.3 | 22.0 | 64.4% | 2.37 | 265.6 |
| C | 4 × 4096 | 56.1 | 70.7 | 79.3% | 3.55 | 413.1 |
| C | 16 × 4096 | 261.7 | 300.5 | 85.3% | 11.05 | 864.4 |
| E | 1 × 4096 | 14.2 | 27.4 | 51.8% | 5.09 | 646.2 |
| E | 4 × 4096 | 53.5 | 105.7 | 51.0% | 19.81 | 2541.7 |
| E | 16 × 4096 | 253.1 | 488.4 | 51.8% | 74.05 | 11489.7 |
| B | 1 × 16384 | 57.2 | 61.5 | 93.5% | 1.75 | 112.3 |
| B | 4 × 16384 | 221.7 | 244.0 | 91.2% | 3.24 | 373.5 |
| B | 16 × 16384 | 982.0 | 1044.7 | 94.1% | 8.97 | 1411.9 |
| C | 1 × 16384 | 56.0 | 70.3 | 78.1% | 2.32 | 372.4 |
| C | 4 × 16384 | 212.5 | 244.2 | 87.6% | 4.58 | 685.8 |
| C | 16 × 16384 | 970.0 | 1101.3 | 88.4% | 11.84 | 1898.8 |

Columns are independently computed medians of three runs; the kernel fraction is the median paired ratio, so ratios of the other medians can differ. Verifier timings exclude JSON parsing, lease/challenge/credit transactions and network.
