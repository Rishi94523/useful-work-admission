# Grant Brief

## Project

PoUW CAPTCHA: Verifiable Useful-Work Rate Limiting for AI-Era Web Abuse

## One-Line Summary

PoUW CAPTCHA turns automated web abuse pressure into verified browser-side ML
work that rate-limits bots while producing useful AI labeling signals.

## Why It Matters

AI agents and solver farms increasingly bypass traditional CAPTCHAs. Blocking
all bots is unrealistic. This project reframes the problem: make automated
traffic pay a measurable compute toll, verify that work cheaply, and recover
part of the imposed cost as useful model/data value.

## Technical Approach

- Assign browser clients ML inference shards — dense and convolutional layers
  from any model in the plug-and-play store.
- Verify submitted outputs with secret projection checks (generic over affine
  layer operators) rather than routine full recomputation.
- Increase workload adaptively for suspicious clients.
- Use selective human verification to produce golden labels.
- Report useful work, failed proof pressure, and estimated captured value.

## Funding Fit

- Cybersecurity and anti-abuse infrastructure.
- Trustworthy AI and human-in-the-loop data systems.
- Privacy-preserving browser computation.
- Sustainable alternatives to wasteful proof-of-work.

## Next Milestones

1. Deploy hosted backend and Cloudflare edge gateway.
2. Run multi-device browser latency evaluation.
3. Expand beyond MNIST to production-relevant approved datasets.
4. Conduct adversarial automation experiments.
5. Submit workshop/conference paper and provisional patent filing.
