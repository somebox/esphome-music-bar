// Monograms, drawn on the device.
//
// When no artwork is configured the panel still shows a tile for every item:
// the item's initials on a colour derived from its name. No image slot, no
// PSRAM buffer, no fetch — so the browser works with nothing installed beyond
// the firmware and a blueprint, and artwork becomes an upgrade rather than a
// prerequisite.
//
// The colour has to match what scripts/normalize-artwork.py produces, because
// the same item may be drawn here on one install and rendered to a PNG on
// another, and screenshots of the two should look like the same product.
// fnv1a() and hsv_to_rgb() below are exact ports of the Python; tests/ compiles
// this file and diffs it against the script for a list of names. Change one
// side and the test fails.

#pragma once

#include <cstdint>
#include <string>

namespace music_bar {

// 32-bit FNV-1a over UTF-8 bytes. Cheap enough to run for five tiles on a page
// turn, and identical to fnv1a() in scripts/normalize-artwork.py.
inline uint32_t fnv1a(const std::string &text) {
  uint32_t h = 0x811C9DC5u;
  for (unsigned char c : text) {
    h ^= c;
    h *= 0x01000193u;
  }
  return h;
}

struct Rgb {
  uint8_t r, g, b;
};

// Port of Python's colorsys.hsv_to_rgb plus the int() truncation the script
// applies. Doubles throughout, because float rounding here would show up as
// tiles that are one step off the rendered PNGs.
inline Rgb hsv_to_rgb(double h, double s, double v) {
  auto byte = [](double c) { return static_cast<uint8_t>(c * 255.0); };
  if (s == 0.0)
    return Rgb{byte(v), byte(v), byte(v)};

  int i = static_cast<int>(h * 6.0);
  double f = (h * 6.0) - i;
  double p = v * (1.0 - s);
  double q = v * (1.0 - s * f);
  double t = v * (1.0 - s * (1.0 - f));
  switch (i % 6) {
    case 0: return Rgb{byte(v), byte(t), byte(p)};
    case 1: return Rgb{byte(q), byte(v), byte(p)};
    case 2: return Rgb{byte(p), byte(v), byte(t)};
    case 3: return Rgb{byte(p), byte(q), byte(v)};
    case 4: return Rgb{byte(t), byte(p), byte(v)};
    default: return Rgb{byte(v), byte(p), byte(q)};
  }
}

// Deterministic, so an item keeps its colour between runs and between installs,
// and spread across the hue circle, so a page of them reads as a design rather
// than as five identical failure icons.
inline Rgb monogram_bg(const std::string &name) {
  return hsv_to_rgb(fnv1a(name) / 4294967295.0, 0.45, 0.40);
}

inline Rgb monogram_fg(const std::string &name) {
  return hsv_to_rgb(fnv1a(name) / 4294967295.0, 0.12, 0.96);
}

// Packed for lvgl.*.update: bg_color / text_color, which take a 24-bit int.
inline uint32_t monogram_bg_hex(const std::string &name) {
  Rgb c = monogram_bg(name);
  return (uint32_t(c.r) << 16) | (uint32_t(c.g) << 8) | c.b;
}

inline uint32_t monogram_fg_hex(const std::string &name) {
  Rgb c = monogram_fg(name);
  return (uint32_t(c.r) << 16) | (uint32_t(c.g) << 8) | c.b;
}

// One or two letters from the name, matching the script for ASCII names.
//
// Returns "" when the name yields no ASCII letter or digit — an item named only
// in a non-Latin script, say. The caller then falls back to the media-type
// glyph rather than printing a "?", which is the second fallback tier. The
// script has Python's full Unicode .upper() available and this does not, so
// agreement is only claimed for ASCII; the colour agrees either way.
inline std::string initials(const std::string &name) {
  std::string out;
  bool at_word_start = true;
  for (char ch : name) {
    unsigned char c = static_cast<unsigned char>(ch);
    bool separator = (c == ' ' || c == '\t' || c == '-' || c == '_' || c == '/');
    if (separator) {
      at_word_start = true;
      continue;
    }
    bool alnum = (c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') ||
                 (c >= 'a' && c <= 'z');
    if (at_word_start && alnum) {
      out += static_cast<char>(c >= 'a' && c <= 'z' ? c - 32 : c);
      if (out.size() == 2)
        return out;
    }
    // A word whose first character is not ASCII-alphanumeric is skipped
    // entirely, as it is in the script.
    at_word_start = false;
  }

  // A single word contributes its first two characters, not just its first.
  if (out.size() == 1) {
    size_t i = name.find_first_not_of(" \t-_/");
    if (i != std::string::npos && i + 1 < name.size()) {
      unsigned char second = static_cast<unsigned char>(name[i + 1]);
      bool alnum = (second >= '0' && second <= '9') ||
                   (second >= 'A' && second <= 'Z') ||
                   (second >= 'a' && second <= 'z');
      bool one_word = name.find_first_of(" \t-_/", i) == std::string::npos;
      if (one_word && alnum)
        out += static_cast<char>(second >= 'a' && second <= 'z' ? second - 32
                                                                : second);
    }
  }
  return out;
}

}  // namespace music_bar
