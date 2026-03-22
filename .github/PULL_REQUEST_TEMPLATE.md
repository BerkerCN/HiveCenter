## Description
<!-- Please include a summary of the change and which issue is fixed. -->
<!-- Include relevant motivation and context. List any dependencies that are required for this change. -->

Fixes # (issue)

## Type of Change
Please delete options that are not relevant.
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] System documentation or automation update

## Verification Protocol
Please confirm that your changes are validated against the execution framework:
- [ ] `make test` passes (or `pytest tests/` with the same environment as CI).
- [ ] `make lint` passes (flake8: syntax / undefined names per project rules).
- [ ] The core orchestration loop still runs without unhandled exceptions in your manual smoke check (if you touched runtime paths).
- [ ] Platform-specific entrypoints you changed (`start.sh`, `hive_app.py`, Docker) still behave as expected.

## Checklist:
- [ ] My code follows the style guidelines of this project
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] My changes generate no new flake8 warnings
- [ ] I have made corresponding changes to the documentation
