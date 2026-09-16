# Vendored FontTools 4.63.0

FrontMind carries this pinned, platform-neutral Python subset of FontTools so
the final DOCX font embedding and audit work from a freshly extracted release
without a host `fontTools` installation. The runtime keeps all upstream Python
modules and package data; compiled accelerators, generated C sources, bytecode,
console scripts and distribution metadata are omitted. FontTools falls back to
the included Python implementations for the operations used here.

The package is MIT licensed. The upstream license and external-test-font notice
are retained under `licenses/`. `VENDOR.json` records the exact version, file
count and deterministic code-tree digest checked before every production load.

The release uses only `fontTools.subset` and `fontTools.ttLib` against the
bundled Noto OTFs. Optional FontTools extras are not required.
