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
FACTORY_YAML := music-bar.factory.factory.yaml
# probe-image-slots.yaml is deliberately absent: online_image needs a display:
# block, which lands with the AXS15231B port. Add it here at the same time.
ALL_CONFIGS := music-bar.base.yaml music-bar.example.yaml music-bar.factory.yaml \
               music-bar.factory.factory.yaml

.PHONY: version config compile run logs clean factory-config factory factory-run \
        probe smoke-test

version:
	@$(ESPHOME) version

config:
	$(ESPHOME) config $(YAML)

compile:
	$(ESPHOME) compile $(YAML)

run:
	$(ESPHOME) run $(YAML)

logs:
	$(ESPHOME) logs $(YAML)

clean:
	rm -rf .esphome

# Factory image (bench flash / web flasher).
factory-config:
	$(ESPHOME) config $(FACTORY_YAML)

factory: factory-config
	$(ESPHOME) compile $(FACTORY_YAML)

factory-run: factory
	$(ESPHOME) run $(FACTORY_YAML)

# The PSRAM probe from docs/plan.md phase 1. Flash it, then page back and
# forth and watch the largest free block rather than the free total.
probe:
	$(ESPHOME) run probe-image-slots.yaml

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
