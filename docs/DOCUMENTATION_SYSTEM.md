# Self-Documenting Repository System

## Overview

This repository features an automatic documentation generation system that keeps all documentation synchronized with the codebase.

## Generated Documentation

The `docs/` folder contains 15 auto-generated markdown files covering all aspects of the trading system:

### Core Documentation
- **Overview.md** - System architecture and big picture
- **RepoMap.md** - Complete file/folder structure with explanations

### Engine Documentation
- **Paper.md** - Paper trading engine internals
- **Live.md** - Live trading engine internals  
- **ExecutionEngine.md** - Execution router and broker abstraction

### Component Documentation
- **StrategyEngine.md** - Strategy framework and signal flow
- **MarketDataEngine.md** - Market data management and caching
- **RiskEngine.md** - Risk validation and position sizing
- **Indicators.md** - All technical indicators implemented
- **Strategies.md** - Complete strategy catalog
- **Signals.md** - Trading signal types and structure

### Operational Documentation
- **Backtesting.md** - Backtesting engine and reporting
- **Dashboard.md** - Web dashboard API and features
- **Commands.md** - Common CLI commands and workflows
- **Changelog.md** - Architectural change history

## How It Works

### Documentation Generation

The `scripts/generate_docs.py` script:
1. Scans the entire repository structure
2. Analyzes Python code using AST parsing
3. Extracts classes, methods, and API endpoints
4. Generates comprehensive markdown documentation
5. Includes ASCII diagrams for data flows
6. Is fully idempotent (same output on repeated runs)

### Automatic Updates

The `.github/workflows/docs_autogen.yml` GitHub Action:
1. Triggers on all pull requests and pushes to main
2. Runs the documentation generation script
3. Detects if documentation is out of sync
4. Automatically commits updates back to the branch
5. Posts PR comments with warnings and checklists
6. Validates architectural boundaries (live vs paper)

### File Change Detection

The workflow monitors these key files:
- `engine/paper_engine.py`
- `engine/live_engine.py`
- `broker/execution_router.py`
- `core/strategy_engine_v2.py`
- `core/risk_engine.py`
- `core/market_data_engine.py`
- `core/indicators.py`
- `strategies/*`
- `ui/dashboard.py`

When any of these files change, documentation is automatically regenerated.

## Manual Regeneration

To manually regenerate documentation:

```bash
# Run the documentation generator
python scripts/generate_docs.py

# The script will:
# - Scan the repository
# - Generate 15 markdown files
# - Display a summary of created files
```

### Example Output

```
============================================================
DOCUMENTATION GENERATION SUMMARY
============================================================
  ✓ Backtesting.md                 (2,845 bytes)
  ✓ Changelog.md                   (739 bytes)
  ✓ Commands.md                    (3,767 bytes)
  ✓ Dashboard.md                   (4,429 bytes)
  ✓ ExecutionEngine.md             (1,885 bytes)
  ✓ Indicators.md                  (2,667 bytes)
  ✓ Live.md                        (3,247 bytes)
  ✓ MarketDataEngine.md            (2,065 bytes)
  ✓ Overview.md                    (2,367 bytes)
  ✓ Paper.md                       (3,312 bytes)
  ✓ RepoMap.md                     (4,217 bytes)
  ✓ RiskEngine.md                  (3,014 bytes)
  ✓ Signals.md                     (2,964 bytes)
  ✓ Strategies.md                  (1,437 bytes)
  ✓ StrategyEngine.md              (3,166 bytes)
============================================================

Total: 15 files generated
Location: /home/runner/work/kite-algo-minimal/kite-algo-minimal/docs
```

## Architecture Boundaries

The system validates that:
- Live engine code doesn't leak into paper engine
- Paper engine code doesn't leak into live engine
- Strategy additions are documented
- Indicator changes are reflected
- API endpoint modifications are tracked

### Validation Warnings

The GitHub Action will warn if:
```
⚠️  WARNING: Potential live code leak in paper_engine.py
⚠️  WARNING: Potential paper code leak in live_engine.py
```

## Benefits

### For Developers
- **Always Up-to-Date**: Documentation never falls behind code
- **Instant Onboarding**: New developers can understand system quickly
- **Clear Architecture**: Visual diagrams and component relationships
- **Safe Refactoring**: Boundary violations are detected automatically

### For AI Assistants
- **Complete Context**: Full system understanding in markdown
- **Structured Knowledge**: Clean separation of concerns
- **Quick Navigation**: Easy to find specific components
- **Pattern Recognition**: Consistent documentation format

### For Operations
- **CLI Reference**: All commands documented
- **Workflow Guides**: Step-by-step procedures
- **Troubleshooting**: Clear component responsibilities
- **Configuration**: Examples and best practices

## Idempotency

The documentation generator is fully idempotent:
- Running multiple times produces identical output (except timestamps)
- No accidental overwrites or data loss
- Safe to run before every commit
- Deterministic output based on code state

## Extensibility

### Adding New Documentation Sections

To add a new documentation file:

1. Add a generator function in `scripts/generate_docs.py`:
```python
def generate_my_new_docs() -> str:
    content = """# My New Section
    
    Documentation content here...
    
    ---
    *Auto-generated on {{timestamp}}*
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    return content.replace("{timestamp}", timestamp)
```

2. Add to the `main()` function:
```python
docs = {
    # ... existing docs
    "MyNewSection.md": generate_my_new_docs(),
}
```

3. Run the generator and commit changes

### Customizing Analysis

The `CodeAnalyzer` class can be extended to extract additional information:
- Decorators
- Type hints
- Constants
- Configuration values

## Preventing Manual Edits

⚠️ **Important**: Do not manually edit files in the `docs/` folder. They will be overwritten by the automation.

Instead:
1. Update the generator code in `scripts/generate_docs.py`
2. Run the generator manually to verify
3. Commit both generator changes and updated docs
4. The CI will validate consistency

## Troubleshooting

### Documentation Not Updating

If documentation doesn't update automatically:
1. Check GitHub Actions logs
2. Verify Python 3.12 compatibility
3. Check for parse errors in Python files
4. Manually run: `python scripts/generate_docs.py`

### Parse Warnings

If you see warnings like:
```
WARNING:__main__:Failed to parse /path/to/file.py
```

This means the file has syntax errors or unsupported Python constructs. Fix the Python file and regenerate.

### Timestamp Changes

Documentation includes generation timestamps. This is intentional:
- Shows when docs were last updated
- Helps identify stale documentation
- Useful for auditing

## Best Practices

1. **Run Before Commits**: Generate docs before major commits
2. **Review Changes**: Check doc diffs in PRs
3. **Update Generator**: Enhance generator for new patterns
4. **Add Diagrams**: Include ASCII art for complex flows
5. **Keep Current**: Regenerate after refactoring

## Integration with Development Workflow

### Development Flow
```
1. Write code
2. Run tests
3. Run: python scripts/generate_docs.py
4. Review docs/
5. Commit code + docs
6. Push to PR
7. CI validates and updates if needed
```

### Review Checklist (Automated)

On every PR, the bot comments with:
- [ ] Documentation accurately reflects code changes
- [ ] No live code leaked into paper engine
- [ ] No paper code leaked into live engine
- [ ] Strategy list is up to date
- [ ] Indicator list is complete

## Future Enhancements

Potential improvements:
- **Dependency graphs**: Visual module dependencies
- **API documentation**: OpenAPI/Swagger generation
- **Metrics tracking**: Code complexity trends
- **Change detection**: More sophisticated diff analysis
- **Multi-format**: Generate PDF/HTML versions

## Questions?

For issues with the documentation system:
1. Check this README
2. Review `scripts/generate_docs.py`
3. Check GitHub Actions logs
4. Open an issue with details

---

**Remember**: The documentation system makes the repository self-aware and always up-to-date. Keep the generator maintained, and the docs will maintain themselves!
