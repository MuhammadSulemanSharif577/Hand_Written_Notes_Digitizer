# OCR evaluation

This package is independent from production OCR inference.

## Modules

- `metrics.py`: confusion matrices, accuracy, macro/micro/weighted precision,
  recall and F1, character error rate (CER), word error rate (WER), and exact
  line accuracy.
- `plots.py`: confusion heatmaps, PRF comparison charts, and training curves.
- `reporting.py`: JSON and CSV serialization.
- `cnn_evaluator.py`: balanced EMNIST ByClass CNN evaluation.
- `sequence_evaluator.py`: labelled handwriting-line TrOCR evaluation.

## Run

From the backend project root:

```powershell
.\.venv311\Scripts\python.exe scripts\evaluate_ocr_models.py --cnn-samples 10000
```

Reports are written to `reports/model_evaluation/`. Use `--skip-cnn` or
`--skip-trocr` to refresh only one model. Partial runs merge into `summary.json`.

## Interpretation

CNN accuracy/PRF values measure isolated EMNIST character classification.
TrOCR CER/WER values measure raw line recognition before CNN fusion and visual
calibration. Writer-calibration results are based on ten labelled lines and
must not be presented as general handwriting accuracy.

## Writer fine-tuning v2/v3

Prepare the expanded writer dataset from original full-resolution uploads:

```powershell
.\.venv311\Scripts\python.exe scripts\prepare_writer_finetune_dataset.py
```

Train a guarded candidate from the active writer checkpoint:

```powershell
.\.venv311\Scripts\python.exe scripts\fine_tune_writer_dataset.py `
  --base-model models\trocr-writer-calibrated-v2 `
  --output-model models\trocr-writer-calibrated-v3 `
  --epochs 10 --learning-rate 1e-5 --check-every 2
```

Each candidate writes `comparison.json`, `promotion.json`, a confusion heatmap,
macro/micro/weighted precision-recall-F1 chart, character CSV, and training
history. Production selects a candidate only when `promotion.json` confirms
that independent validation and target-domain safeguards passed.
