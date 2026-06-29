# Lessons Learned

Notes from building and running the Scenario-Based Validation POC on a GPU
instance. Each entry describes what went wrong (or what surprised us), why it
happened, and what to do about it. The goal is that the next person can avoid
the same time sinks.

## Pipeline overview

The POC has three model stages plus a dashboard:

1. Cosmos Predict2.5 generates a short driving clip from a text prompt (the
   synthetic scenario).
2. YOLOv8n runs on the generated frames as the System Under Test (SUT) and
   reports what it detected and which action it would take.
3. Cosmos Reason2-8B acts as the judge. It watches the clip and the SUT output
   and returns a structured safety verdict.
4. A Streamlit dashboard reads `outputs/manifest.json` and shows the clips,
   detections, and verdicts.

## Cosmos Predict2.5 generation

- The clip length is fixed by the checkpoint, not by our request. The model
  produces 93 frames (about 4.6 seconds at 20 fps) regardless of the
  `--clip-seconds` or `--max-gen-frames` values we pass. Treat those flags as
  upper bounds, not exact targets.
- The two real levers for speed are the number of denoising steps
  (`COSMOS_PREDICT_NUM_STEPS`) and the number of scenarios. Fewer steps and
  fewer scenarios mean a faster run. Each clip took roughly 12 minutes at 20
  steps.
- On a 48 GB GPU (L40S) keep the model resident with
  `COSMOS_PREDICT_LOWVRAM=0`. The low-VRAM path is only needed on smaller cards
  and it is slower.

## Cosmos Reason judge

- The judge crashed when the video path was passed as a `file://` URI. The
  transformers `load_video` helper rejects `file://` and expects either a plain
  local path or an http URL. Fix: pass the absolute path with no `file://`
  prefix.
- Loading the 8B weights cold is slow because there are around 750 shards. If
  you read the weight files once first (a warm-up), the second load runs at
  roughly 397 shards per second instead of seconds per shard. Pre-warming the
  weights before the real run saves a lot of time.
- The judge returned a `failure_category` of "unknown" or null because the
  prompt asked for "a string or null" without giving the model a list to choose
  from. Fix: give the model the exact set of allowed categories (from
  `config/judge_rubric.yaml`) and tell it to pick one, or null only when the
  scenario passes. Keep the prompt list and the rubric `allowed_values` in sync,
  otherwise the validator will overwrite the model's answer with "unknown".
- The judge change only affects future runs. Verdicts already written to
  `manifest.json` keep their old values until the judge runs again.

## Re-running only the judge

- Regenerating clips is the expensive part. We added a reuse mode
  (`SBV_REUSE_CLIPS=1`) so the judge can run against clips that already exist on
  disk. This lets us fix a judge bug and re-judge in a few minutes instead of
  re-generating for over half an hour.

## AWS and the GPU instance

- A stopped GPU instance is not guaranteed to start again. Starting it can fail
  with `InsufficientInstanceCapacity` when AWS has no hardware free in that
  Availability Zone. Plan for this: do not assume you can stop an instance
  overnight and restart it on demand. Retrying over several minutes sometimes
  helps, but there is no guarantee.
- AWS SSO sessions expire. When the session expired mid-run, the automatic
  stop-the-instance step failed because it needed an AWS API call. Important
  detail: SSH and SCP use the key pair and keep working even when SSO is
  expired. Only AWS API calls (start, stop, describe) need a valid SSO login.
  Run `aws sso login --profile poc` before relying on any API based auto-stop.
- Billing while stopped: a stopped instance does not bill for compute, but its
  EBS volumes still cost storage every month. Snapshots and custom AMIs also
  cost storage. An Elastic IP costs money when it is allocated but not attached
  to a running instance. To reach zero cost you have to terminate the instances
  and delete the volumes, snapshots, and AMIs, which is destructive and cannot
  be undone.

## Shell and tooling gotchas

- zsh does not split an unquoted variable into separate words. If you put SSH
  options in a variable like `SSHOPT="-i key -o ..."` and then run
  `ssh $SSHOPT host`, zsh passes the whole thing as one argument and the command
  fails. Pass each option as a separate literal argument instead.
- The terminal tool sometimes drops a leading `cd ... &&` and runs the rest from
  the workspace root, which changes the working directory you expected. Work
  around it by using absolute paths and command-line flags rather than relying
  on the current directory.
- Be careful with `pkill -f` and pattern matching. A pattern meant to kill a
  remote process matched the local SSH command that contained the same text, so
  it killed the wrong process. Use a bracketed pattern (for example
  `[r]un_demo` instead of `run_demo`) so the pattern does not match itself.

## Streamlit version differences

- This machine has an older Streamlit. `st.image` does not accept
  `use_container_width`; it needs `use_column_width`. The newer keyword raises an
  error. Note that `st.dataframe` and `st.plotly_chart` do accept
  `use_container_width` in the same version, so only the image calls had to
  change.
- The Streamlit theme can be set with a `.streamlit/config.toml` file
  (`[theme]` with `base = "light"`) or with the `--theme.base light` flag on the
  command line.

## Security reminder

- A Hugging Face token was exposed in an earlier session while pulling the
  Cosmos models. Rotate that token. Do not paste tokens into commands that get
  logged.
