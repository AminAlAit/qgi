# Next ECR rebuild — what's bundled

Tracks the diff between the qgi-recipe-fleet image last in production and `main` at rebuild time. Update on every rebuild; promote to a session-handoff line when the rebuild ships.

## Rebuild driver

GitHub Actions ECR push workflow (`.github/workflows/ecr-push.yml`) has been silently no-op'd since **2026-05-28** (3 consecutive runs with `stepCount: 0` — quota / runner-minutes exhausted). Auto-rebuild gap means anything merged since 2026-05-27 sits on `main` but is **not** in the image wave-3 is running. Use `rebuild-and-push-local.ps1` (this directory) when staging creds are available.

## Bundled (in chronological merge order)

| Merged | PR | Summary | Surface in image |
|--------|----|--------|------------------|
| 2026-05-28 02:19 | qgi-pipeline#41 | **#129 BLAS pin** — `OMP_NUM_THREADS=1` + 4 siblings env-set in Dockerfile | Dockerfile ENV block |
| 2026-05-28 02:53 | qgi-pipeline#42 | **#130 ecr-push auto-rebuild** — recipe-fleet added to workflow's matrix | workflow (no image bytes) |
| 2026-05-28 13:38 | qgi-pipeline#43 | **#107 FLEET-6/8** — real post-pass Lambda handler | Lambda (separate from image) |
| 2026-05-28 22:42 | qgi-pipeline#44 | **#966 FLEET-POST-PASS** — `_reject_stale_walks` filter on summaries `filed < floors.frozen_at_utc` | Lambda (separate from image) |
| 2026-05-29 00:07 | qgi-pipeline#45 | **#968 FLEET-VINTAGE-ROLLUP** — new Lambda for Admin Dashboard #151 | Lambda (separate from image) |
| 2026-05-29 00:38 | qgi-ml#125 | **#967 score_countries.py** — F-ML-1 per-country × per-recipe scoring script | `/app/scripts/score_countries.py` |
| 2026-05-29 00:51 | qgi-pipeline#46 | **#967 entrypoint hook** — `run_score_countries` called after `run_walk` | `/app/recipe_fleet_entrypoint.py` |
| 2026-05-29 00:51 | qgi-pipeline#46 | **Test-isolation rename** — `test_lambda_function.py` → unique basenames + `spec_from_file_location` | tests (no image bytes) |
| 2026-05-29 01:18 | qgi-ml#126 | **#967 follow-up A** — smoke tests for `build_today_X` year-fallback | tests (no image bytes) |
| 2026-05-29 01:18 | qgi-pipeline#47 | **#967 follow-up B** — `SCORE_COUNTRIES_TIMEOUT_SECONDS` env var | `/app/recipe_fleet_entrypoint.py` |
| 2026-05-29 01:18 | qgi-pipeline#47 | **#967 follow-up C** — content-aware `s3_sync_dir_up` | `/app/recipe_fleet_entrypoint.py` |

Plus whatever lands between this manifest and the rebuild — re-derive with:

```bash
git -C qgi-pipeline log a874691..HEAD --oneline -- batch/recipe-fleet/
git -C qgi-ml      log <last-baked-qgi-ml-sha>..HEAD --oneline -- scripts/ src/
```

## Excluded (by intent)

- **#969 Beta calibration emit** — lives in `qgi-ml/src/beta_calibration.py` + `scripts/run_f_ml_1_poc.py`. Will be bundled IF the rebuild is after qgi-ml#124 was merged; verify with `git -C qgi-ml log --oneline -- src/beta_calibration.py` before rebuild.
- **Wave-3 in-flight walks** — do NOT rebuild the image while wave-3 is still firing; jobs picking up the new image mid-fleet would mix two execution profiles. Wait for wave-3 to drain.

## Post-rebuild verification

1. **Image tag in ECR**:

   ```powershell
   aws ecr describe-images --repository-name qgi-recipe-fleet `
     --image-ids imageTag=latest --region eu-central-1 `
     --query 'imageDetails[0].{Digest:imageDigest,PushedAt:imagePushedAt,Size:imageSizeInBytes}'
   ```

   Expected: `PushedAt` within last 30 minutes; size ≈ 2 GB.

2. **LABEL traceability**: `docker inspect` (or `aws ecr batch-get-image | jq '...Labels'`) must show `qgi_ml_sha=<expected-sha>`. The rebuild script captures and prints this at the end.

3. **§2.5 canary diff harness**:

   ```bash
   # Trigger 1-recipe SFN execution against technology_breakthrough.
   aws stepfunctions start-execution \
     --state-machine-arn arn:aws:states:eu-central-1:771606957899:stateMachine:qgi-recipe-fleet \
     --input '{"RUN_MODE":"canary","RECIPE_IDS":["technology_breakthrough"]}' \
     --region eu-central-1
   ```

   **Precondition check**: `aws s3 ls s3://qgi-data-lake-771606957899/ml-results/technology_breakthrough/greedy-result.json` MUST return NoSuchKey, else the resume guard at `recipe_fleet_entrypoint.py:1050` skips the walk and the canary proves nothing about the new step.

4. **Canary expected outputs**:
   - `ml-results/technology_breakthrough/f-ml-1-poc-summary.json` — present + has `calibration` block (#969).
   - `ml-results/technology_breakthrough/country-scores.json` — present (#967).
   - SFN execution status `SUCCEEDED`.
   - CloudWatch logs from the Batch job show `score_countries complete for technology_breakthrough in <wall-clock>` (#967 hook).
   - Diff harness report shows greedy-result.json + summary.json are bit-identical to the pre-#129 canary on the same recipe (§2.5 contract for #129 alone — score_countries.json is NEW so no prior baseline to diff).

5. **foreign_intervention re-walk** (after canary green):

   ```bash
   # 1. Archive the stale walk (filed 2026-05-25 pre-floors-freeze)
   aws s3 mv s3://qgi-data-lake-771606957899/ml-results/foreign_intervention/ \
             s3://qgi-data-lake-771606957899/ml-results/_archive/foreign_intervention-pre-fix/ \
             --recursive --region eu-central-1

   # 2. Fire 1-recipe SFN execution
   aws stepfunctions start-execution \
     --state-machine-arn arn:aws:states:eu-central-1:771606957899:stateMachine:qgi-recipe-fleet \
     --input '{"RECIPE_IDS":["foreign_intervention"]}' \
     --region eu-central-1
   ```
