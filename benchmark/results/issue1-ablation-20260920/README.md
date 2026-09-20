# Assignment 1 paired ablation evidence

Command: `python benchmark/ablate.py --per-mutation 1 --provider apex-deepseek --model deepseek-v4-flash --thinking medium --max-steps 10 --max-tokens 90000 --max-output-tokens 4096`

The paired neutral task IDs were `case-0001` through `case-0004`, covering none, metadata corruption, hallucinated reference, and reference swap. Both modes used the same model and budgets. Raw run directories (including trajectories and tool artifacts) remain under the ignored `benchmark/runs/issue1-ablation-20260920-v2/`; this tracked package contains sanitized receipts, predictions, configuration, and aggregate metrics. All eight receipts report `completed`, `verified: true`, and zero trajectory protocol errors.

The full mode scored 1.0 reference / 1.0 support / 1.0 joint exact on the four cases. The no-paper-search mode scored 1.0 / 0.5 / 0.5. This is a four-task paired course evaluation, not a general performance estimate.
