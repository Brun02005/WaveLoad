"""
ui/theme/styles.py
==================
WaveLoad 5 Design System — Centralized QSS Stylesheet Generator

Produces the complete application-level stylesheet from design tokens
(colors, typography, spacing). This replaces all inline setStyleSheet()
calls scattered across widget files.

Usage:
    from ui.theme.styles import build_application_stylesheet
    app.setStyleSheet(build_application_stylesheet())

    # Or for component-level styles:
    from ui.theme.styles import component_styles
    widget.setStyleSheet(component_styles.card())
"""

from ui.theme.colors import (
    ACCENT, ACCENT_HOVER, ACCENT_MUTED, ACCENT_SOFT, ACCENT_LINE,
    DANGER_SOFT, DANGER_LINE,
    PRIMARY_GREEN, PRIMARY_GREEN_HOVER, PRIMARY_GREEN_MUTED,
    PRIMARY_ORANGE, PRIMARY_RED, PRIMARY_RED_HOVER,
    SURFACE_BASE, SURFACE_1, SURFACE_2, SURFACE_3, SURFACE_4, SURFACE_5,
    BORDER_SUBTLE, BORDER_DEFAULT, BORDER_STRONG, BORDER_FOCUS,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_INVERSE,
    SCROLLBAR_TRACK, SCROLLBAR_HANDLE, SCROLLBAR_HANDLE_HOVER,
    STATUS_VALID, STATUS_DUPLICATE, STATUS_ERROR, STATUS_PENDING,
    STATUS_INFO,
)
from ui.theme.typography import (
    FONT_STACK_PRIMARY, FONT_STACK_MONO,
    FONT_SIZE_XS, FONT_SIZE_SM, FONT_SIZE_BASE, FONT_SIZE_MD,
    FONT_SIZE_LG, FONT_SIZE_XL, FONT_SIZE_XXL,
)
from ui.theme.spacing import (
    CARD_BORDER_RADIUS, BUTTON_BORDER_RADIUS, INPUT_BORDER_RADIUS,
    PROGRESS_BAR_HEIGHT,
)


def build_application_stylesheet() -> str:
    """
    Generate the complete application-level QSS stylesheet.

    Cubre también los controles sin objectName (QLineEdit, QComboBox,
    QListWidget, QSpinBox, QCheckBox…): un control sin regla cae al estilo
    nativo de Windows, que es claro, y queda como una mancha blanca en una
    interfaz oscura.
    """
    from ui.theme.assets import qss_icon  # noqa: PLC0415

    chevron = qss_icon("chevron-down", TEXT_SECONDARY)
    chevron_up = qss_icon("chevron-up", TEXT_SECONDARY)
    check = qss_icon("check", TEXT_INVERSE, 3.0)

    return f"""
        /* ================================================================
         * BASE
         * ================================================================ */
        QMainWindow, QDialog {{
            background-color: {SURFACE_2};
        }}
        QWidget {{
            color: {TEXT_PRIMARY};
            font-family: {FONT_STACK_PRIMARY};
            font-size: {FONT_SIZE_BASE}px;
        }}
        QLabel {{
            background: transparent;
        }}
        QToolTip {{
            background-color: {SURFACE_5};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_STRONG};
            padding: 6px 9px;
            font-size: {FONT_SIZE_SM + 1}px;
            border-radius: 6px;
        }}
        QSplitter::handle {{
            background-color: {BORDER_SUBTLE};
        }}
        QSplitter::handle:hover {{
            background-color: {BORDER_STRONG};
        }}

        /* ================================================================
         * SCROLL
         * ================================================================ */
        QScrollArea {{
            border: none;
            background: transparent;
        }}
        QScrollArea > QWidget > QWidget {{
            background: transparent;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 2px;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
            background: {SCROLLBAR_HANDLE};
            border-radius: 3px;
        }}
        QScrollBar::handle:vertical {{ min-height: 32px; }}
        QScrollBar::handle:horizontal {{ min-width: 32px; }}
        QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
            background: {SCROLLBAR_HANDLE_HOVER};
        }}
        QScrollBar::add-line, QScrollBar::sub-line,
        QScrollBar::add-page, QScrollBar::sub-page {{
            background: none;
            border: none;
            width: 0px;
            height: 0px;
        }}

        /* ================================================================
         * SHELL: TOOLBAR, SIDEBAR, CONTENEDORES
         * ================================================================ */
        QWidget#wl_toolbar {{
            background-color: {SURFACE_1};
            border-bottom: 1px solid {BORDER_SUBTLE};
        }}
        QLabel#wl_toolbarTitle {{
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_MD + 1}px;
            font-weight: 600;
        }}
        QWidget#wl_sidebar {{
            background-color: {SURFACE_1};
            border-right: 1px solid {BORDER_SUBTLE};
        }}
        QLabel#wl_logoLabel {{
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_LG + 1}px;
            font-weight: 700;
        }}
        QLabel#wl_navSection {{
            color: {TEXT_MUTED};
            font-size: {FONT_SIZE_XS + 1}px;
            font-weight: 600;
            padding: 0px 12px;
        }}
        QPushButton#wl_navBtn, QPushButton#wl_navBtnActive {{
            background-color: transparent;
            border: none;
            border-radius: 8px;
            padding: 0px 12px;
            font-size: {FONT_SIZE_BASE + 1}px;
            font-weight: 500;
            text-align: left;
            color: {TEXT_SECONDARY};
        }}
        QPushButton#wl_navBtn:hover {{
            background-color: {SURFACE_3};
            color: {TEXT_PRIMARY};
        }}
        QPushButton#wl_navBtnActive {{
            background-color: {ACCENT_SOFT};
            color: {TEXT_PRIMARY};
            font-weight: 600;
        }}
        QWidget#wl_sidebarFolderBox {{
            background-color: {SURFACE_2};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 10px;
        }}
        QLabel#wl_sfTitle {{
            font-size: {FONT_SIZE_XS + 1}px;
            font-weight: 600;
            color: {TEXT_MUTED};
        }}
        QLabel#wl_sfPath {{
            font-size: {FONT_SIZE_SM + 1}px;
            color: {TEXT_SECONDARY};
        }}
        QPushButton#wl_sfBtn {{
            background-color: transparent;
            border: 1px solid {BORDER_DEFAULT};
            border-radius: 6px;
            padding: 4px 8px;
            font-size: {FONT_SIZE_SM + 1}px;
            font-weight: 500;
            color: {TEXT_SECONDARY};
        }}
        QPushButton#wl_sfBtn:hover {{
            background-color: {SURFACE_3};
            color: {TEXT_PRIMARY};
        }}
        QFrame#wl_mainContainer {{
            background-color: {SURFACE_2};
        }}
        QWidget#wl_contextPanel {{
            background-color: {SURFACE_1};
            border-left: 1px solid {BORDER_SUBTLE};
        }}
        QWidget#wl_bottomWorkspace {{
            background-color: {SURFACE_1};
            border-top: 1px solid {BORDER_SUBTLE};
        }}

        /* ================================================================
         * BOTONES
         * ================================================================ */
        QPushButton {{
            background-color: {SURFACE_3};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {BUTTON_BORDER_RADIUS}px;
            padding: 6px 12px;
            color: {TEXT_PRIMARY};
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {SURFACE_4};
            border-color: {BORDER_STRONG};
        }}
        QPushButton:disabled {{
            color: {TEXT_MUTED};
            background-color: {SURFACE_2};
            border-color: {BORDER_SUBTLE};
        }}
        QPushButton#wl_primaryBtn {{
            background-color: {ACCENT};
            border: none;
            color: {TEXT_INVERSE};
            font-weight: 600;
            font-size: {FONT_SIZE_BASE + 1}px;
            padding: 0px 18px;
        }}
        QPushButton#wl_primaryBtn:hover {{
            background-color: {ACCENT_HOVER};
        }}
        QPushButton#wl_primaryBtn:disabled {{
            background-color: {SURFACE_3};
            color: {TEXT_MUTED};
        }}
        QPushButton#wl_secondaryBtn {{
            background-color: {SURFACE_3};
            border: 1px solid {BORDER_DEFAULT};
            padding: 0px 12px;
            font-weight: 500;
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_BASE}px;
            min-height: 30px;
        }}
        QPushButton#wl_secondaryBtn:hover {{
            background-color: {SURFACE_4};
            border-color: {BORDER_STRONG};
        }}
        QPushButton#wl_secondaryBtn:disabled {{
            background-color: transparent;
            border-color: {BORDER_SUBTLE};
            color: {TEXT_MUTED};
        }}
        QPushButton#wl_dangerBtn {{
            background-color: transparent;
            border: 1px solid {DANGER_LINE};
            padding: 0px 12px;
            min-height: 30px;
            font-weight: 500;
            color: {PRIMARY_RED};
        }}
        QPushButton#wl_dangerBtn:hover {{
            background-color: {DANGER_SOFT};
            border-color: {PRIMARY_RED};
        }}
        QPushButton#wl_dangerBtn:disabled {{
            border-color: {BORDER_SUBTLE};
            color: {TEXT_MUTED};
        }}
        QPushButton#wl_toolbarBtn {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 6px;
            padding: 0px;
        }}
        QPushButton#wl_toolbarBtn:hover {{
            background-color: {SURFACE_4};
        }}
        QPushButton#wl_toolbarBtn:checked {{
            background-color: {ACCENT_SOFT};
        }}
        QPushButton#wl_toolbarBtn:disabled {{
            background-color: transparent;
        }}
        QPushButton#wl_ghostBtn {{
            background-color: transparent;
            border: none;
            padding: 0px 10px;
            min-height: 30px;
            color: {TEXT_SECONDARY};
            font-weight: 500;
        }}
        QPushButton#wl_ghostBtn:hover {{
            background-color: {SURFACE_3};
            color: {TEXT_PRIMARY};
        }}

        /* ================================================================
         * CAMPOS DE TEXTO
         * ================================================================ */
        QLineEdit, QPlainTextEdit, QTextEdit {{
            background-color: {SURFACE_1};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {INPUT_BORDER_RADIUS}px;
            padding: 6px 10px;
            color: {TEXT_PRIMARY};
            selection-background-color: {ACCENT_MUTED};
            selection-color: {TEXT_PRIMARY};
        }}
        QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover {{
            border-color: {BORDER_STRONG};
        }}
        QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
            border-color: {ACCENT_LINE};
        }}
        QLineEdit:disabled {{
            color: {TEXT_MUTED};
            background-color: {SURFACE_2};
        }}
        QLineEdit#wl_searchInput {{
            background-color: {SURFACE_2};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 8px;
            padding: 0px 10px 0px 4px;
        }}
        QLineEdit#wl_searchInput:hover {{
            border-color: {BORDER_DEFAULT};
        }}
        QLineEdit#wl_searchInput:focus {{
            border-color: {ACCENT_LINE};
            background-color: {SURFACE_1};
        }}
        QPlainTextEdit#wl_inputBox {{
            background-color: {SURFACE_1};
            border-radius: 10px;
            padding: 12px 14px;
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_BASE}px;
        }}
        QPlainTextEdit#wl_logBox {{
            background-color: {SURFACE_BASE};
            border: 1px solid {BORDER_SUBTLE};
            padding: 8px;
            color: {TEXT_SECONDARY};
            font-family: {FONT_STACK_MONO};
            font-size: {FONT_SIZE_SM + 1}px;
        }}

        /* ================================================================
         * COMBO, SPIN
         * ================================================================ */
        QComboBox {{
            background-color: {SURFACE_3};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {INPUT_BORDER_RADIUS}px;
            padding: 5px 30px 5px 10px;
            min-height: 20px;
            color: {TEXT_PRIMARY};
        }}
        QComboBox:hover {{
            border-color: {BORDER_STRONG};
        }}
        QComboBox:focus {{
            border-color: {ACCENT_LINE};
        }}
        QComboBox:editable {{
            background-color: {SURFACE_1};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: center right;
            width: 26px;
            border: none;
        }}
        QComboBox::down-arrow {{
            image: url({chevron});
            width: 14px;
            height: 14px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {SURFACE_3};
            border: 1px solid {BORDER_STRONG};
            border-radius: 8px;
            padding: 4px;
            outline: none;
            selection-background-color: {SURFACE_5};
            selection-color: {TEXT_PRIMARY};
        }}
        QComboBox QAbstractItemView::item {{
            min-height: 26px;
            padding: 0px 8px;
            border-radius: 5px;
        }}
        QSpinBox, QDoubleSpinBox {{
            background-color: {SURFACE_1};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {INPUT_BORDER_RADIUS}px;
            padding: 5px 24px 5px 10px;
            min-height: 20px;
            color: {TEXT_PRIMARY};
        }}
        QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {ACCENT_LINE};
        }}
        QSpinBox::up-button, QDoubleSpinBox::up-button,
        QSpinBox::down-button, QDoubleSpinBox::down-button {{
            subcontrol-origin: border;
            width: 20px;
            border: none;
            background: transparent;
        }}
        QSpinBox::up-button, QDoubleSpinBox::up-button {{
            subcontrol-position: top right;
        }}
        QSpinBox::down-button, QDoubleSpinBox::down-button {{
            subcontrol-position: bottom right;
        }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
            image: url({chevron_up});
            width: 10px;
            height: 10px;
        }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
            image: url({chevron});
            width: 10px;
            height: 10px;
        }}

        /* ================================================================
         * CHECKBOX, RADIO, SLIDER
         * ================================================================ */
        QCheckBox, QRadioButton {{
            color: {TEXT_PRIMARY};
            spacing: 9px;
            background: transparent;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 4px;
            border: 1px solid {BORDER_STRONG};
            background-color: {SURFACE_1};
        }}
        QCheckBox::indicator:hover {{
            border-color: {TEXT_MUTED};
        }}
        QCheckBox::indicator:checked {{
            background-color: {ACCENT};
            border-color: {ACCENT};
            image: url({check});
        }}
        QRadioButton::indicator {{
            width: 14px;
            height: 14px;
            border-radius: 8px;
            border: 1px solid {BORDER_STRONG};
            background-color: {SURFACE_1};
        }}
        QRadioButton::indicator:checked {{
            border: 4px solid {ACCENT};
            background-color: {TEXT_INVERSE};
        }}
        QSlider::groove:horizontal {{
            height: 4px;
            background: {SURFACE_4};
            border-radius: 2px;
        }}
        QSlider::sub-page:horizontal {{
            background: {ACCENT};
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {TEXT_PRIMARY};
            width: 14px;
            height: 14px;
            margin: -5px 0px;
            border-radius: 7px;
        }}

        /* ================================================================
         * LISTAS, TABLAS
         * ================================================================ */
        QListWidget, QListView, QTreeView {{
            background-color: transparent;
            border: none;
            outline: none;
        }}
        QListWidget::item {{
            color: {TEXT_SECONDARY};
            padding: 7px 10px;
            border-radius: 6px;
            margin: 1px 0px;
        }}
        QListWidget::item:hover {{
            background-color: {SURFACE_3};
            color: {TEXT_PRIMARY};
        }}
        QListWidget::item:selected {{
            background-color: {SURFACE_4};
            color: {TEXT_PRIMARY};
        }}
        QTableView#wl_trackTable {{
            background-color: {SURFACE_2};
            alternate-background-color: {SURFACE_2};
            border: none;
            gridline-color: transparent;
            outline: none;
            selection-background-color: transparent;
        }}
        QTableView#wl_trackTable::item {{
            border: none;
            padding: 0px;
            color: {TEXT_PRIMARY};
        }}
        QHeaderView {{
            background-color: {SURFACE_2};
            border: none;
        }}
        QHeaderView::section {{
            background-color: {SURFACE_2};
            color: {TEXT_MUTED};
            border: none;
            border-bottom: 1px solid {BORDER_SUBTLE};
            padding: 8px 10px;
            font-size: {FONT_SIZE_SM}px;
            font-weight: 600;
        }}
        QHeaderView::section:hover {{
            color: {TEXT_SECONDARY};
        }}
        QHeaderView::down-arrow, QHeaderView::up-arrow {{
            width: 0px;
            height: 0px;
        }}

        /* ================================================================
         * MENÚS Y DIÁLOGOS
         * ================================================================ */
        QMenu {{
            background-color: {SURFACE_3};
            border: 1px solid {BORDER_STRONG};
            border-radius: 8px;
            padding: 4px;
        }}
        QMenu::item {{
            padding: 6px 14px;
            border-radius: 5px;
            color: {TEXT_PRIMARY};
        }}
        QMenu::item:selected {{
            background-color: {SURFACE_5};
        }}
        QMenu::separator {{
            height: 1px;
            background: {BORDER_DEFAULT};
            margin: 4px 6px;
        }}
        QMessageBox QPushButton {{
            min-width: 76px;
            min-height: 28px;
        }}

        /* ================================================================
         * PROGRESO
         * ================================================================ */
        QProgressBar {{
            background-color: {SURFACE_4};
            border: none;
            border-radius: {PROGRESS_BAR_HEIGHT // 2}px;
            text-align: center;
            color: transparent;
        }}
        QProgressBar::chunk {{
            background-color: {ACCENT};
            border-radius: {PROGRESS_BAR_HEIGHT // 2}px;
        }}

        /* ================================================================
         * ETIQUETAS CON ROL
         * ================================================================ */
        QLabel#wl_title {{
            font-size: {FONT_SIZE_LG + 2}px;
            font-weight: 600;
            color: {TEXT_PRIMARY};
        }}
        QLabel#wl_subtitle {{
            color: {TEXT_MUTED};
            font-size: {FONT_SIZE_SM + 1}px;
        }}
        QLabel#wl_counterLabel {{
            color: {TEXT_MUTED};
            font-size: {FONT_SIZE_SM + 1}px;
        }}
        QLabel#wl_sectionTitle {{
            color: {TEXT_SECONDARY};
            font-size: {FONT_SIZE_SM + 1}px;
            font-weight: 600;
        }}
        QLabel#wl_caption {{
            color: {TEXT_MUTED};
            font-size: {FONT_SIZE_SM + 1}px;
        }}

        /* ================================================================
         * PANELES
         * ================================================================ */
        QWidget#wl_globalProgressBox {{
            background-color: {SURFACE_3};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {CARD_BORDER_RADIUS}px;
        }}
        QLabel#wl_globalProgressTitle {{
            color: {TEXT_PRIMARY};
            font-weight: 600;
        }}
        QLabel#wl_globalStatsLabel {{
            color: {TEXT_SECONDARY};
            font-size: {FONT_SIZE_SM + 1}px;
            font-weight: 600;
        }}
        QPushButton#wl_collapsibleHeader {{
            background-color: transparent;
            border: 1px solid {BORDER_SUBTLE};
            border-radius: {BUTTON_BORDER_RADIUS}px;
            text-align: left;
        }}
        QPushButton#wl_collapsibleHeader:hover {{
            background-color: {SURFACE_3};
        }}
        QLabel#wl_headerText {{
            color: {TEXT_SECONDARY};
            font-size: {FONT_SIZE_SM + 1}px;
            font-weight: 500;
        }}
        QLabel#wl_contextTitle {{
            font-size: {FONT_SIZE_LG}px;
            font-weight: 600;
            color: {TEXT_PRIMARY};
        }}
        QLabel#wl_contextSubtitle {{
            font-size: {FONT_SIZE_SM + 1}px;
            color: {TEXT_SECONDARY};
        }}
        QLabel#wl_infoLabel {{
            font-size: {FONT_SIZE_SM}px;
            color: {TEXT_MUTED};
            font-weight: 500;
        }}
        QLabel#wl_infoValue {{
            font-size: {FONT_SIZE_BASE}px;
            color: {TEXT_PRIMARY};
        }}

        /* ================================================================
         * INDICADORES
         * ================================================================ */
        QWidget#wl_statusValid {{
            background-color: {STATUS_VALID};
            border-radius: 4px;
        }}
        QWidget#wl_statusDuplicate {{
            background-color: {STATUS_DUPLICATE};
            border-radius: 4px;
        }}
        QWidget#wl_statusError {{
            background-color: {STATUS_ERROR};
            border-radius: 4px;
        }}
        QWidget#wl_statusPending {{
            background-color: {STATUS_PENDING};
            border-radius: 4px;
        }}
    """


# ---------------------------------------------------------------------------
# Component-level style helpers
# ---------------------------------------------------------------------------
# These can be used for widget-level styles when the global stylesheet
# doesn't cover a specific case. Prefer global styles first.

class ComponentStyles:
    """Helper for generating component-specific QSS snippets."""

    @staticmethod
    def download_card() -> str:
        """QSS for a download card widget."""
        return f"""
            QWidget#wl_downloadCard {{
                background-color: {SURFACE_3};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: {CARD_BORDER_RADIUS}px;
            }}
            QWidget#wl_downloadCard:hover {{
                background-color: {SURFACE_4};
                border-color: {BORDER_STRONG};
            }}
            QLabel#wl_titleLabel {{
                color: {TEXT_PRIMARY};
                font-weight: 600;
                font-size: {FONT_SIZE_BASE}px;
            }}
            QLabel#wl_percentLabel {{
                color: {PRIMARY_GREEN};
                font-weight: 800;
                font-size: {FONT_SIZE_SM + 1}px;
            }}
            QLabel#wl_statusLabel {{
                color: {TEXT_SECONDARY};
                font-size: {FONT_SIZE_SM}px;
                font-weight: 600;
            }}
            QLabel#wl_speedLabel,
            QLabel#wl_etaLabel {{
                color: {TEXT_SECONDARY};
                font-size: {FONT_SIZE_SM}px;
                font-family: {FONT_STACK_MONO};
            }}
            QLabel#wl_statusIcon {{
                font-size: 16px;
            }}
        """

    @staticmethod
    def summary_card() -> str:
        """QSS for the batch summary card."""
        return f"""
            QWidget#wl_summaryCard {{
                background-color: {SURFACE_3};
                border: 2px solid {BORDER_DEFAULT};
                border-radius: 12px;
            }}
            QLabel#wl_summaryHeader {{
                color: {TEXT_PRIMARY};
                font-size: {FONT_SIZE_XL}px;
                font-weight: 700;
            }}
            QLabel#wl_summarySubtitle {{
                color: {TEXT_SECONDARY};
                font-size: {FONT_SIZE_BASE}px;
            }}
            QWidget#wl_metricBox {{
                background-color: {SURFACE_4};
                border: 1px solid {BORDER_STRONG};
                border-radius: 8px;
                min-width: 90px;
                min-height: 90px;
            }}
            QLabel#wl_successValue {{
                color: {STATUS_VALID};
                font-size: {FONT_SIZE_XL}px;
                font-weight: bold;
            }}
            QLabel#wl_failedValue {{
                color: {STATUS_ERROR};
                font-size: {FONT_SIZE_XL}px;
                font-weight: bold;
            }}
            QLabel#wl_timeValue {{
                color: {STATUS_INFO};
                font-size: {FONT_SIZE_XL}px;
                font-weight: bold;
            }}
            QLabel#wl_metricLabel {{
                color: {TEXT_SECONDARY};
                font-size: {FONT_SIZE_SM}px;
                font-weight: 600;
            }}
            QPushButton#wl_summaryOpenBtn {{
                background-color: {SURFACE_4};
                border: 1px solid {BORDER_STRONG};
                color: {TEXT_PRIMARY};
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: 600;
                font-size: {FONT_SIZE_BASE}px;
            }}
            QPushButton#wl_summaryOpenBtn:hover {{
                background-color: {SURFACE_5};
            }}
            QPushButton#wl_summaryNewBtn {{
                background-color: {PRIMARY_GREEN};
                border: none;
                color: {TEXT_INVERSE};
                border-radius: 8px;
                padding: 10px 24px;
                font-weight: 600;
                font-size: {FONT_SIZE_BASE}px;
            }}
            QPushButton#wl_summaryNewBtn:hover {{
                background-color: {PRIMARY_GREEN_HOVER};
            }}
        """

    @staticmethod
    def settings_page() -> str:
        """QSS for the settings page."""
        return f"""
            QLabel#wl_settingsTitle {{
                color: {TEXT_PRIMARY};
                font-size: {FONT_SIZE_XXL}px;
                font-weight: 700;
            }}
            QLabel#wl_settingDesc {{
                color: {TEXT_SECONDARY};
                font-size: {FONT_SIZE_SM}px;
                margin-left: 2px;
            }}
            QLabel#wl_dirPathLabel {{
                background-color: {SURFACE_3};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: {INPUT_BORDER_RADIUS}px;
                padding: 8px 12px;
                color: {TEXT_PRIMARY};
                font-family: {FONT_STACK_MONO};
                font-size: {FONT_SIZE_SM + 1}px;
            }}
            QPushButton#wl_changeDirBtn {{
                background-color: {SURFACE_4};
                border: 1px solid {BORDER_STRONG};
                color: {TEXT_PRIMARY};
                border-radius: {BUTTON_BORDER_RADIUS}px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: {FONT_SIZE_SM + 1}px;
            }}
            QPushButton#wl_changeDirBtn:hover {{
                background-color: {SURFACE_5};
            }}
        """


# Global instance for convenience
component_styles = ComponentStyles()
