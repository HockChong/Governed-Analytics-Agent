"""Copy thelook_ecommerce into ${SNAPSHOT_DATASET}.

Run via `make snapshot`; `make snapshot FORCE=1` adds --force.
"""

import sys

from ingestion.snapshot import main

if __name__ == "__main__":
    sys.exit(main())
