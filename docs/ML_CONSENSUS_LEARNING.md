# Machine Learning from Consensus Scoring Data

**Date:** 2026-03-06
**Status:** Design / Roadmap

## Overview

This document describes the strategy for using multi-rater consensus sleep scoring data to train machine learning models that improve automated scoring. The system has a unique advantage: labeled data comes from expert human consensus, not a single scorer or algorithmic ground truth.

## Why This Matters

Actigraphy sleep scoring is subjective at boundary decisions (onset/offset placement). Algorithms like Sadeh provide a starting point, but human scorers override based on visual pattern recognition that has never been formally captured. By collecting consensus labels alongside rich feature data, we can:

1. Learn what drives human scoring decisions
2. Predict when automation will fail and flag for human review
3. Improve auto-scoring accuracy by incorporating learned patterns
4. Reduce inter-rater variability through calibration

## Data Assets

### What We Collect Per Night

**Time-series data (per epoch, typically 1440 epochs/night):**
- Activity counts: axis_x, axis_y, axis_z, vector_magnitude
- Algorithm sleep/wake binary scores (Sadeh or Cole-Kripke)
- Choi nonwear detection mask
- Sensor nonwear mask (from device CSV)
- Timestamps (Unix, 60-second resolution)

**Diary data (per night):**
- Reported sleep onset time
- Reported wake time
- Nap count
- Nonwear periods (up to 3 start/end pairs)

**Computed features (per night, from complexity.py):**
- Transition density (sleep/wake flips per hour during 21:00-09:00)
- Diary-algorithm onset gap (minutes between diary time and nearest algorithm boundary)
- Diary-algorithm offset gap
- Confirmed nonwear epochs (Choi + sensor overlap in night window)
- Choi-only nonwear epochs
- Sleep run count (distinct runs of >= 3 consecutive sleep epochs)
- Sleep period duration (hours, first onset to last offset)
- Nap count from diary
- Boundary clarity score (activity contrast at algorithm onset/offset)
- Onset candidates near diary (sleep run starts within 30 min of diary onset)
- Offset candidates near diary
- Candidate ambiguity penalty
- Night activity spike count

**Labels (from consensus system):**
- Per-scorer marker placements (onset/offset timestamps, per user)
- Consensus candidate markers (voted/selected as best)
- Consensus hash (identifies unique marker configurations)
- Vote counts per candidate
- is_no_sleep flag
- Algorithm used
- Scorer notes

### Derived Labels (to compute at export time)

- Consensus onset timestamp
- Consensus offset timestamp
- Inter-rater onset SD (standard deviation of onset across scorers, in epochs)
- Inter-rater offset SD
- Number of distinct onset placements
- Number of distinct offset placements
- Consensus difficulty (did all scorers agree immediately, or were there multiple candidates?)
- Onset delta from algorithm (consensus onset - algorithm onset, in epochs)
- Offset delta from algorithm

## ML Problem Formulations

### Problem A: Predict Consensus Markers from Features

**Goal:** Given a night's data, predict where human consensus would place onset/offset.

**Formulation options (in order of increasing complexity):**

1. **Regression on summary features** — predict onset/offset as epoch offset from algorithm boundary. Input: complexity features + diary times. Output: signed epoch delta. Model: XGBoost/LightGBM.

2. **Candidate selection** — predict which of the algorithm's candidate boundaries scorers will choose. Input: per-candidate features (activity spike magnitude, proximity to diary, nonwear context). Output: probability per candidate. Model: logistic regression or gradient boosted trees. This mirrors how scorers actually work — they pick from plausible options.

3. **Sequence model** — 1D CNN or LSTM on epoch-level time series, predict per-epoch probability of onset/offset. Auxiliary summary features concatenated before final layers. Requires more data but captures local temporal patterns.

**Recommended starting point:** Option 1 (regression on summary features) as baseline, then Option 2 (candidate selection) which better matches the scoring task.

### Problem B: Predict Scoring Difficulty / Disagreement

**Goal:** Predict how much scorers will disagree, replacing hand-tuned complexity penalties with learned weights.

**Input:** Same features as Problem A.
**Output:** Inter-rater onset SD + offset SD, or binary easy/hard classification, or continuous difficulty score (0-100).

**Direct application:** Replace the hand-tuned penalty weights in `complexity.py` (currently: transition density max -25, diary gap max -15, nonwear max -15, etc.) with weights learned from actual consensus disagreement data.

**Model:** XGBoost on summary features. Interpret with SHAP values to understand which features truly predict difficulty vs. which current penalties are miscalibrated.

### Problem C: Scorer Calibration

**Goal:** Detect and correct individual scorer biases.

**Input:** Per-scorer marker placements across all their scored nights.
**Output:** Per-scorer bias estimate (e.g., "scorer A places onset 2.3 min earlier than consensus on average").

**Application:** Weight votes in consensus, flag systematic drift, provide feedback to scorers.

**Model:** Mixed-effects regression with scorer as random effect, night features as fixed effects.

## Implementation Roadmap

### Phase 1: Training Data Export (immediate)

Build an API endpoint and/or CLI command that exports training data:

```
POST /api/v1/ml/export-training-data
```

Output format: Parquet or CSV with one row per scored night containing:
- file_id, participant_id, analysis_date
- All complexity features (from compute_pre_complexity)
- Diary times
- Consensus onset/offset timestamps
- Per-scorer onset/offset (as JSON array)
- Inter-rater SDs
- Algorithm onset/offset
- Activity summary statistics (mean, SD, zero-epoch proportion for night window)

**Location:** `sleep_scoring_web/api/ml.py` (new router)
**Service:** `sleep_scoring_web/services/ml_export.py` (new)

### Phase 2: Learned Complexity Weights (highest immediate value)

Replace hand-tuned penalties in `complexity.py` with learned weights:

1. Export training data for all consensus-scored nights
2. Train XGBoost to predict inter-rater disagreement (onset SD + offset SD) from features
3. Extract feature importances / SHAP values
4. Replace `_linear_penalty()` weights with learned coefficients
5. Validate with leave-one-participant-out CV

**Key insight:** The current penalty system assumes linear relationships with arbitrary thresholds (e.g., transition density penalty is 0 at <= 2/hr, max at >= 6/hr). The learned model may reveal nonlinear relationships or different thresholds.

**Deliverable:** Updated `complexity.py` with `compute_pre_complexity_ml()` that uses a trained model, falling back to hand-tuned version when no model is available.

### Phase 3: Auto-Score Improvement

Feed ML predictions back into the auto-scorer as a weighted input:

```python
# In place_sleep_markers():
algo_onset = algorithm_detected_onset
ml_onset = ml_model.predict_onset(features)
ml_confidence = ml_model.predict_confidence(features)  # 0-100, calibrated

# Weighted blend
w = ml_confidence / 100.0
final_onset = (1 - w) * algo_onset + w * ml_onset
```

**Critical requirement:** The ML model must be **well-calibrated** — when it says 80% confident, it must be right ~80% of the time. Use Platt scaling or isotonic regression on held-out predictions.

**Validation:** Compare auto-score accuracy (MAE in minutes vs consensus) before and after ML integration, using leave-one-participant-out CV.

### Phase 4: Active Learning

Use the disagreement model to prioritize which nights to send to consensus scoring:

1. Run disagreement prediction on all un-scored nights
2. Rank by predicted difficulty (highest first)
3. Present to scorers in difficulty order
4. Each new scored night improves the model

This maximizes label value per unit of human effort.

### Phase 5: Scorer Quality Control

- Detect when a scorer's placements are statistical outliers relative to model predictions
- Flag nights where one scorer deviates significantly from others
- Track scorer bias over time (drift detection)
- Provide feedback dashboards

## Evaluation Protocol

### Cross-Validation Strategy

**Always use leave-one-participant-out CV** (not random splits). Nights from the same participant are correlated (similar sleep patterns, same device). Random splits leak information and overestimate performance.

```python
from sklearn.model_selection import LeaveOneGroupOut
logo = LeaveOneGroupOut()
for train_idx, test_idx in logo.split(X, y, groups=participant_ids):
    model.fit(X[train_idx], y[train_idx])
    predictions = model.predict(X[test_idx])
```

For hyperparameter tuning, use **nested CV** (inner loop for hyperparams, outer loop for unbiased evaluation).

### Metrics

**For onset/offset prediction:**
- MAE (Mean Absolute Error) in minutes — primary metric
- Median AE — robust to outliers
- Percentage within 5 min of consensus
- Percentage within 10 min of consensus

**For disagreement prediction:**
- Spearman correlation with actual inter-rater SD
- Calibration curve (predicted difficulty vs actual difficulty)
- Binary AUC for easy/hard classification

**For scorer calibration:**
- ICC (Intraclass Correlation Coefficient) before/after calibration
- Bias reduction in minutes

### Minimum Sample Sizes

Rule of thumb for gradient boosted trees on tabular data:
- ~10-20 samples per feature for reasonable performance
- With ~20 features, need ~200-400 scored nights minimum
- More is always better; diminishing returns after ~1000 nights

## Interpretability & Research Output

### SHAP Analysis

After training the disagreement model, compute SHAP values:

```python
import shap
explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test)
shap.summary_plot(shap_values, X_test)
```

This reveals:
- Which features actually predict when humans disagree with the algorithm
- Whether current penalty weights are miscalibrated
- Nonlinear relationships (e.g., maybe moderate transition density is hardest, not high)
- Interaction effects (e.g., high transitions + low boundary clarity = much harder than either alone)

### Publishable Research Questions

1. **"What drives expert sleep scoring decisions beyond algorithmic boundaries?"** — SHAP analysis of disagreement model on multi-rater consensus data. Novel contribution: most validation studies compare algorithm to PSG, not to multi-rater visual scoring.

2. **"Can scoring difficulty be predicted from actigraphy features?"** — Validate learned complexity scores against actual inter-rater variability.

3. **"Active learning for actigraphy sleep scoring"** — Show that prioritizing difficult nights for consensus scoring improves model accuracy faster than random selection.

4. **"Scorer calibration in actigraphy: detecting and correcting systematic bias"** — Mixed-effects models of individual scorer tendencies.

## Technical Notes

### Model Storage

Trained models should be stored as:
- Serialized model file (joblib for sklearn/XGBoost)
- Feature schema (JSON listing expected features, types, ranges)
- Training metadata (date, CV score, sample size, participant count)
- Calibration parameters (Platt scaling coefficients)

Location: `sleep_scoring_web/ml/models/` directory, loaded at startup.

### Feature Schema Versioning

As complexity features evolve, the ML model's expected input may break. Use a version string in the feature schema:

```json
{
  "version": "v1",
  "features": ["transition_density", "diary_onset_gap_min", ...],
  "trained_on": "2026-03-15",
  "cv_mae_minutes": 4.2,
  "n_nights": 450,
  "n_participants": 38
}
```

The prediction endpoint should check version compatibility and fall back to hand-tuned scoring if mismatched.

### Privacy

Training data export must respect any study-level privacy settings. Participant IDs in exported data should be pseudonymized. Raw activity time series may be too identifying — consider exporting only summary features for sharing.

## Dependencies

Core ML stack (add to pyproject.toml when implementing):
- scikit-learn >= 1.4
- xgboost >= 2.0
- shap >= 0.44
- pandas >= 2.1
- pyarrow (for parquet export)

These are training-time dependencies only. Inference uses the serialized model with minimal dependencies.

## Relationship to Existing Code

| Existing Module | ML Integration Point |
|---|---|
| `services/complexity.py` | Replace `_linear_penalty` weights with learned weights (Phase 2) |
| `services/marker_placement.py` | Add ML-weighted onset/offset adjustment (Phase 3) |
| `api/markers.py` (`auto-score`) | Pass ML prediction as optional input |
| `db/models.py` (`ConsensusCandidate`, `ConsensusVote`) | Source of training labels |
| `api/markers.py` (`auto-nonwear`) | Could learn nonwear patterns similarly |

## Appendix: Current Complexity Feature Definitions

See `services/complexity.py` for implementation. Summary of current hand-tuned penalties:

| Feature | Range | Max Penalty | Threshold |
|---|---|---|---|
| Transition density | per hour | -25 | Linear 2-6/hr |
| Diary-algorithm gap | per boundary | -7.5 each (-15 total) | Linear 10-60 min |
| Confirmed nonwear (night) | epochs | -15 | 0-30 linear, >30 = max |
| Sleep run count | count | -5 | <=10: 0, <=15: -2, <=20: -3, >20: -5 |
| Sleep period duration | hours | -10 | 6-9: 0, 4-6/9-11: -5, else: -10 |
| Nap count | 0-3 | -5 | 0: 0, 1: -2, 2: -3, 3: -5 |
| Boundary clarity | 0-1 scale | -10 | Linear from avg clarity |
| Candidate ambiguity | composite | -15 | Based on candidate counts near diary |
| Marker-algorithm alignment | epochs (post) | -5 | <=5: +5, >30: -5 |
| No diary | boolean | score = -1 | Infinite complexity |
| Nonwear > 50% of sleep | boolean | score = -1 | With no activity spikes |
