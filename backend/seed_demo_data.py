"""
Seed de DATOS DE DEMOSTRACIÓN (pasajeros, reservas, leads, conversaciones, tickets, equipo).

Wrapper de consola del servicio demo_data_service. Todo lo generado se marca is_demo=True,
así que limpiar borra solo lo demo (no toca datos reales ni la configuración).

Uso:
  python seed_demo_data.py            # regenera el dataset demo (limpia lo demo y crea fresco)
  python seed_demo_data.py --clear    # borra solo los datos demo
  python seed_demo_data.py --status   # muestra cuántos datos demo hay
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


def _prepare_db():
    """Importa modelos, crea tablas y aplica migraciones (incluye columnas is_demo)."""
    import importlib
    import pkgutil
    import app.models as models_pkg
    for mod in pkgutil.iter_modules(models_pkg.__path__):
        importlib.import_module(f"app.models.{mod.name}")
    from app.models.database import Base, engine, run_light_migrations
    Base.metadata.create_all(bind=engine)
    run_light_migrations()


def main():
    _prepare_db()
    from app.models.database import SessionLocal
    from app.services import demo_data_service

    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    db = SessionLocal()
    try:
        if arg in ("--clear", "--reset"):
            res = demo_data_service.clear(db)
            print("Datos demo eliminados:", res)
        elif arg == "--status":
            print("Datos demo actuales:", demo_data_service.counts(db))
        else:
            print("Generando datos demo (esto puede tardar unos segundos)…")
            res = demo_data_service.populate(db)
            print("\nDataset demo creado:")
            for k, v in res.items():
                print(f"  {k:>14}: {v}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
