 Currently, site is not part of the identity. The adapter checks:

 ```text
   (document name, trimmed/lowercased annotator name)
 ```

 If the same pair occurs across sites in the selected scope, processing fails explicitly—nothing is merged or overwritten. Selecting a single export can avoid that collision.

 That is a limitation of this minimal implementation. For combined-site processing, we should make document identity site-aware, e.g. (site, document name), and carry that distinction through findings, context
 and review. The same annotator name could then occur at different sites without conflating their annotations.