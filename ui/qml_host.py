"""Phase-1 QML shell — HOME + title bar. Studios stay Qt Widgets.

Menus still fire the existing QAction objects, so shortcuts and logic do not move.
If QML fails to load, callers fall back to the widget Home / FloatTitleBar.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import (
    QObject,
    QPoint,
    Property,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QColor, QPixmap
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QMenu, QWidget

from .title_chrome import TITLE_BAR_H, TITLE_MARGIN, begin_frameless_move

_QML = Path(__file__).resolve().parent / "qml"


class _LogoProvider(QQuickImageProvider):
    def __init__(self, loader: Callable[[str], QPixmap]) -> None:
        super().__init__(QQuickImageProvider.ImageType.Pixmap)
        self._loader = loader

    def requestPixmap(self, id: str, size, requestedSize):  # noqa: ANN001, ARG002
        mode = "light" if str(id).startswith("light") else "dark"
        pm = self._loader(mode)
        if pm.isNull():
            pm = QPixmap(8, 8)
            pm.fill(QColor(0, 0, 0, 0))
        return pm


def _quick(source: Path, bridge: QObject, *, logo: Callable[[str], QPixmap] | None = None) -> QQuickWidget:
    from PySide6.QtCore import Qt

    view = QQuickWidget()
    view.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
    # QML Text copies the app font at load. Lang swap rewrites families in rebase_quick_fonts.
    from .i18n.fonts import ui_font

    view.setFont(ui_font())
    # Opaque fallback — a transparent clear next to QOpenGLWidget reads as a black page.
    view.setClearColor(QColor("#12161c"))
    view.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
    view.engine().rootContext().setContextProperty("bridge", bridge)
    if logo is not None:
        view.engine().addImageProvider("mstnlogo", _LogoProvider(logo))
    view.setSource(QUrl.fromLocalFile(str(source)))
    return view


def _qml_ok(view: QQuickWidget) -> bool:
    return view.status() == QQuickWidget.Status.Ready


def warm_quick(view: QQuickWidget) -> None:
    """Paint one frame now so the first time this page is shown is not a hitch."""
    parent = view.parentWidget()
    if parent is not None and parent.width() > 64 and parent.height() > 64:
        view.resize(parent.size())
    elif view.width() < 64 or view.height() < 64:
        view.resize(1100, 720)
    win = view.quickWindow()
    if win is not None:
        win.setPersistentSceneGraph(True)
        win.setPersistentGraphics(True)
    view.update()
    try:
        view.grabFramebuffer()
    except Exception:
        return


class HomeBridge(QObject):
    changed = Signal()
    studioOpened = Signal(str)

    def __init__(self, on_drop: Callable[[list[Path]], None]) -> None:
        super().__init__()
        self._dark = True
        self._on_drop = on_drop
        self._brand = ""
        self._sub = ""
        self._copy = ""
        self._cta = ""
        self._drop_title = ""
        self._drop_hint = ""
        self._icon_font = ""
        self._cards: list[dict[str, str]] = []

    def _get_dark(self) -> bool:
        return self._dark

    dark = Property(bool, _get_dark, notify=changed)

    def _get_brand(self) -> str:
        return self._brand

    brand = Property(str, _get_brand, notify=changed)

    def _get_sub(self) -> str:
        return self._sub

    sub = Property(str, _get_sub, notify=changed)

    def _get_copy(self) -> str:
        return self._copy

    copy = Property(str, _get_copy, notify=changed)

    def _get_cta(self) -> str:
        return self._cta

    cta = Property(str, _get_cta, notify=changed)

    def _get_drop_title(self) -> str:
        return self._drop_title

    dropTitle = Property(str, _get_drop_title, notify=changed)

    def _get_drop_hint(self) -> str:
        return self._drop_hint

    dropHint = Property(str, _get_drop_hint, notify=changed)

    def _get_icon_font(self) -> str:
        return self._icon_font

    iconFont = Property(str, _get_icon_font, notify=changed)

    def _get_cards(self) -> list:
        return self._cards

    cards = Property("QVariantList", _get_cards, notify=changed)

    def apply_copy(
        self,
        *,
        dark: bool,
        brand: str,
        sub: str,
        copy: str,
        cta: str,
        drop_title: str,
        drop_hint: str,
        icon_font: str,
        cards: list[dict[str, str]],
    ) -> None:
        self._dark = dark
        self._brand = brand
        self._sub = sub
        self._copy = copy
        self._cta = cta
        self._drop_title = drop_title
        self._drop_hint = drop_hint
        self._icon_font = icon_font
        self._cards = cards
        self.changed.emit()

    @Slot(str)
    def openStudio(self, studio_id: str) -> None:
        self.studioOpened.emit(str(studio_id))

    @Slot(list)
    def dropUrls(self, urls: list) -> None:
        paths: list[Path] = []
        for raw in urls:
            text = str(raw)
            if text.startswith("file:"):
                from PySide6.QtCore import QUrl as _Url

                local = _Url(text).toLocalFile()
                if local:
                    paths.append(Path(local))
            elif text:
                paths.append(Path(text))
        if paths:
            self._on_drop(paths)


class QmlHomeHost(QWidget):
    """HOME page backed by Qt Quick. Same hooks the widget page exposed."""

    def __init__(
        self,
        *,
        on_mesh: Callable[[], None],
        on_sounds: Callable[[], None],
        on_engine: Callable[[], None],
        on_assets: Callable[[], None],
        on_texmesh: Callable[[], None],
        on_trainzutil: Callable[[], None],
        on_drop: Callable[[list[Path]], None],
        theme_mode: str = "dark",
        logo: object = None,
        parent: QWidget | None = None,
    ) -> None:
        del logo
        super().__init__(parent)
        self.setObjectName("homePage")
        self._theme = theme_mode if theme_mode in ("dark", "light") else "dark"
        self._handlers = {
            "mesh": on_mesh,
            "sounds": on_sounds,
            "engine": on_engine,
            "assets": on_assets,
            "texmesh": on_texmesh,
            "trainzutil": on_trainzutil,
        }
        self._bridge = HomeBridge(on_drop)
        self._bridge.studioOpened.connect(self._open)
        self._view = _quick(_QML / "HomePage.qml", self._bridge, logo=self._logo)
        from PySide6.QtWidgets import QVBoxLayout

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._view)
        self._ok = _qml_ok(self._view)
        self.retranslate()

    @property
    def ok(self) -> bool:
        return self._ok

    def _logo(self, mode: str) -> QPixmap:
        from .app import _logo_pixmap

        return _logo_pixmap(180, mode=mode)

    def _open(self, studio_id: str) -> None:
        fn = self._handlers.get(studio_id)
        if fn is not None:
            fn()

    def retranslate(self) -> None:
        from .i18n import t
        from .icons import ensure_material_icons, glyph, icon_font

        ensure_material_icons()
        font = icon_font(18)
        specs = (
            ("mesh", "Mesh Studio", "Mesh · FBX · lamps", "layers"),
            ("sounds", "Sounds Studio", "Loop · waveform · export", "graphic_eq"),
            ("engine", "Engine Tuner", "Curves · throttle · sim", "tune"),
            ("assets", "Assets Tools", "CDP · config · KUID", "inventory_2"),
            ("texmesh", "Texture & Mesh Lods", "LODs · maps · bake", "texture"),
            ("trainzutil", "TrainzUtil", "Install · CDP · zip", "upload_file"),
        )
        cards = [
            {
                "studioId": sid,
                "title": t(title),
                "blurb": t(blurb),
                "glyph": glyph(name) or "●",
            }
            for sid, title, blurb, name in specs
        ]
        self._bridge.apply_copy(
            dark=self._theme != "light",
            brand=t("MSTN Trainz Studio"),
            sub=t("Meshes · sounds · engine · assets · maps"),
            copy=t("Copyright MSTN Production"),
            cta=t("Open  →"),
            drop_title=t("Drop files"),
            drop_hint=".trainzmesh  ·  .fbx  ·  .wav  ·  .cdp  ·  .mtzs  ·  …",
            icon_font=font.family() if font is not None else "",
            cards=cards,
        )

    def set_theme(self, mode: str) -> None:
        mode = mode if mode in ("dark", "light") else "dark"
        if mode == self._theme:
            return
        self._theme = mode
        self.retranslate()


class TitleBridge(QObject):
    changed = Signal()
    closeClicked = Signal()
    minimizeClicked = Signal()
    zoomClicked = Signal()

    def __init__(self, host: QmlTitleBar) -> None:
        super().__init__()
        self._host = host
        self._dark = True
        self._title = ""
        self._open = ""
        self._menus: list[dict[str, str]] = []
        self._items: list[dict[str, object]] = []

    def _get_dark(self) -> bool:
        return self._dark

    dark = Property(bool, _get_dark, notify=changed)

    def _get_title(self) -> str:
        return self._title

    windowTitle = Property(str, _get_title, notify=changed)

    def _get_open(self) -> str:
        return self._open

    openKey = Property(str, _get_open, notify=changed)

    def _get_menus(self) -> list:
        return self._menus

    menus = Property("QVariantList", _get_menus, notify=changed)

    def _get_items(self) -> list:
        return self._items

    items = Property("QVariantList", _get_items, notify=changed)

    def push(
        self,
        *,
        dark: bool,
        title: str,
        open_key: str,
        menus: list[dict[str, str]],
        items: list[dict[str, object]],
    ) -> None:
        self._dark = dark
        self._title = title
        self._open = open_key
        self._menus = menus
        self._items = items
        self.changed.emit()

    @Slot()
    def requestClose(self) -> None:
        self.closeClicked.emit()

    @Slot()
    def requestMin(self) -> None:
        self.minimizeClicked.emit()

    @Slot()
    def requestZoom(self) -> None:
        self.zoomClicked.emit()

    @Slot()
    def startMove(self) -> None:
        begin_frameless_move(self._host.window())

    @Slot(str, float, float)
    def toggleMenu(self, key: str, x: float, y: float) -> None:
        self._host.toggle_menu(str(key), int(x), int(y))

    @Slot(str)
    def triggerItem(self, action_id: str) -> None:
        self._host.trigger_item(str(action_id))


class QmlTitleBar(QWidget):
    """Glass title capsule in Qt Quick. Dropdown items trigger live QActions."""

    close_clicked = Signal()
    minimize_clicked = Signal()
    zoom_clicked = Signal()

    def __init__(self, parent: QWidget | None = None, *, mode: str = "dark") -> None:
        super().__init__(parent)
        self.setObjectName("floatTitleBar")
        self.setFixedHeight(TITLE_BAR_H)
        self._theme = mode if mode in ("dark", "light") else "dark"
        self._menus: dict[str, QMenu] = {}
        self._actions: dict[str, QAction] = {}
        self._open_key = ""
        self._title = ""
        self._bridge = TitleBridge(self)
        self._bridge.closeClicked.connect(self.close_clicked.emit)
        self._bridge.minimizeClicked.connect(self.minimize_clicked.emit)
        self._bridge.zoomClicked.connect(self.zoom_clicked.emit)
        self._view = _quick(_QML / "TitleBar.qml", self._bridge)
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QVBoxLayout

        # Title capsule is transparent glass. Software scene graph can blend it;
        # AlwaysStackOnTop would punch a native black hole over the page.
        self._view.setClearColor(QColor(0, 0, 0, 0))
        self._view.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self._view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._view.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._view)
        self._ok = _qml_ok(self._view)
        self._pop = _quick(_QML / "MenuDrop.qml", self._bridge)
        from PySide6.QtCore import Qt

        self._pop.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self._pop.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._pop.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._pop.setClearColor(QColor(0, 0, 0, 0))
        self._pop.hide()
        self._sync()

    @property
    def ok(self) -> bool:
        return self._ok and _qml_ok(self._pop)

    def set_theme(self, mode: str) -> None:
        self._theme = mode if mode in ("dark", "light") else "dark"
        self._sync()

    def set_window_title_text(self, text: str) -> None:
        t = (text or "").strip()
        if "—" in t:
            t = t.split("—", 1)[-1].strip()
        elif "-" in t and len(t) > 28:
            t = t.split("-", 1)[-1].strip()
        self._title = t
        self._sync()

    def bind_menus(self, menus: dict[str, QMenu | None]) -> None:
        self._menus = {k: v for k, v in menus.items() if v is not None}
        self.sync_titles()

    def sync_titles(self) -> None:
        self._sync()

    def reposition(self, host: QWidget | None = None) -> None:
        parent = host or self.parentWidget()
        if parent is None:
            return
        w = max(320, parent.width() - TITLE_MARGIN * 2)
        self.setFixedWidth(w)
        self.setFixedHeight(TITLE_BAR_H)
        self.move(TITLE_MARGIN, TITLE_MARGIN)
        self.show()
        self.raise_()

    def toggle_menu(self, key: str, x: int, y: int) -> None:
        if self._open_key == key and self._pop.isVisible():
            self._close_menu()
            return
        menu = self._menus.get(key)
        if menu is None:
            return
        self._open_key = key
        self._fill_items(menu)
        self._sync()
        rows = self._bridge._items
        h = 12 + sum(9 if row.get("sep") else 34 for row in rows)
        h = max(40, min(h, 520))
        self._pop.setFixedSize(280, h)
        self._pop.move(QPoint(x, y + 4))
        self._pop.show()
        self._pop.raise_()

    def trigger_item(self, action_id: str) -> None:
        act = self._actions.get(action_id)
        self._close_menu()
        if act is not None and act.isEnabled():
            act.trigger()

    def _close_menu(self) -> None:
        self._open_key = ""
        self._pop.hide()
        self._sync()

    def _fill_items(self, menu: QMenu) -> None:
        self._actions.clear()
        rows: list[dict[str, object]] = []
        for act in menu.actions():
            if act.isSeparator():
                rows.append(
                    {
                        "actId": "",
                        "label": "",
                        "shortcut": "",
                        "sep": True,
                        "checked": False,
                        "alive": False,
                    }
                )
                continue
            key = str(id(act))
            self._actions[key] = act
            rows.append(
                {
                        "actId": key,
                        "label": act.text().replace("&", ""),
                        "shortcut": act.shortcut().toString(),
                        "sep": False,
                        "checked": bool(act.isCheckable() and act.isChecked()),
                        "alive": bool(act.isEnabled()),
                }
            )
        self._bridge._items = rows

    def _sync(self) -> None:
        keys = ("File", "Edit", "View", "Tools", "Theme", "Lang")
        menus = []
        for key in keys:
            menu = self._menus.get(key)
            label = menu.title().replace("&", "") if menu is not None and menu.title() else key
            menus.append({"key": key, "label": label})
        self._bridge.push(
            dark=self._theme != "light",
            title=self._title,
            open_key=self._open_key,
            menus=menus,
            items=list(self._bridge._items),
        )


def build_qml_home(**kwargs: object) -> QWidget:
    """QML home, or the painted widget page if Quick fails to load."""
    host = QmlHomeHost(**kwargs)  # type: ignore[arg-type]
    if host.ok:
        return host
    host.deleteLater()
    from .home import build_home_page

    return build_home_page(**kwargs)  # type: ignore[arg-type]


def make_title_bar(parent: QWidget, *, mode: str) -> QWidget:
    bar = QmlTitleBar(parent, mode=mode)
    if bar.ok:
        return bar
    bar.deleteLater()
    from .title_chrome import FloatTitleBar

    return FloatTitleBar(parent, mode=mode)
