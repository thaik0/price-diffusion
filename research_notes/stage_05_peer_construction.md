# Stage 5: Peer Construction

## Why peers are central

The project asks how information moves among economically related semiconductor
companies. That question cannot be answered until “related” is defined without
using the price outcome that later stages will study. Peer construction is thus
a research-design input, not an optimization problem. Each output row records a
directed relationship from an initiating security to a comparison security on a
specific date.

Stage 5 creates comparison portfolios only. It does not identify events,
calculate returns, estimate expected returns, measure diffusion, or select peers
from observed stock-price behavior.

## Universe versus peers

The universe answers whether a security may participate in the research on a
date. A peer definition answers which of those eligible securities are relevant
comparators for a particular eligible initiator. Eligibility therefore precedes
peer construction. Both endpoints of every edge must be eligible on the edge
date, and a change in historical membership changes only that date's edges.

A security can be eligible yet have no economic peers if no other eligible firm
shares its reviewed peer group. The absence of a row is preferable to inventing
an economically weak comparator. Under the broad definition, every other
eligible semiconductor is included, so a source needs at least one other
eligible security to have a portfolio.

## Metadata design

`metadata/peer_classification.csv` separates economic grouping from the Stage 4
semiconductor-inclusion metadata. Production use requires one human-reviewed
row per security; the bundled rows are documented seeds for that review:

- `subsector` is a controlled high-level category.
- `peer_group` is a narrower economic comparison group.
- `classification_notes` records the economic rationale and judgment calls.

The baseline `economic_subsector_peers` definition matches firms on
`peer_group`. The name emphasizes that these groups refine the controlled
economic subsectors; it does not mean that all firms sharing a broad subsector
must be peers. Equal weights prevent an untested size, liquidity, or valuation
choice from entering the baseline.

## Definitions and extension boundary

The primary definition uses reviewed economic groups. The secondary
`broad_semiconductor_peers` portfolio includes every other eligible
semiconductor and tests whether later findings are broad sector effects rather
than effects specific to close economic relationships.

The module exposes a definition-to-candidate-builder boundary. A future
`trailing_return_similarity_peers` implementation can use the same directed
output contract, but requesting it now raises `NotImplementedError`. It belongs
in robustness analysis, where its lookback window, minimum observations, lag,
and selection count can be specified and audited.

## Why return similarity is delayed

Selecting peers because their historical returns moved together risks circular
reasoning. The later research outcome concerns relative price movement and
information diffusion; choosing the comparison set from that same behavior can
mechanically strengthen apparent relationships. Return similarity can also
capture common factor exposure, market beta, transient regimes, or shared
liquidity rather than product-market connection. Keeping it out of the baseline
preserves a clean separation between economic hypothesis formation and price
testing.

## Biases and limitations

- Human classifications are subjective and require documented review.
- A single label compresses conglomerates and firms with several material
  product lines.
- Business models, end markets, and competitive relationships change over time;
  the seed file is not a point-in-time historical classification database.
- Narrow groups can yield small or empty peer portfolios, while broad groups
  deliberately mix unlike businesses.
- Equal weighting can overrepresent small firms relative to their economic
  importance, but avoids introducing another estimated parameter at this stage.
- Directed storage supports future initiator-specific rules, although the two
  current candidate rules often create reciprocal edges.
- Correct dated edges still depend on survivorship-free upstream security,
  classification, and universe data.

These limitations should be handled through classification versioning,
historical effective dates, sensitivity definitions, and later robustness
analysis—not by fitting baseline peers to realized returns.
