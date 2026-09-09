import xml.dom.minidom as minidom
from services.export_service import build_m3u8, build_rekordbox_xml


class _Step:
    def __init__(self, track):
        self.track = track


def _steps():
    return [
        _Step({'id': '1', 'title': 'A', 'artist': 'X', 'key': '8A',
               'bpm': '124', 'duration': 180, 'path': r'C:\m\a.mp3'}),
        _Step({'id': '2', 'title': 'B', 'artist': 'Y', 'key': '9A',
               'bpm': '126', 'duration': 200, 'path': r'C:\m\b.mp3'}),
    ]


def test_m3u8_format_and_order():
    lines = build_m3u8(_steps()).splitlines()
    assert lines[0] == '#EXTM3U'
    assert lines[1] == '#EXTINF:180,X - A'
    assert lines[2] == r'C:\m\a.mp3'
    assert lines[3] == '#EXTINF:200,Y - B'


def test_rekordbox_well_formed_and_ordered():
    xml = build_rekordbox_xml(_steps(), 'Set')
    minidom.parseString(xml)  # raises if malformed
    assert xml.count('<TRACK TrackID') == 2
    assert xml.count('<TRACK Key') == 2
    assert 'Tonality="8A"' in xml
    assert 'AverageBpm="124.00"' in xml
    assert 'file://localhost/C:/m/a.mp3' in xml
