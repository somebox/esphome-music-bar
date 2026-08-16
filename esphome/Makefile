# Convenience targets for the music-bar ESPHome firmware.
#
# Default ESPHOME is `esphome` on PATH. The root Makefile prefers
# .venv/bin/esphome when present. Override to test other versions:
#
#   make config ESPHOME=esphome@dev
#   make run    ESPHOME=esphome@2026.5 DEVICE=music-bar-kitchen
#
# Install parallel versions with pipx:
#
#   pipx install esphome
#   pipx install --suffix=@2026.5 esphome==2026.5.0
#   pipx install --suffix=@dev    esphome==dev

ESPHOME ?= esphome
DEVICE  ?= music-bar-kitchen
YAML     = $(DEVICE).yaml

# Where to flash or read logs from. Leave unset and ESPHome asks — which is
# fine interactively and unhelpful in a loop. Set it to a serial port for a
# cable flash, or to a hostname once the panel is on Wi-Fi and you want OTA:
#
#   make factory-run PORT=/dev/cu.usbmodem112201
#   make logs        PORT=music-bar-a1b2c3.local
#
# The first flash of a panel running other firmware has to be over the cable;
# OTA needs the panel already running a build of this project.
#
# A serial port does not identify what is on the other end of it. If more than
# one board is ever plugged into this machine, prefer OTA by hostname — which
# is unambiguous — and check `esphome logs PORT=...` before uploading to a
# port. Flashing this firmware onto something else is a bad afternoon.
PORT ?=
DEVICE_ARG = $(if $(PORT),--device $(PORT),)
FACTORY_YAML := music-bar.factory.factory.yaml
# music-bar.base.yaml is deliberately absent. It carries the LVGL layout, which
# references the display the device profile defines, so it no longer validates
# on its own — it is only ever built through a profile. Every config below
# includes it, so it is still covered.
#
# probe-image-slots.yaml is absent for the opposite reason: it predates the
# display and needs rewriting against the real one before it can run.
ALL_CONFIGS := music-bar.example.yaml music-bar.factory.yaml \
               music-bar.factory.factory.yaml

.PHONY: version config compile run logs clean factory-config factory factory-run \
        factory-logs probe smoke-test

version:
	@$(ESPHOME) version

config:
	$(ESPHOME) config $(YAML)

compile:
	$(ESPHOME) compile $(YAML)

run:
	$(ESPHOME) run $(YAML) $(DEVICE_ARG)

logs:
	$(ESPHOME) logs $(YAML) $(DEVICE_ARG)

clean:
	rm -rf .esphome

# Factory image (bench flash / web flasher).
factory-config:
	$(ESPHOME) config $(FACTORY_YAML)

factory: factory-config
	$(ESPHOME) compile $(FACTORY_YAML)

factory-run: factory
	$(ESPHOME) run $(FACTORY_YAML) $(DEVICE_ARG)

# Logs from the factory build, without recompiling.
factory-logs:
	$(ESPHOME) logs $(FACTORY_YAML) $(DEVICE_ARG)

# The PSRAM probe from docs/plan.md phase 1. Flash it, then page back and
# forth and watch the largest free block rather than the free total.
probe:
	$(ESPHOME) run probe-image-slots.yaml $(DEVICE_ARG)

# Automated smoke test (no hardware). Validates every config and compiles the
# factory binary. Run before pushing. On-device checks are in docs/plan.md.
smoke-test:
	@echo "==> config validation"
	@for f in $(ALL_CONFIGS); do \
		$(ESPHOME) config $$f >/dev/null && echo "  OK: $$f" || { echo "  FAIL: $$f"; exit 1; }; \
	done
	@echo "==> compile factory image"
	$(ESPHOME) compile $(FACTORY_YAML) && echo "  OK: compile"
	@echo "==> smoke-test passed"
