"""Open saved tracker reports in a standalone offline window."""

import argparse
import tkinter

from transmitracker.viewer.data import ViewerError, load


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", help="Existing private tracker JSON")
    parser.add_argument("--catalog", help="Local read-only SQLite catalog")
    parser.add_argument("--demo", action="store_true", help="Entirely synthetic in-memory example")
    args = parser.parse_args(argv)
    if args.demo and (args.report or args.catalog):
        parser.exit(2, "Use --demo sin reporte ni catálogo real.\n")
    try:
        from transmitracker.viewer.app import Viewer

        if args.demo:
            from transmitracker.viewer.demo import make_demo

            scene = make_demo()
        else:
            scene = load(args.report, args.catalog) if args.report else None
        app = Viewer(scene)
        app.report_path, app.catalog_path = args.report, args.catalog
        app.mainloop()
        return 0
    except ViewerError as error:
        parser.exit(2, str(error) + "\n")
    except tkinter.TclError:
        parser.exit(2, "No se pudo iniciar el entorno gráfico Tk; no se abrió el visor.\n")


if __name__ == "__main__":
    raise SystemExit(main())
