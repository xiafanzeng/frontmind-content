# FrontMind bundled Chinese fonts

Runtime 4.11 bundles Noto Sans CJK SC Regular/Bold under the SIL Open Font
License. Every generated DOCX uses these faces and embeds deterministic glyph
subsets, so delivery does not depend on an installed host font or Fontconfig.

The runtime uses `lxml` plus the pinned, bundled FontTools source to build and
independently audit both embedded font parts. A failed embedding or glyph audit
stops DOCX production instead of publishing a document with missing Chinese
characters.
