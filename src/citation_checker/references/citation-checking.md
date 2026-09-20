# Citation-checking guide

## 1. Separate existence from support

A citation can fail in two independent ways:

- **bibliographic failure**: the cited work does not exist or its metadata is wrong;
- **support failure**: the work exists but does not support the manuscript claim.

Never treat a real paper as automatically valid evidence.

## 2. Reference-status definitions

### VERIFIED
RefChecker finds a convincing match and the core metadata (title/authors/year or
DOI) is consistent enough to identify the cited work.

### NOT_FOUND
RefChecker cannot find a credible corresponding work. Do not invent a recovery.

### METADATA_MISMATCH
A likely intended work exists, but one or more important fields differ materially
from the bibliography entry.

### UNVERIFIABLE
The available databases or extraction are insufficient to decide.

## 3. Support-status definitions

### SUPPORTED
The retrieved evidence directly supports the claim at the scope and strength used
in the manuscript.

### PARTIALLY_SUPPORTED
The cited work supports part of the claim, but the manuscript overstates a number,
scope, population, modality, causal relation, or generality.

### UNSUPPORTED
The retrieved source does not support the claim, contradicts it, or addresses a
materially different proposition.

### INSUFFICIENT_EVIDENCE
No credible source evidence is available, or only weak metadata/incomplete text
is available, so a support judgment would be speculative. Use this status when
the reference status is `NOT_FOUND` or `UNVERIFIABLE`; use `UNSUPPORTED` only
after retrieving a real source that does not support the claim.

## 4. Evidence discipline

Prefer full text over abstract when the claim depends on:

- exact numbers;
- subgroup/population details;
- experimental conditions;
- limitations or exceptions;
- causal conclusions;
- comparisons between methods;
- wording stronger than an abstract-level statement.

Title similarity and topical relevance are evidence leads, not proof of support.

## 5. Common citation errors

Check explicitly for:

- wrong title/author/year/DOI;
- correct paper but wrong quantitative value;
- correlation presented as causation;
- "may" or "suggests" rewritten as certainty;
- result on one dataset generalized to all settings;
- secondary source cited for a claim established by another primary source;
- abstract-level relevance without passage-level support.

## 6. Reporting style

Be concise and diagnostic. For every problem, identify exactly what is wrong and
what level of evidence was available. Do not recommend changing a citation unless
the retrieved evidence justifies the recommendation.
