"""Regression test for hmm_postprocessing per-composition accuracy.

CONTEXT
-------
The Phase 2 findings document §4.3 claimed the per-composition accuracy line
(hmm_postprocessing.py, originally at :247) was a bug because
`hmm_preds.index((hp, _))` would collapse long runs of identical predictions
to a single first-index lookup.

Verification against the code invariant shows this is NOT a bug.
`postprocess_predictions` returns `[(hmm_path[t], predictions[t][1]) for t in
range(T)]` — so `hmm_preds[t][1] == predictions[t][1]` at every t. The tuple
`(hp, _)` passed to `.index()` therefore includes the true label at position t,
and any earlier matching index j must satisfy `predictions[j][1] ==
predictions[t][1]`. The subsequent `preds[j][1]` lookup returns the same true
label that would have been read at position t. The convoluted O(T²) code is
semantically equivalent to the clean O(T) zip-based form.

1000 random trials confirm equality (see /tmp/verify_hmm.py in project notes).

WHAT CHANGED
------------
The line was rewritten from O(T²) `.index()`-based to O(T) zip-based for
readability and performance parity with the surrounding loop at L230. This is
a cleanup, NOT a bug fix. Results on existing evaluation outputs are unchanged.

THIS TEST
---------
Verifies the new implementation produces correct per-composition accuracy on a
synthetic 10-composition dataset and that the per-composition values are
consistent with the global `hmm_accuracy` aggregate.
"""

from __future__ import annotations

import json
import os
import tempfile

from hmm_postprocessing import evaluate_with_hmm


def test_10_composition_accuracy_consistency() -> None:
    compositions = []
    for cid in range(1000, 1010):
        length = 20 + (cid % 5) * 4
        preds = [[(i % 2), (i % 3)] for i in range(length)]
        softmax = [[0.34 if j == (i % 2) else 0.33 for j in range(24)] for i in range(length)]
        compositions.append({
            'composition_id': cid,
            'predictions': preds,
            'softmax': softmax,
        })

    data = {'compositions': compositions}
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as fh:
        json.dump(data, fh)
        tmp = fh.name

    try:
        out = evaluate_with_hmm(tmp, self_transition=0.85, tau=2.0)
    finally:
        os.unlink(tmp)

    assert len(out['per_composition']) == 10

    for row in out['per_composition']:
        assert 0.0 <= row['accuracy'] <= 1.0
        assert isinstance(row['accuracy'], float)

    weighted_sum = sum(row['accuracy'] * row['n_predictions'] for row in out['per_composition'])
    total_preds = sum(row['n_predictions'] for row in out['per_composition'])
    reconstructed = weighted_sum / total_preds
    assert abs(reconstructed - out['hmm_accuracy']) < 1e-9, (
        f'aggregate hmm_accuracy {out["hmm_accuracy"]:.6f} inconsistent with '
        f'sum(per_comp.accuracy * n)/sum(n) = {reconstructed:.6f}'
    )

    print(f'  10 compositions evaluated, hmm_accuracy={out["hmm_accuracy"]:.4f}')
    print(f'  per-composition ↔ aggregate invariant holds')


def test_known_answer_single_composition() -> None:
    """Handcrafted single composition with known-answer accuracy."""
    compositions = [{
        'composition_id': 9999,
        'predictions': [[i % 2, 0] for i in range(10)],
        'softmax': [[1.0 if j == 0 else 0.0 for j in range(24)] for _ in range(10)],
    }]
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as fh:
        json.dump({'compositions': compositions}, fh)
        tmp = fh.name

    try:
        out = evaluate_with_hmm(tmp, self_transition=0.99, tau=2.0)
    finally:
        os.unlink(tmp)

    row = out['per_composition'][0]
    assert row['accuracy'] == 1.0, (
        f'HMM forced to class 0 via softmax; all true labels 0; expected 1.0, got {row["accuracy"]}'
    )
    print(f'  known-answer composition: accuracy={row["accuracy"]}')


if __name__ == '__main__':
    print('[1/2] 10-composition accuracy consistency ...')
    test_10_composition_accuracy_consistency()
    print('[2/2] known-answer single composition ...')
    test_known_answer_single_composition()
    print('\nHMM accuracy regression tests passed.')
