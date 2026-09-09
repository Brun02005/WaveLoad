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
