# Root convenience wrappers. The real ESPHome targets live in esphome/Makefile.
#
#   make smoke-test     # validate YAMLs + compile factory + run tests
#   make test           # Python + device-agreement tests only, no ESPHome
#   make factory-run    # compile, flash and monitor the factory image
#   make factory-logs   # reconnect to a running panel without recompiling
#   make check          # is your artwork setup workable? (needs a config)
#
# Flashing a panel over the cable, and watching it afterwards:
#
#   make factory-run  PORT=/dev/cu.usbmodem112201
#   make factory-logs PORT=music-bar-a1b2c3.local
#
# Omit PORT and ESPHome asks which device to use.
#
# ESPHOME defaults to .venv/bin/esphome when present, otherwise `esphome` on
# PATH. Override: make smoke-test ESPHOME=esphome@2026.5.0

ESPHOME ?= $(if $(wildcard $(CURDIR)/.venv/bin/esphome),$(CURDIR)/.venv/bin/esphome,esphome)

# uv resolves the test dependencies per-run, so there is nothing to install.
UV ?= uv
PYTEST := $(UV) run --quiet --with pytest --with 'pillow>=10.1' --with 'pyyaml>=6' pytest

.PHONY: smoke-test test check factory factory-run factory-config factory-logs \
        logs clean probe version

test:
	$(PYTEST) tests/ -q

check:
	./scripts/normalize-artwork.py --check

smoke-test: test
	$(MAKE) -C esphome ESPHOME="$(ESPHOME)" smoke-test

# PORT is forwarded so `make factory-run PORT=...` works from the repo root.
factory factory-run factory-config factory-logs logs clean probe version:
	$(MAKE) -C esphome ESPHOME="$(ESPHOME)" PORT="$(PORT)" $@
