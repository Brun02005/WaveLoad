"""Verificación de la UI de Colecciones.

La suite de pytest es deliberadamente Qt-free (ver el principio 2 de
`ARQUITECTURA.md`), así que la parte de dibujo no está cubierta por tests. Este
script la cubre: levanta los widgets de verdad, manipula sus controles como lo
haría un usuario y verifica lo que sale.

**Nunca toca la librería real**: genera una librería sintética en un directorio
temporal que borra al terminar, así el resultado no depende de lo que el usuario
tenga guardado. Devuelve 0 si todo pasa, 1 si algo falla, así que sirve en CI.

Recorre los caminos que usa la interfaz de verdad (los mismos métodos que
disparan los botones), no atajos que asignan estado a mano.

Uso:
    python tools/smoke_collections_ui.py
    python tools/smoke_collections_ui.py --shot captura.png
"""

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

app = QApplication(sys.argv)

from domain.collections import LayerMode, QueryLayer  # noqa: E402
from domain.query_ast import and_, or_, range_, tag  # noqa: E402
from infrastructure.database import DatabaseManager  # noqa: E402
from services.collection_service import CollectionService  # noqa: E402
from storage.collection_repository import SqliteCollectionRepository  # noqa: E402
from storage.sqlite_track_repository import SqliteTrackRepository  # noqa: E402
from storage.tag_repository import SqliteTagRepository  # noqa: E402
from ui.dialogs.layer_editor_dialog import LayerEditorDialog, select_by_data  # noqa: E402
from ui.workspaces.collections_workspace import CollectionsWorkspace  # noqa: E402

FALLOS: list[str] = []


def check(nombre: str, condicion: bool, detalle: str = ""):
    print(("  OK    " if condicion else "  FALLA ") + nombre
          + (f"   [{detalle}]" if detalle and not condicion else ""))
    if not condicion:
        FALLOS.append(nombre)


def _seed(db: DatabaseManager):
    """Una librería mínima, por si se corre sin una librería real al lado."""
    import uuid
    from datetime import datetime, timezone
    from services.tagging_service import TaggingService

    ahora = datetime.now(timezone.utc).isoformat()
    with db.get_connection() as conn:
        for i in range(20):
            conn.execute(
                "INSERT INTO tracks (id, title, artist, duration, created_at,"
                " updated_at, source_platform) VALUES (?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), f"Track {i:02d}", f"Artista {i % 4}",
                 300 + i, ahora, ahora, "local"),
            )
        filas = [r[0] for r in conn.execute("SELECT id FROM tracks")]
        for i, track_id in enumerate(filas):
            conn.execute(
                "INSERT INTO track_analysis (track_id, bpm, musical_key,"
                " energy_level, analyzed_at) VALUES (?,?,?,?,?)",
                (track_id, 120.0 + i, "8A" if i % 2 else "6A",
                 float(1 + i % 10), ahora),
            )
        conn.commit()
    TaggingService(SqliteTagRepository(db=db)).backfill_derived()


def build_service(tmp: Path) -> CollectionService:
    db = DatabaseManager(db_path=tmp / "smoke.db")
    _seed(db)
    return CollectionService(
        collection_repository=SqliteCollectionRepository(db=db),
        track_repository=SqliteTrackRepository(db=db),
        tag_repository=SqliteTagRepository(db=db),
    )


def probar_dialogo(service):
    print("\n== LayerEditorDialog ==")
    d = LayerEditorDialog(service=service)
    fila = d._rows[0]
    check("arranca con una condición", len(d._rows) == 1)
    check("el desplegable arranca en un namespace poblado",
          fila.combo_value.count() > 0, f"count={fila.combo_value.count()}")
    check("con una sola condición no se puede quitar",
          not fila.btn_remove.isEnabled())

    # Una condición simple
    select_by_data(fila.combo_namespace, "key")
    valores = [fila.combo_value.itemData(i) for i in range(fila.combo_value.count())]
    check("los valores salen del vocabulario de la librería", bool(valores), str(valores[:4]))
    fila.combo_value.setEditText(valores[0] if valores else "8a")
    select_by_data(d.combo_mode, LayerMode.EXCLUDE)
    d._on_accept()
    check("produce un predicado", d.result_predicate is not None)
    check("produce el modo elegido como enum", d.result_mode is LayerMode.EXCLUDE,
          repr(d.result_mode))

    # Dos condiciones en OR, con un valor tipeado a mano
    d = LayerEditorDialog(service=service)
    select_by_data(d.combo_join, "or")
    select_by_data(d._rows[0].combo_namespace, "key")
    d._rows[0].combo_value.setEditText("8a")
    segunda = d._add_row()
    select_by_data(segunda.combo_namespace, "key")
    segunda.combo_value.setEditText("6a")
    d._on_accept()
    check("un valor tipeado a mano gana sobre el seleccionado",
          d.result_predicate == or_(tag("key", "8a"), tag("key", "6a")),
          str(d.result_predicate))

    # Rango negado, y rango invertido
    d = LayerEditorDialog(service=service)
    fila = d._rows[0]
    select_by_data(fila.combo_kind, "range")
    select_by_data(fila.combo_field, "bpm")
    fila.spin_min.setValue(140)
    fila.spin_max.setValue(120)
    fila.combo_negated.setCurrentIndex(1)
    d._on_accept()
    check("negar envuelve en NOT", d.result_predicate.op == "not", str(d.result_predicate))
    check("un rango invertido se ordena solo en vez de fallar",
          d.result_predicate.nodes[0] == range_("bpm", 120.0, 140.0),
          str(d.result_predicate))

    # Condición incompleta
    d = LayerEditorDialog(service=service)
    select_by_data(d._rows[0].combo_kind, "text")
    d._rows[0].edit_value.setText("   ")
    d._on_accept()
    check("una condición incompleta no cierra el diálogo", d.result_predicate is None)
    check("y explica qué falta", bool(d.lbl_error.text()), d.lbl_error.text())

    # Round-trip de una capa existente
    capa = QueryLayer(and_(tag("key", "8a"), range_("bpm", 122, 128)), LayerMode.EXCLUDE, 0)
    d = LayerEditorDialog(service=service, layer=capa)
    check("editar carga las dos condiciones", len(d._rows) == 2)
    check("editar carga el modo", d.selected_mode() is LayerMode.EXCLUDE)
    d._on_accept()
    check("round-trip idéntico", d.result_predicate == capa.predicate, str(d.result_predicate))


def _esperar(ws, ms: int = 8000):
    """Espera a que terminen los workers y deja llegar sus señales.

    ``processEvents`` sola no alcanza: la evaluación corre en otro hilo y las
    señales no llegan hasta que ese hilo termina.
    """
    ws.pool.waitForDone(ms)
    for _ in range(50):
        app.processEvents()


def probar_workspace(service, shot: Path = None):
    print("\n== CollectionsWorkspace ==")
    ws = CollectionsWorkspace(service=service)
    ws.resize(1280, 860)
    ws.activate()

    ws.show()
    app.processEvents()
    check("estado vacío: lo explica",
          ws.lbl_empty.isVisible() and "Sin colecciones" in ws.lbl_empty.title_label.text())
    check("estado vacío: no deja controles muertos a la vista",
          not ws.btn_add_layer.isVisible() and not ws.table.isVisible()
          and not ws.btn_delete.isVisible())

    # --- Caminos reales de la UI --------------------------------------------
    # «Nueva» con la lista vacía: antes la colección quedaba creada pero el
    # panel seguía en el estado vacío, sin el botón de agregar capa.
    ws._on_new()
    _esperar(ws)
    check("«Nueva» abre la colección creada",
          ws.current is not None and ws.lbl_title.text() == ws.current.name,
          ws.lbl_title.text())
    check("y muestra el botón de agregar capa", ws.btn_add_layer.isVisible())

    # Agregar una capa por el diálogo. `exec` se reemplaza por uno que acepta:
    # el camino es el mismo que con un clic en «Guardar capa».
    def aceptar(self):
        self._on_accept()
        return QDialog.DialogCode.Accepted if self.result_predicate is not None else 0
    original_exec = LayerEditorDialog.exec
    LayerEditorDialog.exec = aceptar
    try:
        ws._on_add_layer()
        _esperar(ws)
        check("agregar una capa desde el diálogo la guarda",
              len(ws.current.layers) == 1 and len(ws._layer_rows) == 1,
              str(len(ws.current.layers)))

        # Editar una capa apagada no la prende.
        ws._on_toggle_layer(0, False)
        _esperar(ws)
        ws._on_edit_layer(0)
        _esperar(ws)
        check("editar una capa apagada la deja apagada",
              ws.current.ordered_layers()[0].enabled is False)
    finally:
        LayerEditorDialog.exec = original_exec

    # «Duplicar»: el panel tiene que mostrar la copia, que es la que se edita.
    ws._on_duplicate()
    _esperar(ws)
    check("«Duplicar» muestra la copia",
          "(copia)" in ws.lbl_title.text() and "(copia)" in ws.current.name,
          ws.lbl_title.text())

    # Ir a un crate y volver a la misma colección.
    ws._on_freeze()
    abierta = ws.list_collections.currentItem()
    ws.list_crates.setCurrentRow(0)
    app.processEvents()
    check("abrir un crate deja la colección sin seleccionar",
          ws.current is None and ws.list_collections.currentItem() is None)
    ws.list_collections.setCurrentItem(abierta)
    _esperar(ws)
    check("y se puede volver a la misma colección", ws.current is not None)

    # Una pila de tres capas
    col = service.create("Smoke test")
    col = service.add_layer(col, or_(tag("key", "8a"), tag("key", "6a")))
    col = service.add_layer(col, range_("bpm", 120, 132))
    col = service.add_layer(col, tag("energy", "low"), LayerMode.EXCLUDE)
    ws.current = service.get(col.id)
    ws._render_current()
    _esperar(ws)

    check("dibuja una fila por capa", len(ws._layer_rows) == 3, str(len(ws._layer_rows)))
    check("todas las capas son editables",
          all(f.btn_edit.isEnabled() for f in ws._layer_rows))
    check("la grilla se llenó", ws.table.model().rowCount() > 0)

    # Congelar a crate
    antes = ws.list_crates.count()
    ws._on_freeze()
    check("congelar agrega un crate", ws.list_crates.count() == antes + 1)

    # Apagar una capa cambia el resultado
    ws._on_toggle_layer(1, False)
    _esperar(ws)
    check("apagar una capa no la borra", len(ws._layer_rows) == 3)

    # Una capa anidada no se puede editar, pero sí manipular
    col2 = service.create("Anidada")
    col2 = service.add_layer(
        col2, and_(or_(tag("key", "8a"), tag("key", "6a")), range_("bpm", 120, 132))
    )
    ws.current = service.get(col2.id)
    ws._render_current()
    check("una capa anidada se dibuja igual", len(ws._layer_rows) == 1)
    check("pero no se ofrece editarla", not ws._layer_rows[0].btn_edit.isEnabled())
    check("y sí se puede borrar", ws._layer_rows[0].btn_remove.isEnabled())

    # Avisos
    col3 = service.create("Union primera")
    col3 = service.add_layer(col3, tag("key", "8a"), LayerMode.UNION)
    ws.current = service.get(col3.id)
    ws._render_current()
    check("avisa que una unión primera no hace nada",
          "primera capa suma" in ws.lbl_warnings.text(), ws.lbl_warnings.text())

    if shot is not None:
        ws.current = service.get(col.id)
        ws._render_current()
        _esperar(ws)
        ws.show()
        _esperar(ws)
        ws.grab().save(str(shot))
        print(f"\nCaptura: {shot}")

    return ws


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shot", type=Path, default=None,
                        help="Guarda una captura del workspace en esta ruta.")
    args = parser.parse_args()

    # ignore_cleanup_errors: el modo WAL deja archivos -wal/-shm que Windows
    # puede tardar en soltar; no vale la pena hacer fallar una verificación
    # que pasó por no poder borrar un temporal.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        service = build_service(Path(tmp))
        probar_dialogo(service)
        ws = probar_workspace(service, args.shot)
        ws.shutdown()
        del service
        import gc
        gc.collect()

    print()
    if FALLOS:
        print(f"FALLARON {len(FALLOS)}: {FALLOS}")
        return 1
    print("Todo OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
