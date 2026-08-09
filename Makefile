# Root convenience wrappers. The real ESPHome targets live in esphome/Makefile.
#
#   make smoke-test     # validate YAMLs + compile factory + run tests
#   make test           # Python + device-agreement tests only, no ESPHome
#   make factory-run    # compile, flash and monitor the factory image
#   make check          # is your artwork setup workable? (needs a config)
#
# ESPHOME defaults to .venv/bin/esphome when present, otherwise `esphome` on
# PATH. Override: make smoke-test ESPHOME=esphome@2026.5.0

ESPHOME ?= $(if $(wildcard $(CURDIR)/.venv/bin/esphome),$(CURDIR)/.venv/bin/esphome,esphome)

# uv resolves the test dependencies per-run, so there is nothing to install.
UV ?= uv
PYTEST := $(UV) run --quiet --with pytest --with 'pillow>=10.1' --with 'pyyaml>=6' pytest

.PHONY: smoke-test test check factory factory-run factory-config probe version

test:
	$(PYTEST) tests/ -q

check:
	./scripts/normalize-artwork.py --check

smoke-test: test
	$(MAKE) -C esphome ESPHOME="$(ESPHOME)" smoke-test

factory factory-run factory-config probe version:
	$(MAKE) -C esphome ESPHOME="$(ESPHOME)" $@
