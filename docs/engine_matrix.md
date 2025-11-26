# Engine Matrix (paper & live)

Config-driven engine selection is defined under `engines.<mode>.<asset>` in the YAML configs.

## Config shape

```yaml
engines:
  paper:
    equity:
      enabled: true
      runner: apps.run_equity_paper
    fno:
      enabled: true
      runner: apps.run_fno_paper
    options:
      enabled: true
      runner: apps.run_options_paper
  live:
    equity:
      enabled: true     # in live.yaml; false in dev.yaml
      runner: scripts.run_live_equity
    options:
      enabled: false    # placeholder for future live options
      runner: scripts.run_live_options
```

`runner` is the module name invoked via `python -m <runner>`.

## Example commands

- Paper multi-engine session (multi-process):
  ```bash
  python -m scripts.run_session --mode paper --config configs/dev.yaml --layout multi
  ```
- Live equity session (multi-process, equity only enabled):
  ```bash
  python -m scripts.run_session --mode live --config configs/live.yaml --layout multi
  ```
- Live smoke test (always dry-run, warmup outside hours):
  ```bash
  python -m scripts.live_smoke_test --config configs/live.yaml --max-loops 60 --sleep-seconds 1.0
  ```

## Notes

- Paper defaults remain unchanged: equity/fno/options runners start when enabled.
- Live currently only starts equity; options runner is a placeholder for future LiveOptionsEngine.
- `execution.dry_run` should be respected by engines; the smoke test explicitly forces it to `True` for safety.
