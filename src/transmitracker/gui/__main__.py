"""Run the local desktop, without activating integrations or making HTTP calls."""

import argparse
from pathlib import Path


def main():
    from transmitracker.gui.app import TransMiTrackerApp

    parser = argparse.ArgumentParser(description=__doc__)
    examples = parser.add_mutually_exclusive_group()
    examples.add_argument(
        "--demo", action="store_true", help="Abre el espacio separado de ejemplos técnicos"
    )
    examples.add_argument(
        "--qa-demo", action="store_true", help="Ejemplos técnicos separados de Fase 2.1"
    )
    args = parser.parse_args()
    app = TransMiTrackerApp(
        Path(__file__).resolve().parents[3],
        "data/phase2_1/demo" if args.qa_demo else "data/phase2/demo" if args.demo else "data/gui",
    )
    app.mainloop()


if __name__ == "__main__":
    main()
