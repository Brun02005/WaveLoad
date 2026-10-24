"""
ui/controllers/track_actions.py
===============================
El menú de clic derecho sobre pistas y lo que hace cada acción.

Es un solo lugar para todas las tablas de pistas (Librería, Colecciones): el
menú es el mismo en las dos y las decisiones (qué se quita, qué va a la
Papelera) viven en ``LibraryService``. Acá sólo se pregunta, se llama y se
avisa a las pantallas que cambió algo.
"""

import logging
import subprocess
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QFileDialog, QMenu, QMessageBox, QWidget

from domain.tags import NS_CONTEXT, NS_STATUS, Tag
from ui.dialogs.tag_editor_dialog import TagEditorDialog
from ui.mappers.tag_labels import EDITABLE_NAMESPACES, NAMESPACE_TITLES, SUGGESTIONS, tag_label

from services.library_service import SUPPORTED_AUDIO
from ui.theme.colors import PRIMARY_RED, TEXT_SECONDARY
from ui.theme.icons import Icons, icon

logger = logging.getLogger(__name__)


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


class TrackActions(QObject):
    """Acciones sobre una selección de pistas (dicts de presentación)."""

    # ids quitados de la librería
    tracks_removed = Signal(list)
    # ids de pistas cuyas etiquetas cambiaron
    tags_changed = Signal(list)
    # id del crate que cambió (se crearon o agregaron pistas)
    crates_changed = Signal(int)
    # id de una pista cuyo archivo se ubicó en otra ruta
    track_relocated = Signal(str)

    def __init__(self, library_service, repository, analysis_coordinator,
                 audio_player=None, parent: QWidget | None = None, tagging_service=None,
                 collection_service=None):
        super().__init__(parent)
        self.library = library_service
        self.repository = repository
        self.analysis = analysis_coordinator
        self.audio = audio_player
        self.tagging = tagging_service
        self.collections = collection_service
        # Por tabla: acciones propias de esa pantalla y qué hace Supr ahí.
        self._extras = {}
        self._on_delete = {}
        self._parent = parent

    def attach(self, table, extra_actions=None, on_delete=None) -> None:
        """Conecta una ``WLTrackTable``: clic derecho, Supr y Shift+Supr.

        ``extra_actions(tracks)`` devuelve ``[(icono, texto, callback)]`` que van
        primero en el menú (ej. "Quitar del crate" en un crate abierto).
        ``on_delete(tracks, shift)`` reemplaza lo que hace Supr en esa tabla;
        si devuelve False, Supr sigue con el comportamiento normal.
        """
        self._extras[table] = extra_actions
        self._on_delete[table] = on_delete
        table.context_menu_requested.connect(
            lambda tracks, pos, t=table: self.show_menu(tracks, pos, t)
        )
        table.remove_requested.connect(
            lambda tracks, shift, t=table: self._delete_from(t, tracks, shift)
        )
        # Doble clic sobre una pista: escucharla.
        table.doubleClicked.connect(lambda index: self.play(index.data(Qt.UserRole) or {}))

    # --- menú ----------------------------------------------------------------

    def _delete_from(self, table, tracks: list, shift: bool) -> None:
        propio = self._on_delete.get(table)
        if propio is not None and propio(tracks, shift) is not False:
            return
        self.remove(tracks, shift)

    def show_menu(self, tracks: list, global_pos: QPoint, table=None) -> None:
        menu = QMenu(self._parent)
        n = len(tracks)
        extras = self._extras.get(table)
        propias = extras(tracks) if extras else []
        for icono, texto, accion in propias:
            menu.addAction(icon(icono, TEXT_SECONDARY, 16), texto, accion)
        if propias:
            menu.addSeparator()
        presentes = [t for t in tracks if not t.get("missing")]
        una = tracks[0] if n == 1 else None

        if una and not una.get("missing"):
            menu.addAction(icon(Icons.PLAY, TEXT_SECONDARY, 16), "Escuchar",
                           lambda: self.play(una))
            menu.addAction(icon(Icons.FOLDER, TEXT_SECONDARY, 16), "Mostrar en el Explorador",
                           lambda: self.reveal(una))
        if una and una.get("missing"):
            menu.addAction(icon(Icons.SEARCH, TEXT_SECONDARY, 16), "Ubicar archivo…",
                           lambda: self.relocate(una))
        if presentes:
            texto = "Volver a analizar" if len(presentes) == 1 else \
                f"Volver a analizar {len(presentes)} pistas"
            menu.addAction(icon(Icons.REFRESH, TEXT_SECONDARY, 16), texto,
                           lambda: self.reanalyze(presentes))
        menu.addAction(icon(Icons.DUPLICATE, TEXT_SECONDARY, 16),
                       "Copiar artista y título", lambda: self.copy_names(tracks))
        if una and una.get("path"):
            menu.addAction(icon(Icons.FILE, TEXT_SECONDARY, 16), "Copiar ruta del archivo",
                           lambda: QGuiApplication.clipboard().setText(una["path"]))

        if self.tagging is not None:
            menu.addSeparator()
            menu.addAction(icon(Icons.EDIT, TEXT_SECONDARY, 16), "Etiquetas…",
                           lambda: self.edit_tags(tracks))
            self._add_quick_tags(menu, tracks, NS_CONTEXT)
            self._add_quick_tags(menu, tracks, NS_STATUS)
        if self.collections is not None:
            self._add_crate_menu(menu, tracks)

        menu.addSeparator()
        cuantas = "" if n == 1 else f" {n} pistas"
        menu.addAction(icon(Icons.CLOSE, TEXT_SECONDARY, 16),
                       f"Quitar{cuantas} de la librería\tSupr",
                       lambda: self.remove(tracks, False))
        if presentes:
            menu.addAction(icon(Icons.CLEAR, PRIMARY_RED, 16),
                           f"Quitar{cuantas} y mandar a la Papelera\tShift+Supr",
                           lambda: self.remove(tracks, True))
        menu.exec(global_pos)

    def _add_quick_tags(self, menu: QMenu, tracks: list, namespace: str) -> None:
        """Submenú de un clic para un eje corto (momento del set, estado).

        Tildado si todas las pistas lo tienen; clic lo pone en todas, o lo saca
        de todas si ya estaba en todas.
        """
        sub = menu.addMenu(NAMESPACE_TITLES[namespace])
        for valor in SUGGESTIONS[namespace]:
            con = sum(1 for t in tracks if valor in (t.get("tags") or {}).get(namespace, []))
            texto = tag_label(namespace, valor)
            if 0 < con < len(tracks):
                texto += f"  ({con} de {len(tracks)})"
            accion = sub.addAction(texto.replace("&", "&&"))
            accion.setCheckable(True)
            accion.setChecked(con == len(tracks))
            tag = Tag(namespace, valor)
            todas = con == len(tracks)
            accion.triggered.connect(
                lambda _=False, tag=tag, todas=todas: self.apply_tags(
                    tracks, remove=[tag] if todas else [], add=[] if todas else [tag]
                )
            )

    # --- crates -------------------------------------------------------------------

    def _add_crate_menu(self, menu: QMenu, tracks: list) -> None:
        sub = menu.addMenu(icon(Icons.CRATE, TEXT_SECONDARY, 16), "Agregar a crate")
        ids = [t["id"] for t in tracks]
        try:
            crates = self.collections.list_crates()
        except Exception as exc:  # noqa: BLE001
            logger.error("No se pudieron listar los crates: %s", exc)
            crates = []
        for crate in crates:
            ya = sum(1 for i in ids if i in crate.track_ids)
            texto = crate.name.replace("&", "&&")
            if ya == len(ids):
                texto += "  (ya están)" if len(ids) > 1 else "  (ya está)"
            elif ya:
                texto += f"  ({ya} ya están)"
            accion = sub.addAction(texto)
            accion.setEnabled(ya < len(ids))
            accion.triggered.connect(lambda _=False, c=crate.id: self.add_to_crate(c, ids))
        if crates:
            sub.addSeparator()
        sub.addAction(icon(Icons.PLUS, TEXT_SECONDARY, 16), "Nuevo crate con estas pistas…",
                      lambda: self.new_crate_with(ids))

    def add_to_crate(self, crate_id: int, ids: list) -> None:
        try:
            self.collections.add_to_crate(crate_id, ids)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self._parent, "Agregar a crate", str(exc))
            return
        self.crates_changed.emit(crate_id)

    def new_crate_with(self, ids: list) -> None:
        from PySide6.QtWidgets import QInputDialog  # noqa: PLC0415
        nombre, ok = QInputDialog.getText(self._parent, "Nuevo crate", "Nombre del crate:",
                                          text="Nuevo crate")
        if not ok:
            return
        try:
            crate = self.collections.create_crate(nombre, ids)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self._parent, "Nuevo crate", str(exc))
            return
        self.crates_changed.emit(crate.id)

    # --- etiquetas ---------------------------------------------------------------

    def edit_tags(self, tracks: list) -> None:
        ids = [t["id"] for t in tracks]
        actuales = self.tagging.manual_tags(ids)
        vocabulario = {
            ns: [valor for valor, _uso in self.tagging.repo.usage_by_namespace(ns)]
            for ns in EDITABLE_NAMESPACES
        }
        dialogo = TagEditorDialog(tracks, actuales, vocabulario, parent=self._parent)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        self.apply_tags(tracks, add=dialogo.result_add, remove=dialogo.result_remove)

    def apply_tags(self, tracks: list, add=(), remove=()) -> None:
        if not add and not remove:
            return
        ids = [t["id"] for t in tracks]
        try:
            self.tagging.edit_manual(ids, add=add, remove=remove)
        except Exception as exc:  # noqa: BLE001 — se muestra, no se traga
            logger.error("No se pudieron guardar las etiquetas: %s", exc)
            QMessageBox.critical(self._parent, "Etiquetas", f"No se pudieron guardar.\n\n{exc}")
            return
        self.tags_changed.emit(ids)

    # --- acciones --------------------------------------------------------------

    def play(self, track: dict) -> None:
        if self.audio and track.get("path") and not track.get("missing"):
            artista = track.get("artist") if track.get("artist") not in (None, "—") else ""
            self.audio.toggle_play_pause_for(track["path"], True, track.get("title", ""), artista)

    def reveal(self, track: dict) -> None:
        # El Explorador quiere /select,"ruta" como un solo argumento con las
        # comillas adentro; con la lista de argumentos de subprocess no lo toma.
        subprocess.Popen(f'explorer /select,"{Path(track["path"])}"')

    def copy_names(self, tracks: list) -> None:
        lineas = []
        for t in tracks:
            artista = t.get("artist") if t.get("artist") not in (None, "", "—") else ""
            lineas.append(f"{artista} - {t.get('title', '')}" if artista else t.get("title", ""))
        QGuiApplication.clipboard().setText("\n".join(lineas))

    def reanalyze(self, tracks: list) -> None:
        for t in tracks:
            if t.get("path"):
                self.analysis.analyze_track(t["id"], t["path"])

    def relocate(self, track: dict) -> None:
        filtro = "Audio (" + " ".join(f"*{ext}" for ext in sorted(SUPPORTED_AUDIO)) + ")"
        nombre = Path(track.get("path") or "").name
        ruta, _ = QFileDialog.getOpenFileName(
            self._parent, f"Ubicar «{track.get('title', nombre)}»", nombre, filtro
        )
        if not ruta:
            return
        try:
            self.library.relocate(track["id"], ruta)
        except ValueError as exc:
            QMessageBox.warning(self._parent, "No se pudo ubicar el archivo", str(exc))
            return
        self.track_relocated.emit(track["id"])
        # Si nunca se pudo analizar (el archivo faltaba), es el momento.
        if track.get("bpm") in (None, "", "—"):
            self.analysis.analyze_track(track["id"], ruta)

    def remove(self, tracks: list, delete_files: bool) -> None:
        n = len(tracks)
        if delete_files:
            con_archivo = sum(1 for t in tracks if not t.get("missing"))
            titulo = "Mandar a la Papelera"
            texto = (
                f"¿Quitar {_plural(n, 'pista', 'pistas')} de la librería y mandar "
                f"{_plural(con_archivo, 'archivo', 'archivos')} a la Papelera de reciclaje?"
            )
            detalle = ("Se pierden su análisis, etiquetas y lugar en los crates. "
                       "Los archivos se pueden restaurar desde la Papelera mientras no la vacíes.")
            boton = "Mandar a la Papelera"
        else:
            titulo = "Quitar de la librería"
            texto = f"¿Quitar {_plural(n, 'pista', 'pistas')} de la librería?"
            detalle = ("Los archivos no se tocan: siguen en su carpeta. Se pierden su "
                       "análisis, etiquetas y lugar en los crates.")
            boton = "Quitar"

        caja = QMessageBox(self._parent)
        caja.setWindowTitle(titulo)
        caja.setIcon(QMessageBox.Warning if delete_files else QMessageBox.Question)
        caja.setText(texto)
        caja.setInformativeText(detalle)
        confirmar = caja.addButton(boton, QMessageBox.DestructiveRole)
        caja.addButton("Cancelar", QMessageBox.RejectRole)
        caja.setDefaultButton(QMessageBox.Cancel)
        caja.exec()
        if caja.clickedButton() is not confirmar:
            return

        # Un archivo que se está reproduciendo está abierto: Windows no deja
        # moverlo a la Papelera.
        if delete_files and self.audio is not None:
            rutas = {t.get("path") for t in tracks}
            if self.audio.current_key() in rutas:
                self.audio.stop()

        dominio = self.repository.get_by_ids([t["id"] for t in tracks])
        try:
            reporte = self.library.remove_tracks(dominio, delete_files=delete_files)
        except Exception as exc:  # noqa: BLE001 — se muestra, no se traga
            logger.error("No se pudieron quitar las pistas: %s", exc)
            QMessageBox.critical(self._parent, titulo, f"No se pudieron quitar las pistas.\n\n{exc}")
            return

        conservados = {p for p, _ in reporte.kept}
        quitados = [t["id"] for t in tracks if t.get("path") not in conservados]
        self.tracks_removed.emit(quitados)

        if reporte.kept:
            lista = "\n".join(f"• {Path(p).name}: {motivo}" for p, motivo in reporte.kept[:8])
            QMessageBox.warning(
                self._parent, titulo,
                f"{_plural(len(reporte.kept), 'archivo no se pudo', 'archivos no se pudieron')} "
                "mandar a la Papelera, así que esas pistas siguen en la librería:\n\n" + lista,
            )
