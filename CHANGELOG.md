# Changelog

## 2.0.0 (unreleased)

- Fix ECMAScript and JSON string escaping for punctuation, controls, astral
  code points and lone UTF-16 surrogates while preserving quote options.
  Regression reports credited to wjsw1781 (PR #4) and AugustineFulgur (PR #5).
  Their proposed range-specific and Python `repr` replacements are superseded
  by a general ECMAScript-aware implementation. No GitHub PR state is changed.
