# Local corpus and generated data

The source brochure and processed corpus files are local runtime data and are intentionally excluded from Git. This avoids publishing copyrighted or otherwise restricted material, generated embeddings, and large image assets by accident.

For a local setup, provide an authorized copy of the brochure at:

```text
data/documents/Brochure-EMSI.pdf
```

The repository's extraction/chunking/embedding scripts write generated artifacts under `data/processed/`. The backend serves indexed local image assets from that directory. Those files are also excluded from Git. Qdrant must separately contain the expected `emsi_text` and `emsi_images` collections; the normal startup procedure does not create or populate them.

Only run the data-preparation and indexing scripts when you are intentionally setting up or refreshing a local corpus and have reviewed the impact. Do not run them as part of ordinary application startup. Follow the code and local data permissions when preparing a corpus; this repository does not redistribute the brochure or prebuilt Qdrant data.
