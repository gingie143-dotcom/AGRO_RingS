"""Render Asterisk configuration at startup; reject config-injection characters."""
import os
from pathlib import Path


def value(key,default=''):
    result=os.environ.get(key,default)
    if any(c in result for c in '\r\n;[]'):
        raise ValueError('Invalid configuration characters in '+key)
    return result


def render(root):
    root.mkdir(parents=True,exist_ok=True)
    password=value('ARI_PASSWORD')
    if len(password)<24:
        raise ValueError('ARI_PASSWORD must contain at least 24 characters')
    (root/'http.conf').write_text('[general]\nenabled=yes\nbindaddr=0.0.0.0\nbindport=8088\n')
    (root/'ari.conf').write_text('[general]\nenabled=yes\npretty=no\n[caller]\ntype=user\nread_only=no\npassword='+password+'\n')
    (root/'rtp.conf').write_text('[general]\nrtpstart=10000\nrtpend=10099\n')
    (root/'extensions.conf').write_text('[default]\nexten => _X.,1,Hangup()\n[from-trunk]\nexten => _X.,1,Hangup()\n')
    (root/'logger.conf').write_text('[general]\n[logfiles]\nconsole => warning,error\n')
    (root/'manager.conf').write_text('[general]\nenabled=no\n')
    host=value('SIP_HOST')
    username=value('SIP_USERNAME')
    sip_password=value('SIP_PASSWORD')
    external=value('SIP_EXTERNAL_ADDRESS')
    local=value('SIP_LOCAL_NET','172.16.0.0/12')
    pjsip='[transport-udp]\ntype=transport\nprotocol=udp\nbind=0.0.0.0:5060\n'
    if external:
        pjsip+=f'external_signaling_address={external}\nexternal_media_address={external}\nlocal_net={local}\n'
    if host:
        if not username or not sip_password:
            raise ValueError('SIP credentials required with SIP_HOST')
        pjsip+=f'''
[trunk-auth]
type=auth
auth_type=userpass
username={username}
password={sip_password}
[trunk-aor]
type=aor
contact=sip:{host}
[trunk]
type=endpoint
transport=transport-udp
context=from-trunk
disallow=all
allow=ulaw
outbound_auth=trunk-auth
aors=trunk-aor
from_user={username}
from_domain={host}
direct_media=no
rtp_symmetric=yes
force_rport=yes
rewrite_contact=yes
[trunk-registration]
type=registration
transport=transport-udp
outbound_auth=trunk-auth
server_uri=sip:{host}
client_uri=sip:{username}@{host}
retry_interval=60
expiration=300
'''
    (root/'pjsip.conf').write_text(pjsip)
    os.chmod(root/'ari.conf',0o600)
    os.chmod(root/'pjsip.conf',0o600)

if __name__=='__main__':
    render(Path('/etc/asterisk'))
    os.execvp('asterisk',['asterisk','-f','-U','asterisk','-G','asterisk'])
