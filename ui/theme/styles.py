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
    ACCENT, ACCENT_MUTED,
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

    This stylesheet is applied once at the QApplication or QMainWindow level.
    It defines global defaults and all reusable component styles via
    objectName selectors.

    Returns
    -------
    str
        A complete QSS stylesheet string.
    """
    return f"""
        /* ================================================================
         * GLOBAL DEFAULTS
         * ================================================================ */
        QMainWindow {{
            background-color: {SURFACE_BASE};
        }}
        QWidget {{
            color: {TEXT_PRIMARY};
            font-family: {FONT_STACK_PRIMARY};
            font-size: {FONT_SIZE_BASE}px;
        }}

        /* ================================================================
         * SCROLLBARS (Global)
         * ================================================================ */
        QScrollBar:vertical {{
            border: none;
            background: {SCROLLBAR_TRACK};
            width: 6px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {SCROLLBAR_HANDLE};
            min-height: 20px;
            border-radius: 3px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {SCROLLBAR_HANDLE_HOVER};
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            border: none;
            background: none;
            height: 0px;
        }}
        QScrollBar:horizontal {{
            border: none;
            background: {SCROLLBAR_TRACK};
            height: 6px;
            margin: 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: {SCROLLBAR_HANDLE};
            min-width: 20px;
            border-radius: 3px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {SCROLLBAR_HANDLE_HOVER};
        }}
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {{
            border: none;
            background: none;
            width: 0px;
        }}

        /* ================================================================
         * SCROLL AREAS
         * ================================================================ */
        QScrollArea {{
            border: none;
            background-color: transparent;
        }}

        /* ================================================================
         * TOOLTIPS
         * ================================================================ */
        QToolTip {{
            background-color: {SURFACE_5};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_STRONG};
            padding: 6px 10px;
            font-size: {FONT_SIZE_SM}px;
            border-radius: 4px;
        }}

        /* ================================================================
         * SIDEBAR
         * ================================================================ */
        QWidget#wl_sidebar {{
            background-color: {SURFACE_1};
        }}
        QLabel#wl_logoLabel {{
            font-size: {FONT_SIZE_XL}px;
            font-weight: 800;
            color: {PRIMARY_GREEN};
            padding: 4px;
            letter-spacing: 1px;
        }}

        /* Sidebar Navigation Buttons */
        QPushButton#wl_navBtn,
        QPushButton#wl_navBtnActive {{
            background-color: transparent;
            border: none;
            border-radius: 4px;
            padding: 10px 14px;
            font-size: {FONT_SIZE_MD}px;
            font-weight: 600;
            text-align: left;
            color: {TEXT_SECONDARY};
        }}
        QPushButton#wl_navBtn:hover {{
            background-color: {SURFACE_2};
            color: {TEXT_PRIMARY};
        }}
        QPushButton#wl_navBtnActive {{
            background-color: {ACCENT_MUTED};
            color: {TEXT_PRIMARY};
            border-left: 3px solid {ACCENT};
            border-radius: 0px 4px 4px 0px;
        }}

        /* Sidebar Folder Box */
        QWidget#wl_sidebarFolderBox {{
            background-color: {SURFACE_2};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {CARD_BORDER_RADIUS}px;
        }}
        QLabel#wl_sfTitle {{
            font-size: {FONT_SIZE_SM}px;
            font-weight: 700;
            color: {TEXT_SECONDARY};
        }}
        QLabel#wl_sfPath {{
            font-size: {FONT_SIZE_SM}px;
            color: {TEXT_PRIMARY};
            font-family: {FONT_STACK_MONO};
        }}
        QPushButton#wl_sfBtn {{
            background-color: {SURFACE_3};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: 3px;
            padding: 4px 8px;
            font-size: {FONT_SIZE_SM}px;
            font-weight: 600;
            color: {TEXT_PRIMARY};
        }}
        QPushButton#wl_sfBtn:hover {{
            background-color: {SURFACE_4};
            border: 1px solid {PRIMARY_GREEN};
        }}

        /* ================================================================
         * TOOLBAR
         * ================================================================ */
        QWidget#wl_toolbar {{
            background-color: {SURFACE_1};
            border-bottom: 1px solid {BORDER_SUBTLE};
        }}

        /* Toolbar Search */
        QLineEdit#wl_searchInput {{
            background-color: {SURFACE_3};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {INPUT_BORDER_RADIUS}px;
            padding: 6px 12px 6px 32px;
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_BASE}px;
            font-family: {FONT_STACK_PRIMARY};
        }}
        QLineEdit#wl_searchInput:focus {{
            border-color: {PRIMARY_GREEN};
        }}
        QLineEdit#wl_searchInput::placeholder {{
            color: {TEXT_MUTED};
        }}

        /* Toolbar Buttons */
        QPushButton#wl_toolbarBtn {{
            background-color: transparent;
            border: none;
            border-radius: {BUTTON_BORDER_RADIUS}px;
            padding: 6px 12px;
            font-size: {FONT_SIZE_SM}px;
            font-weight: 600;
            color: {TEXT_SECONDARY};
        }}
        QPushButton#wl_toolbarBtn:hover {{
            background-color: {SURFACE_3};
            color: {TEXT_PRIMARY};
        }}

        /* ================================================================
         * MAIN CONTAINERS
         * ================================================================ */
        QFrame#wl_mainContainer {{
            background-color: {SURFACE_2};
            border-left: 1px solid {BORDER_SUBTLE};
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
         * ACTION BUTTONS
         * ================================================================ */
        QPushButton#wl_primaryBtn {{
            background-color: {PRIMARY_GREEN};
            border: none;
            border-radius: {BUTTON_BORDER_RADIUS}px;
            color: {TEXT_INVERSE};
            font-weight: 700;
            font-size: {FONT_SIZE_MD}px;
            letter-spacing: 0.3px;
        }}
        QPushButton#wl_primaryBtn:hover {{
            background-color: {PRIMARY_GREEN_HOVER};
        }}
        QPushButton#wl_primaryBtn:disabled {{
            background-color: {PRIMARY_GREEN_MUTED};
            color: {TEXT_MUTED};
        }}
        QPushButton#wl_secondaryBtn {{
            background-color: {SURFACE_3};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {BUTTON_BORDER_RADIUS}px;
            padding: 6px 12px;
            font-weight: 600;
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_SM}px;
        }}
        QPushButton#wl_secondaryBtn:hover {{
            background-color: {SURFACE_4};
            border-color: {BORDER_STRONG};
        }}
        QPushButton#wl_dangerBtn {{
            background-color: transparent;
            border: 1px solid {PRIMARY_RED};
            border-radius: {BUTTON_BORDER_RADIUS}px;
            padding: 6px 12px;
            font-weight: 600;
            color: {PRIMARY_RED};
            font-size: {FONT_SIZE_SM}px;
        }}
        QPushButton#wl_dangerBtn:hover {{
            background-color: {PRIMARY_RED};
            color: {TEXT_PRIMARY};
        }}

        /* ================================================================
         * INPUT AREAS
         * ================================================================ */
        QPlainTextEdit#wl_inputBox {{
            background-color: {SURFACE_3};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {INPUT_BORDER_RADIUS}px;
            padding: 10px;
            color: {PRIMARY_GREEN};
            font-family: {FONT_STACK_MONO};
            font-size: {FONT_SIZE_BASE}px;
        }}
        QPlainTextEdit#wl_inputBox:focus {{
            border-color: {PRIMARY_GREEN};
        }}

        /* ================================================================
         * LOG BOX
         * ================================================================ */
        QPlainTextEdit#wl_logBox {{
            background-color: {SURFACE_BASE};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {INPUT_BORDER_RADIUS}px;
            padding: 8px;
            color: {TEXT_SECONDARY};
            font-family: {FONT_STACK_MONO};
            font-size: {FONT_SIZE_SM}px;
        }}

        /* ================================================================
         * PROGRESS BARS
         * ================================================================ */
        QProgressBar {{
            background-color: {SURFACE_BASE};
            border: none;
            border-radius: {PROGRESS_BAR_HEIGHT // 2}px;
        }}
        QProgressBar::chunk {{
            background-color: {PRIMARY_GREEN};
            border-radius: {PROGRESS_BAR_HEIGHT // 2}px;
        }}

        /* ================================================================
         * LABELS
         * ================================================================ */
        QLabel#wl_counterLabel {{
            color: {TEXT_SECONDARY};
            font-weight: 600;
            font-size: {FONT_SIZE_SM + 1}px;
        }}
        QLabel#wl_sectionTitle {{
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_MD}px;
            font-weight: 600;
        }}

        /* ================================================================
         * LIBRARY TRACK TABLE (DJ crate)
         * ================================================================ */
        QTableView#wl_trackTable {{
            background-color: {SURFACE_2};
            alternate-background-color: {SURFACE_1};
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
        }}
        QTableView#wl_trackTable QHeaderView::section {{
            background-color: {SURFACE_2};
            color: {TEXT_MUTED};
            border: none;
            border-bottom: 1px solid {BORDER_DEFAULT};
            padding: 7px 10px;
            font-size: {FONT_SIZE_XS + 1}px;
            font-weight: 700;
        }}

        /* ================================================================
         * GLOBAL PROGRESS BOX
         * ================================================================ */
        QWidget#wl_globalProgressBox {{
            background-color: {SURFACE_3};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {CARD_BORDER_RADIUS}px;
        }}
        QLabel#wl_globalProgressTitle {{
            color: {TEXT_PRIMARY};
            font-weight: 800;
            font-size: {FONT_SIZE_BASE}px;
        }}
        QLabel#wl_globalStatsLabel {{
            color: {PRIMARY_GREEN};
            font-size: {FONT_SIZE_SM + 1}px;
            font-weight: 800;
        }}

        /* ================================================================
         * COLLAPSIBLE PANEL
         * ================================================================ */
        QPushButton#wl_collapsibleHeader {{
            background-color: {SURFACE_3};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {BUTTON_BORDER_RADIUS}px;
            text-align: left;
        }}
        QPushButton#wl_collapsibleHeader:hover {{
            background-color: {SURFACE_4};
            border-color: {BORDER_STRONG};
        }}
        QLabel#wl_arrowLabel {{
            color: {TEXT_SECONDARY};
            font-size: {FONT_SIZE_XS}px;
            font-weight: bold;
        }}
        QLabel#wl_headerText {{
            color: {TEXT_SECONDARY};
            font-size: {FONT_SIZE_SM + 1}px;
            font-weight: 600;
        }}

        /* ================================================================
         * CONTEXT PANEL
         * ================================================================ */
        QLabel#wl_contextTitle {{
            font-size: {FONT_SIZE_LG}px;
            font-weight: 700;
            color: {TEXT_PRIMARY};
        }}
        QLabel#wl_contextSubtitle {{
            font-size: {FONT_SIZE_SM}px;
            color: {TEXT_SECONDARY};
        }}
        QLabel#wl_infoLabel {{
            font-size: {FONT_SIZE_SM}px;
            color: {TEXT_MUTED};
            font-weight: 600;
        }}
        QLabel#wl_infoValue {{
            font-size: {FONT_SIZE_BASE}px;
            color: {TEXT_PRIMARY};
        }}

        /* ================================================================
         * STATUS INDICATORS
         * ================================================================ */
        QWidget#wl_statusValid {{
            background-color: {STATUS_VALID};
            border-radius: 5px;
        }}
        QWidget#wl_statusDuplicate {{
            background-color: {STATUS_DUPLICATE};
            border-radius: 5px;
        }}
        QWidget#wl_statusError {{
            background-color: {STATUS_ERROR};
            border-radius: 5px;
        }}
        QWidget#wl_statusPending {{
            background-color: {STATUS_PENDING};
            border-radius: 5px;
        }}

        /* ================================================================
         * COMBOBOX (Settings)
         * ================================================================ */
        QComboBox#wl_combo {{
            background-color: {SURFACE_3};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {INPUT_BORDER_RADIUS}px;
            padding: 6px 10px;
            color: {TEXT_PRIMARY};
            min-width: 200px;
        }}
        QComboBox#wl_combo QAbstractItemView {{
            background-color: {SURFACE_3};
            color: {TEXT_PRIMARY};
            selection-background-color: {STATUS_INFO};
        }}

        /* ================================================================
         * CHECKBOX
         * ================================================================ */
        QCheckBox {{
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_BASE}px;
            font-weight: 500;
            spacing: 8px;
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
