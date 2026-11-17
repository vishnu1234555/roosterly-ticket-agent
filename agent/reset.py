"""Re-open all practice tickets: python -m agent.reset
It asks you to type RESET, and refuses after the final run (when FINAL_RUN_DONE exists)."""
from __future__ import annotations

import sys

from agent.config import ROOT, load_settings
from agent.helpdesk import Helpdesk


def main() -> int:
    if (ROOT / "FINAL_RUN_DONE").exists():
        print("Refusing to reset: FINAL_RUN_DONE exists, so the scored run is done.")
        return 1
    helpdesk = Helpdesk(load_settings())
    print("Status now:", helpdesk.status())
    if input("This re-opens all practice tickets. Type RESET to continue: ").strip() != "RESET":
        print("Cancelled. Nothing was reset.")
        return 1
    helpdesk.reset()
    print("Status after reset:", helpdesk.status())
    return 0


if __name__ == "__main__":
    sys.exit(main())
