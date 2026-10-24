from pathlib import Path
from core.utils import sanitize_filename, build_final_mp3_path


def test_removes_ascii_reserved():
    assert sanitize_filename('a|b:c/d') == 'abcd'


def test_fullwidth_pipe():
    assert sanitize_filename('A ｜ B') == 'A B'


def test_reserved_device_name():
    assert sanitize_filename('CON') == '_CON'
    assert sanitize_filename('NUL') == '_NUL'


def test_trailing_dots_and_spaces():
    assert sanitize_filename('song...') == 'song'
    assert sanitize_filename('song   ') == 'song'


def test_control_chars_become_space():
    assert sanitize_filename('a\tb\nc') == 'a b c'


def test_empty_and_only_illegal():
    assert sanitize_filename('') == 'audio'
    assert sanitize_filename('///') == 'audio'


def test_length_cap():
    assert len(sanitize_filename('x' * 300)) == 150


def test_build_final_mp3_path_strips_illegal():
    p = build_final_mp3_path(Path('X'), 'Song|Name')
    assert p.name == 'SongName.mp3'


class TestFriendlyErrorMessage:
    """Los errores de yt-dlp, como los ve el usuario."""

    def test_strips_terminal_colors_and_maps_copyright(self):
        from core.utils import friendly_error_message
        crudo = ("\x1b[0;31mERROR:\x1b[0m [youtube] qruvRVkz_WQ: It was removed following "
                 "a copyright removal request by Sony Music Publishing")
        assert friendly_error_message(crudo) == "Eliminado de YouTube por un reclamo de copyright."

    def test_not_available(self):
        from core.utils import friendly_error_message
        crudo = "\x1b[0;31mERROR:\x1b[0m [youtube] xzN8SEQAdyY: This video is not available"
        assert friendly_error_message(crudo) == "El video no está disponible."

    def test_an_unknown_error_comes_back_clean_not_invented(self):
        from core.utils import friendly_error_message
        crudo = "\x1b[0;31mERROR:\x1b[0m [youtube] abcdefghijk: Something new went wrong"
        assert friendly_error_message(crudo) == "Something new went wrong"

    def test_a_title_with_the_word_playlist_is_not_a_playlist_error(self):
        from core.utils import friendly_error_message
        assert "playlists" not in friendly_error_message("HTTP Error 500 on My Playlist Mix")

    def test_empty(self):
        from core.utils import friendly_error_message
        assert friendly_error_message("") == "Error desconocido."
