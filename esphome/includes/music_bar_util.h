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

inline size_t count_non_empty(const std::vector<std::string> &values) {
  size_t n = 0;
  for (const auto &v : values)
    if (!v.empty())
      n++;
  return n;
}

}  // namespace music_bar
