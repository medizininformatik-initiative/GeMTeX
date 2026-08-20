# Release-view normalization and blacklist metadata

## Goal

The GUI should support two closely related sanitization workflows over INCEpTION/UIMA exports:

1. **Policy sanitization**: validate and sanitize annotations against a policy view.
2. **Release-view normalization**: transform arbitrary annotations to concepts that are valid in a selected SNOMED CT release view, without requiring whitelist membership.

Both workflows can reuse the same phases:

```text
INCEpTION export + HDF5
        |
Check annotations
        |
Suggest replacements
        |
Review suggestions
        |
Apply reviewed replacements to a copied export
```

## Target views

### Policy view

Current behavior.

An annotation is valid when its code is:

```text
active at policy date
AND in whitelist policy view
AND not in blacklist policy view
```

A replacement candidate is acceptable when it is:

```text
active at policy date
AND in whitelist policy view
AND not in blacklist policy view
AND not SNOMED CT root
```

### Release active-concept view

New mode.

An annotation is valid when its code is:

```text
known in the HDF5/release
AND active in the release view
AND, optionally, not blacklisted
```

A replacement candidate is acceptable when it is:

```text
active in the release view
AND, optionally, not blacklisted
AND not SNOMED CT root
```

There is no whitelist requirement in this mode.

## Optional blacklist in release view

Release-view normalization may use no blacklist, or one of two blacklist sources:

1. **Embedded HDF5 blacklist**: use `/policy_views/blacklist/0` already stored in the HDF5.
2. **Runtime blacklist**: upload a blacklist rule file and resolve it at runtime, if the HDF5 contains enough concept/FSN and ancestor data.

The blacklist rule file is line-separated:

```text
non-numeric line -> exclude by FSN semantic tag
numeric line     -> exclude that concept and its descendants
```

Example:

```text
substance
373873005
organism
```

## Minimal HDF5 blacklist metadata

The HDF5 should not duplicate resolved blacklist concepts, because those are already derivable from `/policy_views/blacklist/0` or legacy `/blacklist/0`.

Store only compact provenance/rule metadata:

```text
/metadata/blacklists/0/format_version
/metadata/blacklists/0/source_name
/metadata/blacklists/0/rules_raw
/metadata/blacklists/0/rules_kind
```

Where `rules_kind` contains:

```text
fsn_tag
concept_descendants
```

No resolved SCTIDs, FSNs, descendant lists, or per-rule counts should be stored.

The GUI can display the resolved blacklist count from the existing blacklist view and show the rules from metadata. Numeric rule FSNs may be looked up dynamically from `/concepts` for display, but should not be stored redundantly.

## GUI refactor direction

Refactor the GUI around a shared target-view workflow:

```text
Sidebar:
  INCEpTION project ZIP
  HDF5 file
  Target view:
    - Policy view
    - Release active-concept view
  Release blacklist options:
    - no blacklist
    - embedded HDF5 blacklist
    - runtime blacklist file
  Annotation layers
  Ignore-overlap layers

Tabs:
  1. Check annotations
  2. Suggest replacements
  3. Review & apply
```

The review/apply tab should stay shared. Suggestions JSON should include target-view metadata so reviewed decisions can be interpreted correctly later.
