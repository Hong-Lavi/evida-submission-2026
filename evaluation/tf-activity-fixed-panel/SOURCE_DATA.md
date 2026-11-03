# External inputs and exact identity

Acquire the external inputs separately from their official sources; the included reconstruction script reads local files.

| Input | Official locator | Exact identity |
|---|---|---|
| KnockTF expression | https://zenodo.org/records/7035528/files/knockTF_expr.csv?download=1 | SHA256 a97264b92be783e84c974af5090ea4f8fd3c27c087aac5d44e45fa7fc4e22a80; MD5 3fd4045f2e9f79a50b19ae312339b13c; 146086808 bytes |
| KnockTF metadata | https://zenodo.org/records/7035528/files/knockTF_meta.csv?download=1 | SHA256 4b27332cc9d84125dbea8120f52b559ebce946c0ae2a02310be23892dd9ed626; MD5 2b93506dd196c8eeed2a46aadc02ac74 |
| DoRothEA prior TSV | OmniPath / decoupleR get_dorothea human mRNA interactions | SHA256 a50a2692d7ac21f316d19856b6fd4e92810e9996803a128e55e33d2bf752c520 |
| CollecTRI prior TSV | OmniPath / decoupleR get_collectri human mRNA interactions, TF-miRNA omitted | SHA256 39f7eef18dedcfa318469fe62875c50a994c0fdf0d335d194fa8ef5c22216e90 |

The frozen prior TSVs were produced by the author's retrieval transformation with a transport-only adaptation. A fresh query to a changing OmniPath service is not guaranteed to regenerate these bytes. Full inference reproduction needs authorized copies matching these SHA256 values; this package does not supply or claim a reproducible current-service replacement. Interpreter, package DESCRIPTION/rdb/rdx and all packet pins are in `frozen/pinned-product-regulon-resources.json` and `frozen/protocol.json`.

Author references: [decoupleR R package](https://saezlab.github.io/decoupleR/), [official KnockTF tutorial](https://decoupler.scverse.org/en/v1.9.2/notebooks/benchmark.html), [CollecTRI paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC10639077/), [CollecTRI benchmark code at preserved commit 86760ed852231c944396044c6fea4ecc38cc8bd1](https://github.com/saezlab/CollecTRI/blob/86760ed852231c944396044c6fea4ecc38cc8bd1/scripts/benchmark/02_benchmark.ipynb), [OmniPath](https://omnipathdb.org/). These are source locators from retained records; this packaging step made no network request.
