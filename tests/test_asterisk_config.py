import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('asterisk_render', ROOT / 'asterisk/render.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


@pytest.mark.parametrize('transport', ['udp', 'tcp'])
def test_registration_transport(tmp_path, monkeypatch, transport):
    for key, value in {
        'ARI_PASSWORD': 'x' * 32, 'SIP_HOST': 'sip.example.test',
        'SIP_USERNAME': 'test-user', 'SIP_PASSWORD': 'test-password',
        'SIP_TRANSPORT': transport, 'SIP_EXTERNAL_ADDRESS': '',
    }.items():
        monkeypatch.setenv(key, value)
    renderer.render(tmp_path)
    config = (tmp_path / 'pjsip.conf').read_text()
    assert f'protocol={transport}\n' in config
    assert config.count(f'transport=transport-{transport}\n') == 2
    assert f'server_uri=sip:sip.example.test:5060;transport={transport}\n' in config
    assert f'contact=sip:sip.example.test:5060;transport={transport}\n' in config
    assert f'client_uri=sip:test-user@sip.example.test;transport={transport}\n' in config
    assert 'Hangup()' in (tmp_path / 'extensions.conf').read_text()
    assert (tmp_path / 'pjsip.conf').stat().st_mode & 0o777 == 0o600


def test_invalid_transport(tmp_path, monkeypatch):
    monkeypatch.setenv('ARI_PASSWORD', 'x' * 32)
    monkeypatch.setenv('SIP_TRANSPORT', 'invalid')
    with pytest.raises(ValueError, match='SIP_TRANSPORT'):
        renderer.render(tmp_path)


def test_compose_transport_wiring():
    service = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())['services']['asterisk']
    assert service['environment']['SIP_TRANSPORT'] == '${SIP_TRANSPORT:-udp}'
    assert any(':5060:5060/${SIP_TRANSPORT:-udp}' in p for p in service['ports'])
    assert any('10000-10099/udp' in p for p in service['ports'])
