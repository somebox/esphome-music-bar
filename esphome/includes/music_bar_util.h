// Small helpers used by the API action handlers.
//
// Kept separate from music_bar_monogram.h, which is pinned by a test that diffs it
// against the Python normalizer and should stay narrow.

#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace music_bar {

// Drop scheme and host, keeping path and query.
//
// Music Assistant answers on two ports (8095 and 8097 on the reference
// install) and Home Assistant alternates entity_picture between them, so the
// same artwork arrives as two different URLs seconds apart. Comparing whole
// URLs makes every other push look like a change and re-downloads artwork that
// is already on screen. (docs/spec.md section 6)
inline std::string strip_origin(const std::string &url) {
  size_t scheme = url.find("://");
  if (scheme == std::string::npos)
    return url;
  size_t path = url.find('/', scheme + 3);
  if (path == std::string::npos)
    return "/";
  return url.substr(path);
}

// Safe indexing into a page's arrays.
//
// Home Assistant sends a short array on the last page — three items rather
// than five — so the tile-painting code indexes past the end by design and
// gets an empty string, which the caller renders as an empty tile.
// Home Assistant's non-values, as they arrive over the wire.
//
// An attribute that does not exist comes through as the literal string
// "unknown" or "unavailable" rather than as an empty one, and a Python None
// renders as "None". Printing those on a hifi display looks like a fault in
// the panel; they mean "nothing is playing".
inline std::string clean(const std::string &value) {
  if (value == "unknown" || value == "unavailable" || value == "None" ||
      value == "none" || value == "null")
    return "";
  return value;
}

inline std::string nth(const std::vector<std::string> &values, size_t index) {
  return index < values.size() ? values[index] : std::string();
}

inline size_t count_non_empty(const std::vector<std::string> &values) {
  size_t n = 0;
  for (const auto &v : values)
    if (!v.empty())
      n++;
  return n;
}

}  // namespace music_bar
