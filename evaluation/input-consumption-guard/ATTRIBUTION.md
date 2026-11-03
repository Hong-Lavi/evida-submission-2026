# Design reference and code attribution

The input-revision and dependency-recording concept is informed by the author-maintained [Salsa algorithm reference](https://salsa-rs.github.io/salsa/reference/algorithm.html). Salsa records tracked dependencies, checks changed inputs across revisions, and can retain a downstream result when recomputation produces the same value. EVIDA adapts the distinction between changed inputs and retained outputs to explicit declared consumption and reassessment records.

This package contains an independent EVIDA Python implementation and its synthetic publication replay. No Salsa source code or runtime is bundled, and the replay is not a test of Salsa's implementation. EVIDA's model-authored usage declarations also do not expose a language model's internal dependencies.

The native EVIDA dependency files, selected Runner methods, reference driver and saved observations are individually attributed by original source hashes in `source-map.json`. Portability changes are disclosed there and in `PORTABILITY.md`. The only external Python dependency needed to run the software replay is `jsonschema`, installed separately under its own license.
